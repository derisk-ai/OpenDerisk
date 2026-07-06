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
        # 用 metadata.user_name 替换字面量 "用户:"，让 raw 记忆文件能归属到实际
        # 提问人。没拿到 user_name 时退回 "用户"。
        user_label = (metadata or {}).get("user_name") or "用户"
        conversation = f"{user_label}: {user_message.strip()}\n助手: {agent_response.strip()}"
        # terminate 时 _attach_delivery_files 暂存的交付文件列表。追加到
        # 同一 verbat content（不另开文件），让"最终结论 + 交付物"落在同一
        # 条原始记忆里。文件 bytes 仍只存 OSS，这里只写元数据 + 路径。
        delivery_files = (metadata or {}).get("delivery_files")
        if delivery_files:
            delivery_section = self._format_delivery_section(delivery_files, user_label)
            conversation = conversation + "\n" + delivery_section
        conv_id = (metadata or {}).get("conv_id")
        round_no = (metadata or {}).get("round")
        logger.info(
            "[LongTermMemory] write_turn_lightweight start conv=%s round=%s "
            "spaces=%d user_len=%d ai_len=%d delivery_files=%s",
            conv_id,
            round_no,
            len(self._memory_stores),
            len(user_message or ""),
            len(agent_response or ""),
            len(delivery_files) if delivery_files else 0,
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
                # KnowledgeVaultMemoryStore short-circuit for tier1:
                # route the raw conversation fragment directly to L0
                # Verbat (extract_mode=convo), bypassing LLM extraction.
                # The LLM-driven consolidation is deferred to tier2
                # reflect, which reads these verbats back via search.
                if (
                    metadata or {}).get("tier") == 1 and _is_knowledge_vault_store(store):
                    conv = f"{user_label}: {user_message.strip()}\n助手: {agent_response.strip()}"
                    if delivery_files:
                        conv = conv + "\n" + self._format_delivery_section(
                            delivery_files, user_label
                        )
                    await store.awrite_memory(
                        content=conv,
                        wing=self._config.wing,
                        room="convo",
                        metadata=metadata,
                    )
                    results[space_id] = True
                    logger.info(
                        "[LongTermMemory] space=%s tier1 wrote L0 Verbat (kv path)",
                        space_id,
                    )
                    continue

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

    @staticmethod
    def _format_delivery_section(
        delivery_files: List[Dict[str, Any]],
        user_label: str,
    ) -> str:
        """把交付文件列表格式化成 verbat content 的一个 section。

        - 文件 bytes 不进 vault（单一信源：OSS）
        - 这里只写元数据 + OSS 路径，让 LLM 检索时能"看到"交付物的存在
        - FTS 会索引这段，所以 file_name / description / oss 路径都可搜
        """
        lines = [
            f"[交付] {user_label} 在本轮交付了 {len(delivery_files)} 个文件:"
        ]
        for i, f in enumerate(delivery_files, 1):
            if not isinstance(f, dict):
                continue
            name = f.get("file_name") or f.get("file_id") or "unknown"
            mime = f.get("mime_type") or ""
            size = f.get("file_size") or 0
            oss = f.get("oss_url") or f.get("object_path") or ""
            desc = (f.get("description") or "").strip()
            line = f"{i}. {name} ({mime}, {size} bytes)"
            if desc:
                line += f" — {desc}"
            lines.append(line)
            if oss:
                lines.append(f"   - OSS: {oss}")
        return "\n".join(lines)

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
                now_iso = datetime.utcnow().isoformat()
                for mem in consolidation.new_memories:
                    if _is_knowledge_vault_store(store):
                        # tier2 reflect -> L1 Document (type=memory|insight)
                        # + derived-from edges back to source verbats.
                        doc_type = "insight" if mem.room == "insight" else "memory"
                        doc_path = f"wiki/{doc_type}s/{now_iso.replace(':', '-')}-{space_id[:8]}-{written}.md"
                        src_v_ids = (mem.metadata or {}).get("source_verbat_ids", []) or []
                        frontmatter = {
                            "type": doc_type,
                            "title": (mem.content[:40] + "...") if len(mem.content) > 40 else mem.content,
                            "created": now_iso,
                            "updated": now_iso,
                            "source_conversation": (metadata or {}).get("conv_id"),
                            "author": (metadata or {}).get("user_name"),
                            "user_id": (metadata or {}).get("user_id"),
                            "source_verbat_ids": src_v_ids,
                        }
                        mem_meta = dict(mem.metadata or {})
                        mem_meta["tier"] = 2
                        mem_meta["doc_path"] = doc_path
                        mem_meta["frontmatter"] = frontmatter
                        entry = await store.awrite_memory(
                            content=mem.content,
                            wing=self._config.wing,
                            room=mem.room,
                            metadata=mem_meta,
                        )
                        doc_id = entry.id if hasattr(entry, "id") else str(entry)
                        # derived-from edges back to source verbats (if tracked)
                        for v_id in (mem.metadata or {}).get("source_verbat_ids", []):
                            try:
                                await store.akg_add(
                                    subject=f"doc:{doc_path}",
                                    predicate="derived-from",
                                    object_=f"verbat:{v_id}",
                                )
                            except Exception as e:
                                logger.warning(
                                    f"[Tier2] derived-from edge failed: {e}"
                                )
                    else:
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
                # 会话结束轻量版：只跑 promotion + snapshot。
                # L1 doc 的 umbrella 合并 + 三信号分类 + tar.gz 回滚
                # 已搬到 idle curator（curate_space + cron job），不再在此处执行。
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

    @staticmethod
    async def curate_space(
        space_slug: str,
        system_app: Any,
        llm_client: Any = None,
    ) -> Dict[str, Any]:
        """Idle curator entry (cron-triggered): full L1 consolidation.

        不依赖 bundle —— 直接从 KnowledgeService 解析 vault，列举全部 L1
        memory/insight docs，做 umbrella 合并 + 三信号分类 + tar.gz 回滚。

        流程参考 hermes-agent curator.py：
        1. tar.gz snapshot space dir（保留最近 5 份）
        2. LLM 聚类：把全部 L1 doc 摘要喂给 LLM，输出 merge groups
        3. 对每个 merge group 调 curate_merge（创建 umbrella doc +
           merged-into/supersedes 边 + delete source docs）
        4. 写 REPORT.md

        Args:
            space_slug: llm-wiki Space slug（如 memory-canvas-agent）
            system_app: SystemApp，用于解析 KnowledgeService
            llm_client: 可选 LLMClient；None 时尝试从 default LLM 取

        Returns:
            摘要 dict：{backed_up, merge_groups, merged_docs, report_path}
        """
        import os
        import shutil
        from derisk.storage.memory.llm_processor import LLMMemoryProcessor

        report: Dict[str, Any] = {
            "space_slug": space_slug,
            "backed_up": False,
            "merge_groups": [],
            "merged_docs": 0,
            "report_path": None,
        }

        # 1. 解析 vault
        try:
            from derisk_serve.knowledge.service.service import (
                Service as KnowledgeService,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[curate_space] KnowledgeService import failed: %s", e)
            return report
        try:
            ks = KnowledgeService.get_instance(system_app)
            vault = await ks.get_vault(space_slug)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[curate_space] resolve vault slug=%s failed: %s", space_slug, e
            )
            return report

        # 2. 列举全部 L1 memory/insight docs
        l1_docs: List[Any] = []
        for doc_type in ("memory", "insight"):
            try:
                docs = await vault.doc_list(type=doc_type, limit=100)
            except Exception as e:  # noqa: BLE001
                logger.debug("[curate_space] doc_list(%s) failed: %s", doc_type, e)
                docs = []
            l1_docs.extend(docs or [])
        if not l1_docs:
            logger.info("[curate_space] no L1 docs for slug=%s; skip", space_slug)
            return report

        # 3. tar.gz snapshot
        space_root = None
        try:
            space_root = getattr(vault, "_root", None) or getattr(vault, "root", None)
        except Exception:  # noqa: BLE001
            pass
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup_dir = None
        if space_root and os.path.isdir(space_root):
            backup_dir = os.path.join(space_root, ".backups")
            os.makedirs(backup_dir, exist_ok=True)
            try:
                shutil.make_archive(
                    os.path.join(backup_dir, f"curator-{ts}"),
                    "gztar",
                    root_dir=space_root,
                )
                report["backed_up"] = True
                # 保留最近 5 份
                backups = sorted(
                    [f for f in os.listdir(backup_dir) if f.startswith("curator-")],
                    reverse=True,
                )
                for old in backups[5:]:
                    try:
                        os.remove(os.path.join(backup_dir, old))
                    except OSError:
                        pass
            except Exception as e:  # noqa: BLE001
                logger.warning("[curate_space] backup failed: %s", e)

        # 4. LLM 聚类
        processor = None
        if llm_client is not None:
            try:
                processor = LLMMemoryProcessor(llm_client=llm_client)
            except Exception as e:  # noqa: BLE001
                logger.warning("[curate_space] processor init failed: %s", e)

        merge_groups: List[List[str]] = []  # 每组是 doc path 列表
        if processor is not None:
            try:
                merge_groups = await _cluster_l1_docs(processor, vault, l1_docs)
            except Exception as e:  # noqa: BLE001
                logger.warning("[curate_space] cluster failed: %s", e)
        else:
            # 无 LLM：退化为按 type 分组（同 type 全合并）—— 至少能跑
            by_type: Dict[str, List[str]] = {}
            for d in l1_docs:
                p = d.path or ""
                t = d.type or "memory"
                by_type.setdefault(t, []).append(p)
            merge_groups = [paths for paths in by_type.values() if len(paths) > 1]

        report["merge_groups"] = merge_groups

        # 5. 执行合并 —— 用 KnowledgeVaultMemoryStore.curate_merge
        #    构造一个临时 store 实例（仅用 vault 引用，不依赖 bundle）
        merged_total = 0
        try:
            from derisk_ext.storage.memory.knowledge_vault_store import (
                KnowledgeVaultMemoryConfig,
                KnowledgeVaultMemoryStore,
            )
            tmp_store = KnowledgeVaultMemoryStore(
                config=KnowledgeVaultMemoryConfig(space_slug=space_slug),
                vault=vault,
                system_app=system_app,
            )
            now_iso = datetime.utcnow().isoformat()
            for idx, paths in enumerate(merge_groups):
                if not paths or len(paths) < 2:
                    continue
                merged_md = await _merge_doc_bodies(vault, paths)
                if not merged_md:
                    continue
                target_path = (
                    f"wiki/memories/curated-{ts}-{idx}.md"
                )
                frontmatter = {
                    "type": "memory",
                    "title": f"Curated merge {idx} ({len(paths)} docs) {ts}",
                    "created": now_iso,
                    "updated": now_iso,
                    "merged_from": paths,
                    "curator": "idle-cron",
                }
                try:
                    await tmp_store.curate_merge(
                        source_paths=paths,
                        target_path=target_path,
                        merged_content=merged_md,
                        frontmatter=frontmatter,
                    )
                    merged_total += len(paths)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "[curate_space] curate_merge group %d failed: %s", idx, e
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("[curate_space] merge phase failed: %s", e)
        report["merged_docs"] = merged_total

        # 6. REPORT.md
        report_dir = None
        if space_root:
            report_dir = os.path.join(space_root, ".curator", ts)
            try:
                os.makedirs(report_dir, exist_ok=True)
                lines = [
                    "# Memory Curator Report",
                    f"- space: {space_slug}",
                    f"- timestamp: {ts}",
                    f"- backed_up: {report['backed_up']}",
                    f"- l1_docs_before: {len(l1_docs)}",
                    f"- merge_groups: {len(merge_groups)}",
                    f"- merged_docs: {merged_total}",
                    "",
                    "## Merge Groups",
                ]
                for i, g in enumerate(merge_groups):
                    lines.append(f"### Group {i} ({len(g)} docs)")
                    for p in g:
                        lines.append(f"- {p}")
                    lines.append("")
                with open(os.path.join(report_dir, "REPORT.md"), "w") as f:
                    f.write("\n".join(lines))
                report["report_path"] = os.path.join(report_dir, "REPORT.md")
            except Exception as e:  # noqa: BLE001
                logger.warning("[curate_space] report write failed: %s", e)

        logger.info(
            "[curate_space] done slug=%s merged=%d groups=%d",
            space_slug, merged_total, len(merge_groups),
        )
        return report

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

    async def _summarize_for_curate(
        self,
        candidates: List[MemoryEntry],
        history_text: str,
    ) -> Optional[str]:
        """Produce merged markdown from tier3 candidate memories.

        Joins the top candidate snippets into a single consolidated
        markdown page. If a processor is available, we could LLM-summarize;
        for now we concatenate with a header — the L2 edges created by
        curate_merge preserve the provenance.
        """
        if not candidates:
            return None
        lines = ["# Curated Memory Merge\n"]
        lines.append(f"Consolidated from {len(candidates)} entries.\n")
        for i, e in enumerate(candidates, 1):
            layer = e.metadata.get("layer", "?")
            path = e.metadata.get("path") or e.metadata.get("verbat_id") or ""
            lines.append(f"## Entry {i} [{layer}] {path}\n")
            lines.append(e.content.strip() or "")
            lines.append("")
        return "\n".join(lines)

    async def _summarize_for_paths(
        self,
        paths: List[str],
        history_text: str,
    ) -> Optional[str]:
        """Produce merged markdown by reading L1 docs at the given paths.

        Reads each path through the store's vault and concatenates the
        bodies under a header. Provenance is preserved by the merged-into /
        supersedes edges created in `curate_merge`.
        """
        if not paths:
            return None
        lines = ["# Curated Memory Merge\n"]
        lines.append(f"Consolidated from {len(paths)} documents.\n")
        for i, p in enumerate(paths, 1):
            doc = None
            try:
                store = self._get_primary_store()[1]
                vault = getattr(store, "vault", None) if store else None
                if vault is not None:
                    doc = await vault.doc_read(p)
            except Exception as e:  # noqa: BLE001
                logger.debug("[Tier3] doc_read %s failed: %s", p, e)
            title = getattr(doc, "title", p) if doc else p
            body = getattr(doc, "content", "") if doc else ""
            lines.append(f"## Entry {i} {title}\n")
            lines.append(f"_path: {p}_\n")
            lines.append((body or "").strip())
            lines.append("")
        return "\n".join(lines)


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


def _is_knowledge_vault_store(store: Any) -> bool:
    """Duck-type check for KnowledgeVaultMemoryStore.

    Avoids a hard import dependency on derisk_ext from derisk_core (which
    would invert the package layering). We check for the `write_doc`
    and `curate_merge` async helpers that only the knowledge-vault
    adapter exposes.
    """
    return (
        hasattr(store, "write_doc")
        and hasattr(store, "curate_merge")
        and hasattr(store, "vault")
    )


async def _cluster_l1_docs(
    processor: Any, vault: Any, docs: List[Any]
) -> List[List[str]]:
    """LLM 聚类：把全部 L1 doc 摘要喂给 LLM，输出 merge groups。

    用 consolidate_memories 的 LLM 调用通道（复用 _call_llm），但 prompt
    换成聚类专用。返回 [[path1, path2], [path3, path4], ...]。

    无 LLM 或解析失败时返回空列表（调用方退化到按 type 分组）。
    """
    import json as _json

    # 拼摘要：每条 doc 取 title + path + 前 150 字
    summaries: List[Dict[str, str]] = []
    for d in docs:
        title = getattr(d, "title", "") or getattr(d, "path", "")
        path = getattr(d, "path", "") or ""
        body_snippet = ""
        try:
            full = await vault.doc_read(path)
            body_snippet = (getattr(full, "content", "") or "")[:150]
        except Exception:  # noqa: BLE001
            pass
        summaries.append({
            "path": path,
            "title": title,
            "snippet": body_snippet,
        })

    prompt = (
        "你是记忆整理器。下面是空间里全部 L1 记忆文档的摘要。请把语义相关的"
        "文档分到同一组（合并成一个 umbrella 文档），每组至少 2 个文档，"
        "孤立的文档不分组。\n\n"
        f"文档列表（JSON）：\n{_json.dumps(summaries, ensure_ascii=False)}\n\n"
        "请以 JSON 输出，格式：\n"
        '{{"groups": [[{{"path": "doc1"}}, {{"path": "doc2"}}], ...]}}\n'
        "如果没有任何文档应该合并，返回 {{\"groups\": []}}。"
    )
    try:
        text = await processor._call_llm(prompt)  # noqa: SLF001
        parsed = _parse_json_lenient_cluster(text)
        groups: List[List[str]] = []
        for g in parsed.get("groups", []):
            paths = [item.get("path") for item in g if isinstance(item, dict)]
            paths = [p for p in paths if p]
            if len(paths) >= 2:
                groups.append(paths)
        return groups
    except Exception as e:  # noqa: BLE001
        logger.warning("[_cluster_l1_docs] LLM cluster failed: %s", e)
        return []


def _parse_json_lenient_cluster(text: str) -> Dict[str, Any]:
    """宽松 JSON 解析：去 markdown fence，尝试直接 parse，失败则抓 {...} span。"""
    import json as _json
    import re as _re

    if not text:
        return {}
    t = text.strip()
    # 去 ```json ... ``` fence
    fence = _re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if fence:
        t = fence.group(1).strip()
    try:
        return _json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    # 抓最外层 {...}
    m = _re.search(r"\{[\s\S]*\}", t)
    if m:
        try:
            return _json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return {}
    return {}


async def _merge_doc_bodies(vault: Any, paths: List[str]) -> Optional[str]:
    """读取多个 L1 doc，拼成 merged markdown body。"""
    if not paths:
        return None
    lines = ["# Curated Memory Merge\n"]
    lines.append(f"Consolidated from {len(paths)} documents.\n")
    for i, p in enumerate(paths, 1):
        try:
            doc = await vault.doc_read(p)
        except Exception as e:  # noqa: BLE001
            logger.debug("[_merge_doc_bodies] doc_read %s failed: %s", p, e)
            doc = None
        title = getattr(doc, "title", p) if doc else p
        body = getattr(doc, "content", "") if doc else ""
        lines.append(f"## Entry {i} {title}\n")
        lines.append(f"_path: {p}_\n")
        lines.append((body or "").strip())
        lines.append("")
    return "\n".join(lines)


