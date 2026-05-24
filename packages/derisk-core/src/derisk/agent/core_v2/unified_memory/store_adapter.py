"""Adapter: Bridge MemoryStoreBase to V2 UnifiedMemoryInterface.

This adapter allows the V2 UnifiedMemoryInterface to use the existing
vector-store-backed MemoryStoreBase (MemPalace, etc.) as its storage layer.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from uuid import uuid4

from derisk.agent.core_v2.unified_memory.base import (
    MemoryItem,
    MemoryType,
    SearchOptions,
    UnifiedMemoryInterface,
    MemoryConsolidationResult,
)
from derisk.storage.memory.base import MemoryStoreBase, MemoryEntry

logger = logging.getLogger(__name__)


class MemoryStoreAdapter(UnifiedMemoryInterface):
    """Bridge MemoryStoreBase to UnifiedMemoryInterface.

    Maps V2 UnifiedMemoryInterface operations to MemoryStoreBase calls:
    - write()     -> store.awrite_memory()
    - read()      -> store.asearch_memory()
    - search_similar() -> store.asearch_memory() with filters
    - update()    -> store.aupdate_memory() (if available)
    - delete()    -> store.adelete_memory() (if available)
    """

    def __init__(
        self,
        store: MemoryStoreBase,
        wing: str = "default",
        hybrid_search: Optional[Any] = None,  # HybridSearchEngine
    ):
        self._store = store
        self._wing = wing
        self._hybrid_search = hybrid_search  # Optional HybridSearchEngine

    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True,
    ) -> str:
        """Write a memory item via MemoryStoreBase."""
        room = memory_type.value
        meta = metadata or {}
        meta["memory_type"] = memory_type.value

        entry = await self._store.awrite_memory(
            content=content,
            wing=self._wing,
            room=room,
            metadata=meta,
        )
        return entry.id or str(uuid4())

    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        """Read memory items matching query."""
        options = options or SearchOptions()
        top_k = options.top_k

        entries = await self._store.asearch_memory(
            query=query,
            top_k=top_k,
            wing=self._wing,
        )
        return self._entries_to_items(entries)

    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """Search using HybridSearchEngine if available, fallback to store."""
        if self._hybrid_search:
            from derisk.storage.memory.hybrid_search import HybridSearchConfig

            config = HybridSearchConfig(
                vector_weight=0.6,
                keyword_weight=0.4,
                temporal_decay_enabled=True,
                temporal_decay_halflife=30,
                mmr_enabled=True,
                mmr_diversity=0.5,
            )

            results = await self._hybrid_search.search(
                query=query,
                store=self._store,
                top_k=top_k,
                config=config,
            )
            # SearchResult -> MemoryItem
            items = []
            for r in results:
                items.append(
                    MemoryItem(
                        id=r.id,
                        content=r.content,
                        memory_type=MemoryType.SEMANTIC,
                        importance=r.score,
                        metadata=r.metadata,
                        source="hybrid_search",
                    )
                )
            return items

        # Fallback: direct store search
        entries = await self._store.asearch_memory(
            query=query,
            top_k=top_k,
            wing=self._wing,
        )
        return self._entries_to_items(entries)

    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """Get a memory item by ID (not directly supported by store)."""
        logger.warning("get_by_id not supported by MemoryStoreBase")
        return None

    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a memory item if store supports it."""
        if hasattr(self._store, "aupdate_memory"):
            try:
                await self._store.aupdate_memory(
                    memory_id=memory_id,
                    content=content,
                    metadata=metadata,
                )
                return True
            except Exception as e:
                logger.warning(f"Failed to update memory: {e}")
        return False

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory item if store supports it."""
        if hasattr(self._store, "adelete_memory"):
            try:
                return await self._store.adelete_memory(memory_id)
            except Exception as e:
                logger.warning(f"Failed to delete memory: {e}")
        return False

    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> MemoryConsolidationResult:
        """Consolidate memories — delegate to MemoryPromotionEngine if available."""
        # This is handled externally by MemoryPromotionEngine
        return MemoryConsolidationResult(
            success=False,
            source_type=source_type,
            target_type=target_type,
            items_consolidated=0,
            error="Consolidation not supported via adapter",
        )

    async def export(
        self,
        format: str = "markdown",
        memory_types: Optional[List[MemoryType]] = None,
    ) -> str:
        """Export memories — not directly supported."""
        logger.warning("Export not supported via adapter")
        return ""

    async def import_from_file(
        self,
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED,
    ) -> int:
        """Import memories from file — delegate to store.import_documents if available."""
        if hasattr(self._store, "import_documents"):
            result = self._store.import_documents(
                source_path=file_path,
                wing=self._wing,
            )
            return result.get("entries_created", 0)
        return 0

    async def clear(
        self,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> int:
        """Clear memories — not directly supported."""
        logger.warning("Clear not supported via adapter")
        return 0

    def _entries_to_items(self, entries: List[MemoryEntry]) -> List[MemoryItem]:
        """Convert MemoryEntry list to MemoryItem list."""
        items = []
        for e in entries:
            items.append(
                MemoryItem(
                    id=e.id or str(uuid4()),
                    content=e.content,
                    memory_type=MemoryType.SEMANTIC,
                    importance=e.score or 0.5,
                    metadata=e.metadata or {},
                    source="memory_store",
                )
            )
        return items
