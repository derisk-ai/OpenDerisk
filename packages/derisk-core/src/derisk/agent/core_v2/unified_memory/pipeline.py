"""Memory pipeline operator for V2 agent execution.

Wires the full v2 memory architecture into the agent generate flow:
- Before reasoning: retrieve memories via HybridSearchEngine, capture snapshot
- During turns: lifecycle hooks on turn start/end
- After completion: auto-write memories via MemoryProcessor
- On session end: run promotion engine for three-phase dreaming
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryPipeline:
    """Memory pipeline that integrates all v2 memory components into agent execution.

    This is the single entry point for memory operations during agent execution.
    It coordinates:
    1. Pre-reasoning memory retrieval (HybridSearch + Snapshot)
    2. Turn-level lifecycle hooks
    3. Post-reasoning auto-write (MemoryProcessor per space)
    4. Session-end promotion (three-phase dreaming)

    Usage:
        pipeline = MemoryPipeline(bundle)
        await pipeline.on_turn_start(turn, user_message)
        memories = await pipeline.retrieve(query)
        await pipeline.on_turn_end(turn, user_message, assistant_response)
        await pipeline.on_session_end()
    """

    def __init__(self, bundle: Any):  # MemoryIntegrationBundle
        self._bundle = bundle
        self._turn_count = 0
        self._session_active = False

    async def on_session_start(self, query: str) -> str:
        """Called at session start. Captures frozen snapshots and retrieves initial memories.

        Returns:
            Formatted memory context for system prompt injection
        """
        self._session_active = True
        self._turn_count = 0

        # Retrieve memories and capture snapshot
        memory_context = await self.retrieve(query)

        # Notify lifecycle hooks
        await self._bundle.lifecycle_hooks.on_session_switch(
            new_session_id="current",
            reset=True,
        )

        return memory_context

    async def retrieve(self, query: str, top_k: Optional[int] = None) -> str:
        """Retrieve relevant memories with HybridSearchEngine.

        Returns:
            Formatted memory text for context injection
        """
        return await self._bundle.manager.retrieve_relevant_memories(
            query=query,
            top_k=top_k,
            use_hybrid_search=True,
        )

    async def on_turn_start(self, turn_number: int, user_message: str) -> None:
        """Called before each agent turn."""
        self._turn_count = turn_number
        await self._bundle.lifecycle_hooks.on_turn_start(
            turn_number=turn_number,
            user_message=user_message,
        )

    async def on_turn_end(
        self,
        turn_number: int,
        user_message: str,
        assistant_response: str,
    ) -> Dict[str, bool]:
        """Called after each agent turn. Triggers auto-write via MemoryProcessor."""
        results = await self._bundle.manager.write_memory_auto(
            user_message=user_message,
            agent_response=assistant_response,
        )

        # Notify lifecycle hooks
        await self._bundle.lifecycle_hooks.on_turn_end(
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=assistant_response,
        )

        return results

    async def on_session_end(self, history: Optional[List[Dict[str, str]]] = None) -> Dict:
        """Called when session ends. Runs promotion engine and final cleanup.

        Returns:
            Promotion results per space
        """
        results = {}

        # Notify lifecycle hooks
        if history:
            await self._bundle.lifecycle_hooks.on_session_end(history)

        # Run three-phase promotion for each space
        for space_id, store in self._bundle.manager.memory_stores.items():
            try:
                promotion_result = await self._bundle.promotion_engine.run_promotion_sweep(
                    space_id=space_id,
                    store=store,
                )
                results[space_id] = {
                    "promoted": len(promotion_result.promoted),
                    "error": promotion_result.error,
                }
                logger.info(
                    f"[MemoryPipeline] Promotion for {space_id}: "
                    f"{len(promotion_result.promoted)} memories promoted"
                )
            except Exception as e:
                logger.warning(f"[MemoryPipeline] Promotion failed for {space_id}: {e}")
                results[space_id] = {"promoted": 0, "error": str(e)}

        # Refresh snapshots for next session
        self._bundle.snapshot_manager.refresh_all()
        self._session_active = False

        return results

    async def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Called before context compression. Extracts insights from messages."""
        return await self._bundle.lifecycle_hooks.on_pre_compress(messages)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory statistics."""
        stats = {
            "session_active": self._session_active,
            "turn_count": self._turn_count,
            "spaces": {},
        }
        for space_id, store in self._bundle.manager.memory_stores.items():
            space_stats = {"store_type": type(store).__name__}
            try:
                if hasattr(store, 'get_status'):
                    space_stats["status"] = store.get_status()
            except Exception:
                pass
            stats["spaces"][space_id] = space_stats
        return stats

    async def run_promotion(self, space_id: str) -> Any:
        """Manually trigger promotion for a specific space."""
        store = self._bundle.manager.memory_stores.get(space_id)
        if not store:
            logger.warning(f"[MemoryPipeline] No store for space {space_id}")
            return None
        return await self._bundle.promotion_engine.run_promotion_sweep(
            space_id=space_id,
            store=store,
        )
