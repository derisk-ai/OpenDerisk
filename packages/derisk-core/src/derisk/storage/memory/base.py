"""Memory store base class.

Defines the abstract interface for pluggable memory storage providers.
Any third-party memory system (custom, etc.) only needs to implement
MemoryStoreBase to integrate with OpenDerisk's knowledge and agent
pipeline.

Architecture:
    IndexStoreBase (core storage interface)
        └── MemoryStoreBase (adds memory-specific ops)
                ├── SimpleSQLiteMemoryStore (default)
                └── ... (other providers)
"""

import logging
from abc import ABC, abstractmethod
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from derisk.core import Chunk
from derisk.storage.base import IndexStoreBase, IndexStoreConfig
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util import RegisterParameters
from derisk.util.executor_utils import blocking_func_to_async

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry returned by the memory store."""

    id: str
    content: str
    wing: str
    room: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None
    created_at: Optional[str] = None


@dataclass
class KGTriple:
    """A knowledge graph triple (subject-predicate-object)."""

    subject: str
    predicate: str
    object_: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None


@dataclass
class MemoryStoreConfig(IndexStoreConfig, RegisterParameters):
    """Base config for memory stores.

    Subclass this and set ``__type__`` to register a new provider.
    The StorageManager will auto-discover registered providers via
    ``__subclasses__()``.

    Example::

        @dataclass
        class MyMemoryConfig(MemoryStoreConfig):
            __type__ = "my_memory"
            db_url: str = "sqlite:///memory.db"

            def create_store(self, **kwargs) -> "MyMemoryStore":
                return MyMemoryStore(config=self, **kwargs)
    """

    __cfg_type__ = "memory_store"

    def create_store(self, **kwargs) -> "MemoryStoreBase":
        """Create a new memory store from this config."""
        raise NotImplementedError(
            "Current memory store config does not support create_store"
        )


class MemoryStoreBase(IndexStoreBase, ABC):
    """Abstract base for memory storage providers.

    Extends IndexStoreBase with memory-specific operations:

    - **Hierarchical organisation** — wing / room structure for multi-tenant
      or multi-topic memory isolation.
    - **Knowledge graph** — entity-relationship triples with temporal
      validity (``kg_add``, ``kg_query``).
    - **Bulk import** — ingest external documents / files into the memory
      store (``import_documents``).
    - **Management** — list wings/rooms, get status.

    Implementors must provide:
    1. All 6 abstract methods from ``IndexStoreBase``
       (load_document, aload_document, similar_search_with_scores,
        delete_by_ids, truncate, delete_vector_name, get_config)
    2. All abstract methods defined here.

    The concrete helper methods on ``IndexStoreBase``
    (similar_search, load_document_with_limit, async wrappers, etc.)
    are inherited automatically.
    """

    def __init__(self, executor: Optional[Executor] = None):
        super().__init__(executor)

    # ------------------------------------------------------------------
    # Abstract: must be implemented by every provider
    # ------------------------------------------------------------------

    @abstractmethod
    def get_config(self) -> MemoryStoreConfig:
        """Return the config that created this store."""

    # --- Memory write / read ---

    @abstractmethod
    def write_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Write a single memory entry.

        Args:
            content: The verbatim text to store.
            wing: Top-level grouping (e.g. app_code, project name).
            room: Topic within the wing (e.g. "backend", "meetings").
            metadata: Optional extra metadata.

        Returns:
            The created MemoryEntry (with generated id).
        """

    @abstractmethod
    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        """Semantic search over memories.

        Args:
            query: The search query text.
            top_k: Maximum number of results.
            wing: Optional filter by wing.
            room: Optional filter by room.
            max_distance: Maximum vector distance threshold.

        Returns:
            List of matching MemoryEntry objects, ordered by relevance.
        """

    @abstractmethod
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a single memory entry by id.

        Returns:
            True if deleted, False if not found.
        """

    # --- Knowledge graph ---

    @abstractmethod
    def kg_add(
        self,
        subject: str,
        predicate: str,
        object_: str,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
    ) -> str:
        """Add a knowledge graph triple.

        Returns:
            The triple id.
        """

    @abstractmethod
    def kg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        """Query knowledge graph triples for an entity.

        Args:
            entity: The entity name to query.
            as_of: Optional ISO date string for temporal filtering.

        Returns:
            List of KGTriple matching the entity.
        """

    @abstractmethod
    def kg_invalidate(
        self,
        triple_id: str,
    ) -> bool:
        """Invalidate (soft-delete) a knowledge graph triple.

        Returns:
            True if invalidated, False if not found.
        """

    # --- Bulk import ---

    @abstractmethod
    def import_documents(
        self,
        source_path: str,
        wing: Optional[str] = None,
    ) -> Dict[str, int]:
        """Bulk import documents / files into the memory store.

        Args:
            source_path: Path to a directory or file to import.
            wing: Optional wing name override.

        Returns:
            Dict with import statistics, e.g.
            {"files_processed": 42, "entries_created": 156}
        """

    # --- Management ---

    @abstractmethod
    def list_wings(self) -> List[Dict[str, Any]]:
        """List all wings with entry counts.

        Returns:
            List of dicts, e.g. [{"name": "my_app", "count": 42}]
        """

    @abstractmethod
    def list_rooms(self, wing: str) -> List[Dict[str, Any]]:
        """List rooms within a wing with entry counts.

        Returns:
            List of dicts, e.g. [{"name": "backend", "count": 15}]
        """

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get overall memory store status.

        Returns:
            Dict with status info, e.g.
            {"total_entries": 200, "wings": 3, "rooms": 10, "kg_triples": 50}
        """

    # ------------------------------------------------------------------
    # Async wrappers (convenience — override for native async)
    # ------------------------------------------------------------------

    async def awrite_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Async version of write_memory."""
        return await blocking_func_to_async(
            self._executor, self.write_memory, content, wing, room, metadata
        )

    async def asearch_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        """Async version of search_memory."""
        return await blocking_func_to_async(
            self._executor, self.search_memory, query, top_k, wing, room, max_distance
        )

    async def adelete_memory(self, memory_id: str) -> bool:
        """Async version of delete_memory."""
        return await blocking_func_to_async(
            self._executor, self.delete_memory, memory_id
        )

    async def akg_add(
        self,
        subject: str,
        predicate: str,
        object_: str,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
    ) -> str:
        """Async version of kg_add."""
        return await blocking_func_to_async(
            self._executor,
            self.kg_add,
            subject,
            predicate,
            object_,
            valid_from,
            valid_to,
            confidence,
            source,
        )

    async def akg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        """Async version of kg_query."""
        return await blocking_func_to_async(
            self._executor, self.kg_query, entity, as_of
        )

    async def aimport_documents(
        self,
        source_path: str,
        wing: Optional[str] = None,
    ) -> Dict[str, int]:
        """Async version of import_documents."""
        return await blocking_func_to_async(
            self._executor, self.import_documents, source_path, wing
        )
