"""Long-term memory manager for Memory-type knowledge spaces.

This module provides automatic memory retrieval and writing for agents
that are bound to Memory-type knowledge spaces. Unlike the memory tools
(memory_search, memory_save) which require explicit agent invocation,
this manager operates as a framework-level hook:

- Before agent reasoning: Automatically retrieves relevant memories
- After agent completes: Automatically extracts and writes important content
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from derisk._private.config import Config
from derisk.storage.memory.base import MemoryStoreBase, MemoryEntry
from derisk.storage.memory.processor import MemoryProcessor
from derisk.storage.memory.recall_tracker import RecallTracker
from derisk.storage.memory.strategy import MemorySpaceStrategy
from derisk.storage.memory.hybrid_search import HybridSearchEngine, HybridSearchConfig
from derisk.storage.memory.lifecycle import DefaultLifecycleHooks
from derisk.storage.memory.snapshot import FrozenSnapshotManager
from derisk.storage.memory.promotion import MemoryPromotionEngine

logger = logging.getLogger(__name__)
CFG = Config()


@dataclass
class LongTermMemoryConfig:
    """Configuration for long-term memory integration.

    This config is parsed from resource_memory AgentResource value.
    """
    # List of bound memory spaces
    memories: List[Dict[str, str]] = field(default_factory=list)
    # Whether to automatically write memories after conversation
    auto_memory: bool = True
    # Whether to enable knowledge graph operations
    enable_kg: bool = False
    # Number of memories to retrieve before each conversation
    top_k: int = 5
    # Maximum distance threshold for memory retrieval
    max_distance: float = 0.4
    # Minimum content length to consider for auto-write
    min_content_length: int = 50
    # Wing identifier (user/session)
    wing: str = "default"
    # Per-space processing strategies
    space_strategies: Dict[str, MemorySpaceStrategy] = field(default_factory=dict)
    # Whether to enable recall tracking
    recall_tracking_enabled: bool = True
    # Tier 2 reflection cadence: run cross-turn consolidation every N turns.
    reflection_interval: int = 10

    @classmethod
    def from_resource_value(cls, value: Any) -> Optional["LongTermMemoryConfig"]:
        """Parse config from AgentResource value.

        Args:
            value: The value field of AgentResource (string or dict)

        Returns:
            LongTermMemoryConfig or None if invalid
        """
        if value is None:
            return None

        parsed = {}
        if isinstance(value, dict):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Invalid resource_memory value: {value}")
                return None
        else:
            return None

        return cls(
            memories=parsed.get("memories", []),
            auto_memory=parsed.get("auto_memory", True),
            enable_kg=parsed.get("enable_kg", False),
            top_k=parsed.get("top_k", 5),
            max_distance=parsed.get("max_distance", 0.4),
            min_content_length=parsed.get("min_content_length", 50),
            wing=parsed.get("wing", "default"),
            reflection_interval=parsed.get("reflection_interval", 10),
        )


class LongTermMemoryManager:
    """Manager for automatic long-term memory integration.

    This manager:
    1. Holds references to multiple MemoryStoreBase instances (one per bound space)
    2. Retrieves relevant memories before agent reasoning
    3. Writes important content after agent completes (if auto_memory=True)
    4. Uses per-space MemoryProcessor for LLM-based extraction and consolidation
    5. Tracks retrieval history for memory promotion decisions
    """

    # Keywords that suggest important content worth memorizing
    _IMPORTANCE_KEYWORDS = {
        "decision", "decided", "agreed", "conclusion", "important",
        "remember", "note", "key point", "action item", "deadline",
        "决定", "结论", "重要", "记住", "注意", "关键", "截止",
        "偏好", "喜欢", "不喜欢", "preference", "like", "dislike",
    }

    def __init__(
        self,
        config: LongTermMemoryConfig,
        memory_stores: Dict[str, MemoryStoreBase],
        processors: Optional[Dict[str, MemoryProcessor]] = None,
        strategies: Optional[Dict[str, MemorySpaceStrategy]] = None,
        recall_tracker: Optional[RecallTracker] = None,
        hybrid_search_engine: Optional[Any] = None,  # HybridSearchEngine
        lifecycle_hooks: Optional[Any] = None,
        snapshot_manager: Optional[Any] = None,
        promotion_engine: Optional[Any] = None,
    ):
        """Initialize the manager.

        Args:
            config: Configuration from resource_memory
            memory_stores: Dict mapping memory_id to MemoryStoreBase instance
            processors: Dict mapping memory_id to MemoryProcessor
            strategies: Dict mapping memory_id to MemorySpaceStrategy
            recall_tracker: RecallTracker instance
            hybrid_search_engine: HybridSearchEngine instance
            lifecycle_hooks: Optional DefaultLifecycleHooks for tier 3 curation
            snapshot_manager: Optional FrozenSnapshotManager for tier 3 snapshots
            promotion_engine: Optional MemoryPromotionEngine for tier 3 promotion
        """
        self._config = config
        self._memory_stores = memory_stores
        self._processors = processors or {}
        self._strategies = strategies or {}
        self._recall_tracker = recall_tracker or RecallTracker()
        self._hybrid_search_engine = hybrid_search_engine
        self._lifecycle_hooks = lifecycle_hooks
        self._snapshot_manager = snapshot_manager
        self._promotion_engine = promotion_engine
        self._last_conversation_content: Optional[str] = None

    @property
    def config(self) -> LongTermMemoryConfig:
        """Get the configuration."""
        return self._config

    @property
    def memory_stores(self) -> Dict[str, MemoryStoreBase]:
        """Get the memory stores."""
        return self._memory_stores

    def has_stores(self) -> bool:
        """Check if any memory stores are available."""
        return len(self._memory_stores) > 0

    def get_bound_space_names(self) -> List[str]:
        """Get names of bound memory spaces."""
        return [m.get("memory_name", m.get("memory_id", "")) for m in self._config.memories]

    async def retrieve_relevant_memories(
        self,
        query: str,
        top_k: Optional[int] = None,
        use_hybrid_search: bool = True,
        exclude_rooms: Optional[List[str]] = None,
    ) -> str:
        """Retrieve relevant memories from all bound spaces before agent reasoning.

        This method searches across all memory spaces and returns formatted
        text that can be injected into the agent's context.

        Args:
            query: The user's question or current context
            top_k: Override config.top_k if provided
            use_hybrid_search: If True, use HybridSearchEngine (temporal decay + MMR)
            exclude_rooms: Rooms to skip (e.g. static-layer rooms like "profile"
                that are already frozen into system prompt — avoids duplicate
                injection).

        Returns:
            Formatted memory text for context injection
        """
        if not self.has_stores():
            return ""

        top_k = top_k or self._config.top_k
        exclude_rooms_set = set(exclude_rooms or [])
        all_entries: List[Tuple[str, MemoryEntry]] = []  # (space_name, entry)

        for memory_id, store in self._memory_stores.items():
            space_name = self._get_space_name(memory_id)
            try:
                if use_hybrid_search and hasattr(self, '_hybrid_search_engine') and self._hybrid_search_engine:
                    # Use HybridSearchEngine with temporal decay + MMR
                    from derisk.storage.memory.hybrid_search import HybridSearchConfig
                    config = HybridSearchConfig(
                        vector_weight=0.6,
                        keyword_weight=0.4,
                        temporal_decay_enabled=True,
                        temporal_decay_halflife=30,
                        mmr_enabled=True,
                        mmr_diversity=0.5,
                    )
                    results = await self._hybrid_search_engine.search(
                        query=query,
                        store=store,
                        top_k=top_k,
                        wing=self._config.wing,
                        config=config,
                    )
                    for r in results:
                        if exclude_rooms_set and r.room in exclude_rooms_set:
                            continue
                        all_entries.append((space_name, MemoryEntry(
                            id=r.id,
                            content=r.content,
                            wing=r.wing,
                            room=r.room,
                            score=r.score,
                            metadata=r.metadata,
                        )))
                else:
                    # Direct store search (fallback)
                    entries = await store.asearch_memory(
                        query=query,
                        top_k=top_k,
                        wing=self._config.wing,
                        max_distance=self._config.max_distance,
                    )
                    for entry in entries:
                        if exclude_rooms_set and entry.room in exclude_rooms_set:
                            continue
                        all_entries.append((space_name, entry))

                # Track recall for promotion decisions
                if self._config.recall_tracking_enabled:
                    await self._recall_tracker.record(query, [e[1] for e in all_entries if e[0] == space_name], memory_id)
            except Exception as e:
                logger.warning(f"Failed to search memory space {memory_id}: {e}")
                continue

        if not all_entries:
            return ""

        # Sort by score and deduplicate
        all_entries.sort(key=lambda x: x[1].score or 0, reverse=True)

        # Format as structured text
        memory_lines = []
        seen_content = set()

        for space_name, entry in all_entries[:top_k]:
            # Deduplicate by content
            content_key = entry.content[:100]
            if content_key in seen_content:
                continue
            seen_content.add(content_key)

            score_str = f" (相关性: {entry.score:.2f})" if entry.score else ""
            room_str = f" [{entry.room}]" if entry.room else ""
            space_str = f" [来源: {space_name}]" if space_name else ""
            memory_lines.append(
                f"- {entry.content}{room_str}{score_str}{space_str}"
            )

        if not memory_lines:
            return ""

        memory_text = (
            "## 相关长期记忆\n\n"
            "以下是从绑定的记忆空间中检索到的相关信息：\n\n"
            + "\n".join(memory_lines)
        )

        logger.info(
            f"[LongTermMemory] Retrieved {len(memory_lines)} memories "
            f"from {len(self._memory_stores)} spaces for query: {query[:50]}..."
        )

        return memory_text

    async def write_memory_auto(
        self,
        user_message: str,
        agent_response: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """Backward-compatible wrapper. Delegates to write_turn_lightweight."""
        return await self.write_turn_lightweight(
            user_message=user_message,
            agent_response=agent_response,
            metadata=metadata,
        )

    async def write_turn_lightweight(
        self,
        user_message: str,
        agent_response: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """Tier 1: per-turn lightweight memory write.

        Called (asynchronously, via the turn_complete hook) after each
        successful agent turn. Each space independently processes and writes
        content based on its own strategy.

        Args:
            user_message: The user's input message
            agent_response: The agent's response
            metadata: Additional metadata to attach

        Returns:
            Dict mapping space_id to whether something was written
        """
        if not self._config.auto_memory:
            logger.info(
                "[LongTermMemory] write_turn_lightweight skipped: auto_memory=False"
            )
            return {}

        if not self.has_stores():
            logger.info(
                "[LongTermMemory] write_turn_lightweight skipped: no memory stores bound"
            )
            return {}

        results = {}
        conversation = f"用户: {user_message.strip()}\n助手: {agent_response.strip()}"
        conv_id = (metadata or {}).get("conv_id")
        round_no = (metadata or {}).get("round")
        logger.info(
            "[LongTermMemory] write_turn_lightweight start conv=%s round=%s "
            "spaces=%d user_len=%d ai_len=%d",
            conv_id,
            round_no,
            len(self._memory_stores),
            len(user_message or ""),
            len(agent_response or ""),
        )

        for space_id, store in self._memory_stores.items():
            strategy = self._strategies.get(space_id)
            processor = self._processors.get(space_id)

            # Check if auto-extraction is enabled for this space
            if strategy and not strategy.auto_extraction:
                logger.info(
                    "[LongTermMemory] space=%s skipped: auto_extraction=False",
                    space_id,
                )
                results[space_id] = False
                continue

            try:
                # Use processor for LLM-based extraction if available
                if processor:
                    extracted = await processor.extract_key_content(
                        conversation=conversation,
                        extraction_prompt=strategy.extraction_prompt if strategy else None,
                    )

                    if not extracted:
                        logger.info(
                            "[LongTermMemory] space=%s skipped: extract_key_content "
                            "returned empty",
                            space_id,
                        )
                        results[space_id] = False
                        continue

                    # Retrieve related memories for consolidation
                    existing = await store.asearch_memory(
                        query=user_message,
                        top_k=5,
                        wing=self._config.wing,
                        max_distance=self._config.max_distance,
                    )

                    # Consolidate with existing memories
                    threshold = strategy.consolidation_threshold if strategy else 0.7
                    consolidation = await processor.consolidate_memories(
                        existing=existing,
                        new=extracted,
                        consolidation_threshold=threshold,
                    )

                    # Write new memories
                    for mem in consolidation.new_memories:
                        await store.awrite_memory(
                            content=mem.content,
                            wing=self._config.wing,
                            room=mem.room,
                            metadata=mem.metadata,
                        )

                    # Extract KG triples if enabled
                    kg_enabled = strategy.kg_extraction if strategy else self._config.enable_kg
                    if kg_enabled:
                        triples = await processor.extract_triples(agent_response)
                        for triple in triples:
                            try:
                                await store.akg_add(
                                    subject=triple.get("subject", ""),
                                    predicate=triple.get("predicate", ""),
                                    object_=triple.get("object", ""),
                                )
                            except Exception as e:
                                logger.warning(f"Failed to add KG triple: {e}")

                    results[space_id] = True
                    logger.info(
                        "[LongTermMemory] space=%s wrote (processor path) "
                        "extracted=%d new=%d",
                        space_id,
                        len(extracted),
                        len(consolidation.new_memories),
                    )
                else:
                    # Fallback to keyword-based extraction (existing behavior)
                    content = self._extract_noteworthy_content(user_message, agent_response)
                    if not content:
                        logger.info(
                            "[LongTermMemory] space=%s skipped: _extract_noteworthy_content "
                            "returned None (below importance threshold)",
                            space_id,
                        )
                        results[space_id] = False
                        continue

                    room = self._classify_room(content)
                    await store.awrite_memory(
                        content=content,
                        wing=self._config.wing,
                        room=room,
                    )
                    results[space_id] = True
                    logger.info(
                        "[LongTermMemory] space=%s wrote (fallback path) room=%s "
                        "content_len=%d",
                        space_id,
                        room,
                        len(content),
                    )

            except Exception as e:
                logger.warning(
                    "[LongTermMemory] space=%s auto-write failed: %s",
                    space_id,
                    e,
                    exc_info=True,
                )
                results[space_id] = False

        logger.info(
            "[LongTermMemory] write_turn_lightweight done conv=%s round=%s results=%s",
            conv_id,
            round_no,
            results,
        )
        return results

    async def reflect_on_last_n_turns(
        self,
        n: int = 10,
        turns: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """Tier 2: cross-turn reflection / consolidation.

        Runs every N turns (N defaults to 10). Pulls the last N turns from
        session history (caller may pass them in `turns`; otherwise we best-
        effort pull from `_last_conversation_content`), feeds the combined
        transcript through `processor.consolidate_memories` for cross-turn
        dedup / refinement, and writes the consolidated entries.

        Args:
            n: Window size. Ignored when `turns` is provided.
            turns: Optional pre-fetched list of {user, assistant} dicts.
            metadata: Extra metadata to attach to writes.

        Returns:
            Dict mapping space_id to whether reflection wrote anything.
        """
        if not self.has_stores():
            return {}

        if turns is None:
            turns = []
        if not turns:
            logger.debug("[LongTermMemory] tier 2: no turns to reflect on")
            return {}

        results: Dict[str, bool] = {}
        transcript_parts = []
        for t in turns:
            u = (t.get("user") or "").strip()
            a = (t.get("assistant") or "").strip()
            if u or a:
                transcript_parts.append(f"用户: {u}\n助手: {a}")
        if not transcript_parts:
            return {}
        transcript = "\n\n".join(transcript_parts)

        for space_id, store in self._memory_stores.items():
            strategy = self._strategies.get(space_id)
            processor = self._processors.get(space_id)
            if strategy and not strategy.auto_extraction:
                results[space_id] = False
                continue
            if processor is None:
                results[space_id] = False
                continue
            try:
                extracted = await processor.extract_key_content(
                    conversation=transcript,
                    extraction_prompt=strategy.extraction_prompt if strategy else None,
                )
                if not extracted:
                    results[space_id] = False
                    continue

                # Retrieve existing and consolidate against the wider window
                existing = await store.asearch_memory(
                    query=transcript[:500],
                    top_k=10,
                    wing=self._config.wing,
                    max_distance=self._config.max_distance,
                )
                threshold = strategy.consolidation_threshold if strategy else 0.7
                consolidation = await processor.consolidate_memories(
                    existing=existing,
                    new=extracted,
                    consolidation_threshold=threshold,
                )

                written = 0
                for mem in consolidation.new_memories:
                    await store.awrite_memory(
                        content=mem.content,
                        wing=self._config.wing,
                        room=mem.room,
                        metadata=mem.metadata,
                    )
                    written += 1

                if self._config.enable_kg or (strategy and strategy.kg_extraction):
                    triples = await processor.extract_triples(transcript)
                    for triple in triples:
                        try:
                            await store.akg_add(
                                subject=triple.get("subject", ""),
                                predicate=triple.get("predicate", ""),
                                object_=triple.get("object", ""),
                            )
                        except Exception as e:
                            logger.warning(f"[Tier2] Failed to add KG triple: {e}")

                results[space_id] = written > 0
                logger.info(
                    f"[LongTermMemory] Tier 2 reflection: {written} consolidated "
                    f"memories for space {space_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[LongTermMemory] Tier 2 reflection failed for space {space_id}: {e}"
                )
                results[space_id] = False

        return results

    async def curate_session(
        self,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Tier 3: session-end curation.

        Triggered by the `conversation_complete` hook. Runs:
        - lifecycle_hooks.on_session_end for any final extraction
        - promotion_engine.run_promotion_sweep to promote hot memories
        - snapshot_manager.capture_snapshot to freeze a session-end view

        Returns:
            Dict with per-space curation summary.
        """
        summary: Dict[str, Any] = {"spaces": {}}
        if not self.has_stores():
            return summary

        history = conversation_history or []

        # Run lifecycle hook if attached (best-effort).
        try:
            from derisk.storage.memory.lifecycle import DefaultLifecycleHooks
            if isinstance(getattr(self, "_lifecycle_hooks", None), DefaultLifecycleHooks):
                # Default is no-op; real implementations can plug in here.
                await self._lifecycle_hooks.on_session_end(history)
        except Exception as e:
            logger.warning(f"[Tier3] lifecycle on_session_end failed: {e}")

        for space_id, store in self._memory_stores.items():
            space_summary: Dict[str, Any] = {}
            try:
                # Promotion sweep — best-effort, requires recall_tracker stats.
                promotion_engine = getattr(self, "_promotion_engine", None)
                if promotion_engine is not None:
                    try:
                        promo_result = await promotion_engine.run_promotion_sweep(
                            space_id=space_id,
                            store=store,
                        )
                        space_summary["promotions"] = getattr(
                            promo_result, "promoted_count", 0
                        )
                    except Exception as e:
                        logger.debug(
                            f"[Tier3] promotion sweep skipped for {space_id}: {e}"
                        )

                # Snapshot — best-effort.
                snapshot_manager = getattr(self, "_snapshot_manager", None)
                if snapshot_manager is not None:
                    try:
                        # Aggregate content for snapshot
                        content_preview = ""
                        for msg in history[-5:]:
                            role = msg.get("role", "")
                            c = msg.get("content", "")
                            if isinstance(c, str):
                                content_preview += f"{role}: {c}\n"
                        snapshot_manager.capture_snapshot(
                            space_id=space_id,
                            content=content_preview,
                            memory_count=-1,
                        )
                        space_summary["snapshot_captured"] = True
                    except Exception as e:
                        logger.debug(
                            f"[Tier3] snapshot capture skipped for {space_id}: {e}"
                        )

                summary["spaces"][space_id] = space_summary
            except Exception as e:
                logger.warning(
                    f"[LongTermMemory] Tier 3 curation failed for space {space_id}: {e}"
                )
                summary["spaces"][space_id] = {"error": str(e)}

        logger.info(
            f"[LongTermMemory] Tier 3 curation done for {len(summary['spaces'])} spaces"
        )
        return summary

    def _get_primary_store(self) -> Tuple[Optional[str], Optional[MemoryStoreBase]]:
        """Get the primary memory store (first one in config)."""
        if not self._config.memories or not self._memory_stores:
            return None, None

        primary_memory_id = self._config.memories[0].get("memory_id")
        if primary_memory_id and primary_memory_id in self._memory_stores:
            return primary_memory_id, self._memory_stores[primary_memory_id]

        # Fallback to first available
        for memory_id, store in self._memory_stores.items():
            return memory_id, store

        return None, None

    def _get_space_name(self, memory_id: str) -> str:
        """Get the display name for a memory space."""
        for m in self._config.memories:
            if m.get("memory_id") == memory_id:
                return m.get("memory_name", memory_id)
        return memory_id

    def _extract_noteworthy_content(
        self,
        user_message: str,
        agent_response: str,
    ) -> Optional[str]:
        """Extract noteworthy content from conversation.

        Returns None if content is not important enough to memorize.
        """
        parts = []

        if user_message and user_message.strip():
            parts.append(f"用户: {user_message.strip()}")

        if agent_response and agent_response.strip():
            parts.append(f"助手: {agent_response.strip()}")

        if not parts:
            return None

        combined = "\n".join(parts)

        # Check minimum length
        if len(combined) < self._config.min_content_length:
            return None

        # Check importance keywords
        combined_lower = combined.lower()
        has_keywords = any(kw in combined_lower for kw in self._IMPORTANCE_KEYWORDS)

        # Long content is considered important
        if len(combined) > 500 or has_keywords:
            return combined

        return None

    def _classify_room(self, content: str) -> str:
        """Classify content into a topic room."""
        content_lower = content.lower()

        topic_keywords = {
            "backend": {"api", "database", "server", "endpoint", "sql", "后端", "数据库"},
            "frontend": {"ui", "component", "css", "react", "vue", "前端", "页面"},
            "devops": {"deploy", "ci", "docker", "kubernetes", "部署", "运维"},
            "architecture": {"design", "pattern", "architecture", "refactor", "架构", "设计"},
            "bug": {"bug", "fix", "error", "issue", "缺陷", "修复"},
            "meeting": {"meeting", "discuss", "agree", "会议", "讨论"},
            "preference": {"偏好", "喜欢", "prefer", "like", "want", "希望"},
        }

        best_room = "general"
        best_score = 0

        for room, keywords in topic_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > best_score:
                best_score = score
                best_room = room

        return best_room

    async def get_recall_stats(self, space_id: str) -> Dict[str, Any]:
        """Get recall statistics for a space."""
        stats = await self._recall_tracker.get_recall_stats(space_id)
        return {mid: {
            "recall_count": s.recall_count,
            "average_score": s.average_score,
            "unique_queries": s.unique_queries,
        } for mid, s in stats.items()}

    async def get_promotion_candidates(
        self,
        space_id: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get top promotion candidates for a space."""
        return await self._recall_tracker.get_top_candidates(space_id, top_k)


async def create_long_term_memory_manager(
    config: LongTermMemoryConfig,
    system_app: Any,
    processors: Optional[Dict[str, MemoryProcessor]] = None,
    strategies: Optional[Dict[str, MemorySpaceStrategy]] = None,
) -> Optional[LongTermMemoryManager]:
    """Create a LongTermMemoryManager with initialized memory stores.

    Args:
        config: The configuration parsed from resource_memory
        system_app: SystemApp instance for getting StorageManager
        processors: Dict mapping memory_id to MemoryProcessor
        strategies: Dict mapping memory_id to MemorySpaceStrategy

    Returns:
        LongTermMemoryManager or None if no valid memory spaces
    """
    if not config or not config.memories:
        return None

    from derisk.component import ComponentType
    # TODO: rewire to new knowledge module (Task #9)
    try:
        from derisk_serve.rag.storage_manager import StorageManager
    except ImportError:
        logger.warning(
            "StorageManager unavailable (old rag module removed); "
            "skipping long-term memory manager init."
        )
        return None

    try:
        storage_manager: StorageManager = system_app.get_component(
            ComponentType.RAG_STORAGE_MANAGER, StorageManager
        )
    except Exception as e:
        logger.warning(f"StorageManager not available: {e}")
        return None

    memory_stores: Dict[str, MemoryStoreBase] = {}

    for memory_item in config.memories:
        memory_id = memory_item.get("memory_id")
        if not memory_id:
            continue

        try:
            memory_store = storage_manager.create_memory_store(memory_id)
            if memory_store:
                memory_stores[memory_id] = memory_store
                logger.info(f"[LongTermMemory] Connected to memory space: {memory_id}")
        except Exception as e:
            logger.warning(f"Failed to create memory store for {memory_id}: {e}")

    if not memory_stores:
        return None

    return LongTermMemoryManager(
        config=config,
        memory_stores=memory_stores,
        processors=processors,
        strategies=strategies,
    )


# ------------------------------------------------------------------
# MemoryIntegrationBundle — full long-term memory stack
# ------------------------------------------------------------------


@dataclass
class MemoryIntegrationBundle:
    """Complete memory stack for an agent.

    Bundles together all long-term memory components:
    - config: LongTermMemoryConfig (parsed from resource)
    - manager: LongTermMemoryManager (retrieval + auto-write)
    - processors: per-space LLM processors
    - strategies: per-space processing strategies
    - recall_tracker: retrieval history tracking
    - hybrid_search: enhanced search with temporal decay + MMR
    - lifecycle_hooks: session-level event handlers
    - snapshot_manager: frozen snapshot for prefix cache
    - promotion_engine: three-phase memory promotion
    """

    config: LongTermMemoryConfig
    manager: LongTermMemoryManager
    processors: Dict[str, MemoryProcessor] = field(default_factory=dict)
    strategies: Dict[str, MemorySpaceStrategy] = field(default_factory=dict)
    recall_tracker: RecallTracker = field(default_factory=RecallTracker)
    hybrid_search: HybridSearchEngine = field(default_factory=HybridSearchEngine)
    lifecycle_hooks: Any = field(default_factory=DefaultLifecycleHooks)
    snapshot_manager: FrozenSnapshotManager = field(default_factory=FrozenSnapshotManager)
    promotion_engine: MemoryPromotionEngine = field(default_factory=MemoryPromotionEngine)

    def get_search_config(self) -> HybridSearchConfig:
        """Get hybrid search config from bundle."""
        return HybridSearchConfig(
            vector_weight=0.6,
            keyword_weight=0.4,
            temporal_decay_enabled=True,
            temporal_decay_halflife=30,
            mmr_enabled=True,
            mmr_diversity=0.5,
        )


async def create_memory_integration_bundle(
    config: LongTermMemoryConfig,
    system_app: Any,
    processor_factory: Optional[Any] = None,
    strategy_overrides: Optional[Dict[str, MemorySpaceStrategy]] = None,
) -> Optional[MemoryIntegrationBundle]:
    """Create a complete memory integration bundle.

    Single entry point for building the full long-term memory stack.
    Creates all components and wires them together.

    Args:
        config: LongTermMemoryConfig from resource parsing
        system_app: SystemApp instance for getting StorageManager
        processor_factory: Callable(space_id) -> MemoryProcessor
                          If None, creates default LLMMemoryProcessor
        strategy_overrides: Pre-built MemorySpaceStrategy per space

    Returns:
        MemoryIntegrationBundle or None if no valid memory spaces
    """
    if not config or not config.memories:
        return None

    from derisk.component import ComponentType
    # TODO: rewire to new knowledge module (Task #9)
    try:
        from derisk_serve.rag.storage_manager import StorageManager
    except ImportError:
        logger.warning(
            "StorageManager unavailable (old rag module removed); "
            "skipping memory integration bundle."
        )
        return None

    try:
        storage_manager: StorageManager = system_app.get_component(
            ComponentType.RAG_STORAGE_MANAGER, StorageManager
        )
    except Exception as e:
        logger.warning(f"StorageManager not available: {e}")
        return None

    memory_stores: Dict[str, MemoryStoreBase] = {}
    processors: Dict[str, MemoryProcessor] = {}
    strategies: Dict[str, MemorySpaceStrategy] = {}

    for memory_item in config.memories:
        memory_id = memory_item.get("memory_id")
        if not memory_id:
            continue

        try:
            memory_store = storage_manager.create_memory_store(memory_id)
            if memory_store:
                memory_stores[memory_id] = memory_store
                logger.info(f"[MemoryBundle] Connected store: {memory_id}")
        except Exception as e:
            logger.warning(f"Failed to create store for {memory_id}: {e}")

        # Create processor for this space
        if processor_factory:
            try:
                processors[memory_id] = processor_factory(memory_id)
                logger.info(f"[MemoryBundle] Created processor for {memory_id}")
            except Exception as e:
                logger.warning(f"Failed to create processor for {memory_id}: {e}")

        # Create strategy for this space
        if strategy_overrides and memory_id in strategy_overrides:
            strategies[memory_id] = strategy_overrides[memory_id]
        else:
            strategies[memory_id] = MemorySpaceStrategy(
                space_id=memory_id,
                auto_extraction=config.auto_memory,
                kg_extraction=config.enable_kg,
            )

    if not memory_stores:
        return None

    recall_tracker = RecallTracker()
    hybrid_search = HybridSearchEngine()
    lifecycle_hooks = DefaultLifecycleHooks()
    snapshot_manager = FrozenSnapshotManager()
    promotion_engine = MemoryPromotionEngine(
        recall_tracker=recall_tracker,
        promotion_threshold=0.5,
        max_promotions_per_sweep=10,
    )

    manager = LongTermMemoryManager(
        config=config,
        memory_stores=memory_stores,
        processors=processors,
        strategies=strategies,
        recall_tracker=recall_tracker,
        hybrid_search_engine=hybrid_search,
        lifecycle_hooks=lifecycle_hooks,
        snapshot_manager=snapshot_manager,
        promotion_engine=promotion_engine,
    )

    return MemoryIntegrationBundle(
        config=config,
        manager=manager,
        processors=processors,
        strategies=strategies,
        recall_tracker=recall_tracker,
        hybrid_search=hybrid_search,
        lifecycle_hooks=lifecycle_hooks,
        snapshot_manager=snapshot_manager,
        promotion_engine=promotion_engine,
    )


__all__ = [
    "LongTermMemoryConfig",
    "LongTermMemoryManager",
    "MemoryIntegrationBundle",
    "create_long_term_memory_manager",
    "create_memory_integration_bundle",
]
