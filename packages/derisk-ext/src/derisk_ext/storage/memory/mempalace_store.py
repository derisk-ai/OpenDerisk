"""MemPalace memory store implementation.

This module provides a concrete implementation of ``MemoryStoreBase`` backed
by the `mempalace <https://github.com/mempalace/mempalace>`_ library.

MemPalace features:
- Verbatim storage with SHA256-based deduplication
- Hierarchical organization: Palace → Wings → Rooms → Drawers
- Knowledge graph with temporal validity (SQLite-backed)
- Bulk document mining with auto-chunking
- Write-ahead log for audit / poisoning detection

Embedding model handling:
- When ``embedding_fn`` is provided by OpenDerisk's ``EmbeddingFactory``,
  the store uses OpenDerisk's centrally configured embedding model for
  vector operations, ensuring consistent vector space across knowledge
  and memory modules.
- When ``embedding_fn`` is ``None``, falls back to mempalace's built-in
  embedding model (all-MiniLM-L6-v2).

To switch to a different provider, implement ``MemoryStoreBase`` and set a
different ``__type__`` on your config — the ``StorageManager`` will pick it
up automatically via subclass discovery.
"""

import hashlib
import logging
import os
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from derisk.core import Chunk, Embeddings
from derisk.storage.memory.base import (
    KGTriple,
    MemoryEntry,
    MemoryStoreBase,
    MemoryStoreConfig,
)
from derisk.storage.vector_store.filters import MetadataFilters

logger = logging.getLogger(__name__)


def _require_mempalace():
    """Lazy-check that mempalace is installed."""
    try:
        import mempalace  # noqa: F401

        return True
    except ImportError:
        raise ImportError(
            "mempalace is required for MemPalaceMemoryStore. "
            "Install it with: pip install mempalace>=3.3.0"
        )


@dataclass
class MemPalaceMemoryConfig(MemoryStoreConfig):
    """Configuration for the MemPalace memory provider.

    Set ``__type__ = "mempalace"`` so StorageManager can auto-discover this
    config via ``MemoryStoreConfig.__subclasses__()``.
    """

    __type__ = "mempalace"

    palace_path: str = field(
        default=os.path.expanduser("~/.mempalace/palace"),
        metadata={"help": "Path to the MemPalace data directory."},
    )
    enable_kg: bool = field(
        default=True,
        metadata={"help": "Enable the knowledge graph (entity triples)."},
    )
    default_wing: Optional[str] = field(
        default=None,
        metadata={"help": "Default wing name (falls back to 'default')."},
    )
    use_builtin_embedding: bool = field(
        default=False,
        metadata={
            "help": (
                "If True, use mempalace's built-in embedding model "
                "(all-MiniLM-L6-v2) instead of the OpenDerisk embedding "
                "factory.  Set to True only if you want the memory store "
                "to be fully self-contained."
            ),
        },
    )

    def create_store(self, **kwargs) -> "MemPalaceMemoryStore":
        """Create a MemPalaceMemoryStore from this config."""
        return MemPalaceMemoryStore(config=self, **kwargs)


class MemPalaceMemoryStore(MemoryStoreBase):
    """MemPalace implementation of the memory store interface.

    Supports two embedding modes:

    1. **Unified mode** (default) — when ``embedding_fn`` is provided by
       ``StorageManager``, the store uses OpenDerisk's configured embedding
       model (e.g. ``text-embedding-v3``, ``bge-m3``).  This ensures the
       same vector space is shared between knowledge and memory retrieval.

    2. **Standalone mode** — when ``embedding_fn`` is ``None`` or
       ``config.use_builtin_embedding`` is ``True``, falls back to
       mempalace's built-in ``all-MiniLM-L6-v2``.  Useful for offline
       or fully self-contained deployments.

    Non-vector features (KG, bulk import, wing/room management) always
    delegate to mempalace regardless of embedding mode.
    """

    def __init__(
        self,
        config: MemPalaceMemoryConfig,
        name: Optional[str] = None,
        embedding_fn: Optional[Embeddings] = None,
        executor: Optional[Executor] = None,
    ):
        super().__init__(executor or ThreadPoolExecutor())
        self._config = config
        self._name = name
        self._palace_path = os.path.expanduser(config.palace_path)
        # Per-space isolation: each memory space (knowledge_id) lives in its
        # own subdirectory so that counts, wings and the unified Chroma
        # collection never collide across spaces.
        if name:
            self._palace_path = os.path.join(
                self._palace_path, name.replace("/", "_")
            )
        os.makedirs(self._palace_path, exist_ok=True)
        self._default_wing = config.default_wing or "default"
        self._enable_kg = config.enable_kg

        _require_mempalace()

        # Decide embedding mode
        if config.use_builtin_embedding or embedding_fn is None:
            self._embedding_fn = None  # will use mempalace built-in
            self._use_derisk_embedding = False
            if embedding_fn is None and not config.use_builtin_embedding:
                logger.info(
                    "No OpenDerisk embedding_fn provided — memory store will "
                    "use mempalace's built-in all-MiniLM-L6-v2 model."
                )
        else:
            self._embedding_fn = embedding_fn
            self._use_derisk_embedding = True
            logger.info(
                "Memory store using OpenDerisk's configured embedding model "
                "for unified vector space with knowledge module."
            )

        # Lazy-init palace / kg / chroma on first use
        self._palace = None
        self._kg = None
        self._chroma_collection = None  # Only used in unified mode

    def _get_palace(self):
        """Builtin-mode backend — NOT available in mempalace>=3.3.

        mempalace 3.3 removed the ``Palace`` class in favour of a
        function-based API. The store therefore only supports *unified*
        mode (an OpenDerisk ``embedding_fn`` is provided and writes/reads
        go through our own Chroma collection). If we reach here it means the
        store was built in builtin mode (no embedding model configured),
        which is unsupported — fail loudly and actionably instead of raising
        an opaque ImportError deep in a write path.
        """
        raise RuntimeError(
            "MemPalace builtin embedding mode is not supported with "
            "mempalace>=3.3. Configure an embedding model "
            "([[models.embeddings]] in your server config) so the memory "
            "store runs in unified mode, or set "
            "[rag.storage.memory] use_builtin_embedding=false and provide "
            "an embedding_factory."
        )

    def _get_kg(self):
        """Lazy-initialize the KnowledgeGraph instance."""
        if self._kg is None and self._enable_kg:
            from mempalace.knowledge_graph import KnowledgeGraph

            self._kg = KnowledgeGraph(path=self._palace_path)
        return self._kg

    def _get_chroma_collection(self):
        """Get or create a ChromaDB collection for unified embedding mode.

        In unified mode we manage our own Chroma collection using
        OpenDerisk's embedding_fn, bypassing mempalace's internal
        ChromaDB to keep vector spaces consistent.
        """
        if self._chroma_collection is not None:
            return self._chroma_collection

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "chromadb is required for unified embedding mode. "
                "Install it with: pip install chromadb>=0.4.22"
            )

        chroma_dir = os.path.join(self._palace_path, "derisk_chroma")
        os.makedirs(chroma_dir, exist_ok=True)

        client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        collection_name = f"memory_{self._name or 'default'}"
        # Sanitise collection name (chroma requires 3-63 chars, alphanumeric)
        collection_name = collection_name.replace("-", "_")[:63]
        if len(collection_name) < 3:
            collection_name = "memory_default"

        self._chroma_collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._chroma_collection

    # ------------------------------------------------------------------
    # IndexStoreBase abstract methods
    # ------------------------------------------------------------------

    def get_config(self) -> MemPalaceMemoryConfig:
        return self._config

    # ------------------------------------------------------------------
    # Unified embedding helpers
    # ------------------------------------------------------------------

    def _gen_drawer_id(self, wing: str, room: str, content: str) -> str:
        """Generate a deterministic drawer id (same scheme as mempalace)."""
        raw = f"{wing}_{room}_{content}"
        return f"drawer_{wing}_{room}_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"

    def _unified_add(self, content: str, wing: str, room: str) -> str:
        """Add content using OpenDerisk embedding + local Chroma."""
        collection = self._get_chroma_collection()
        drawer_id = self._gen_drawer_id(wing, room, content)

        # Dedup check
        existing = collection.get(ids=[drawer_id])
        if existing and existing["ids"]:
            return drawer_id

        embedding = self._embedding_fn.embed_documents([content])[0]
        collection.add(
            ids=[drawer_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{"wing": wing, "room": room, "filed_at": datetime.now().isoformat()}],
        )
        return drawer_id

    def _unified_search(
        self, query: str, topk: int, wing: Optional[str], room: Optional[str],
        max_distance: float,
    ) -> List[Dict[str, Any]]:
        """Search using OpenDerisk embedding + local Chroma."""
        collection = self._get_chroma_collection()
        query_embedding = self._embedding_fn.embed_query(query)

        where_filter = None
        if wing and room:
            where_filter = {"$and": [{"wing": wing}, {"room": room}]}
        elif wing:
            where_filter = {"wing": wing}
        elif room:
            where_filter = {"room": room}

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": topk,
        }
        if where_filter:
            kwargs["where"] = where_filter

        raw = collection.query(**kwargs)

        results = []
        for i, doc_id in enumerate(raw["ids"][0]):
            distance = raw["distances"][0][i] if raw.get("distances") else 0.5
            if distance > max_distance:
                continue
            meta = raw["metadatas"][0][i] if raw.get("metadatas") else {}
            results.append({
                "id": doc_id,
                "content": raw["documents"][0][i] if raw.get("documents") else "",
                "distance": distance,
                "wing": meta.get("wing", ""),
                "room": meta.get("room", ""),
                "filed_at": meta.get("filed_at"),
                "metadata": meta,
            })
        return results

    # ------------------------------------------------------------------
    # IndexStoreBase abstract methods
    # ------------------------------------------------------------------

    def load_document(self, chunks: List[Chunk]) -> List[str]:
        """Load document chunks as memory entries."""
        ids = []
        for chunk in chunks:
            wing = (chunk.metadata or {}).get("wing", self._default_wing)
            room = (chunk.metadata or {}).get("room", "general")
            try:
                if self._use_derisk_embedding:
                    drawer_id = self._unified_add(chunk.content, wing, room)
                else:
                    palace = self._get_palace()
                    result = palace.add_drawer(
                        wing=wing, room=room, content=chunk.content,
                    )
                    drawer_id = result.get("drawer_id", "")
                ids.append(drawer_id)
            except Exception as e:
                logger.warning(f"Failed to load chunk into memory store: {e}")
                ids.append("")
        return ids

    async def aload_document(self, chunks: List[Chunk]) -> List[str]:
        """Async version delegates to thread pool."""
        from derisk.util.executor_utils import blocking_func_to_async

        return await blocking_func_to_async(
            self._executor, self.load_document, chunks
        )

    def similar_search_with_scores(
        self,
        text,
        topk,
        score_threshold: float,
        filters: Optional[MetadataFilters] = None,
        **kwargs,
    ) -> List[Chunk]:
        """Semantic search returning Chunk objects."""
        # Extract wing/room filters
        wing = None
        room = None
        if filters:
            for f in filters.filters:
                if f.key == "wing":
                    wing = f.value
                elif f.key == "room":
                    room = f.value

        max_distance = 1.0 - score_threshold if score_threshold > 0 else 0.5

        try:
            if self._use_derisk_embedding:
                results = self._unified_search(text, topk, wing, room, max_distance)
            else:
                palace = self._get_palace()
                results = palace.search(
                    query=text, max_results=topk,
                    wing=wing, room=room, max_distance=max_distance,
                )
        except Exception as e:
            logger.warning(f"Memory search failed: {e}")
            return []

        chunks = []
        for r in results:
            score = 1.0 - r.get("distance", 0.5)
            if score_threshold and score < score_threshold:
                continue
            chunks.append(
                Chunk(
                    content=r.get("content", ""),
                    score=score,
                    metadata={
                        "wing": r.get("wing", ""),
                        "room": r.get("room", ""),
                        "drawer_id": r.get("id", ""),
                        "source": "mempalace",
                    },
                    chunk_id=r.get("id", ""),
                )
            )
        return chunks

    def delete_by_ids(self, ids: str) -> List[str]:
        """Delete drawers by comma-separated ids."""
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
        if self._use_derisk_embedding:
            try:
                collection = self._get_chroma_collection()
                collection.delete(ids=id_list)
                return id_list
            except Exception as e:
                logger.warning(f"delete_by_ids failed: {e}")
                return []
        palace = self._get_palace()
        deleted = []
        for drawer_id in id_list:
            try:
                palace.delete_drawer(drawer_id=drawer_id)
                deleted.append(drawer_id)
            except Exception as e:
                logger.warning(f"Failed to delete drawer {drawer_id}: {e}")
        return deleted

    def truncate(self) -> List[str]:
        """Truncate is not directly supported — returns empty list."""
        logger.warning(
            "MemPalace does not support bulk truncate. "
            "Delete individual drawers or remove the palace directory."
        )
        return []

    def delete_vector_name(self, index_name: str):
        """Delete the entire palace data (destructive)."""
        import shutil

        palace_path = self._palace_path
        if os.path.exists(palace_path):
            shutil.rmtree(palace_path)
            logger.info(f"Deleted MemPalace data at {palace_path}")
        self._palace = None
        self._kg = None

    def vector_name_exists(self) -> bool:
        """Check if the palace directory exists and has data."""
        return os.path.exists(self._palace_path)

    # ------------------------------------------------------------------
    # MemoryStoreBase abstract methods
    # ------------------------------------------------------------------

    def write_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        if self._use_derisk_embedding:
            drawer_id = self._unified_add(content, wing, room)
        else:
            palace = self._get_palace()
            result = palace.add_drawer(wing=wing, room=room, content=content)
            drawer_id = result.get("drawer_id", "")

        return MemoryEntry(
            id=drawer_id,
            content=content,
            wing=wing,
            room=room,
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
        )

    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        try:
            if self._use_derisk_embedding:
                results = self._unified_search(
                    query, top_k, wing, room, max_distance
                )
            else:
                palace = self._get_palace()
                results = palace.search(
                    query=query, max_results=top_k,
                    wing=wing, room=room, max_distance=max_distance,
                )
        except Exception as e:
            logger.warning(f"search_memory failed: {e}")
            return []

        entries = []
        for r in results:
            entries.append(
                MemoryEntry(
                    id=r.get("id", ""),
                    content=r.get("content", ""),
                    wing=r.get("wing", ""),
                    room=r.get("room", ""),
                    metadata=r.get("metadata", {}),
                    score=1.0 - r.get("distance", 0.5),
                    created_at=r.get("filed_at"),
                )
            )
        return entries

    def delete_memory(self, memory_id: str) -> bool:
        if self._use_derisk_embedding:
            try:
                collection = self._get_chroma_collection()
                collection.delete(ids=[memory_id])
                return True
            except Exception as e:
                logger.warning(f"delete_memory failed: {e}")
                return False
        palace = self._get_palace()
        try:
            palace.delete_drawer(drawer_id=memory_id)
            return True
        except Exception:
            return False

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
        kg = self._get_kg()
        if kg is None:
            raise RuntimeError("Knowledge graph is not enabled in config.")
        result = kg.add(
            subject=subject,
            predicate=predicate,
            object=object_,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        return result.get("triple_id", "")

    def kg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        kg = self._get_kg()
        if kg is None:
            raise RuntimeError("Knowledge graph is not enabled in config.")
        results = kg.query(entity=entity, as_of=as_of)
        triples = []
        for r in results:
            triples.append(
                KGTriple(
                    subject=r.get("subject", ""),
                    predicate=r.get("predicate", ""),
                    object_=r.get("object", ""),
                    valid_from=r.get("valid_from"),
                    valid_to=r.get("valid_to"),
                    confidence=r.get("confidence"),
                    source=r.get("source"),
                )
            )
        return triples

    def kg_invalidate(self, triple_id: str) -> bool:
        kg = self._get_kg()
        if kg is None:
            raise RuntimeError("Knowledge graph is not enabled in config.")
        try:
            kg.invalidate(triple_id=triple_id)
            return True
        except Exception:
            return False

    def import_documents(
        self,
        source_path: str,
        wing: Optional[str] = None,
    ) -> Dict[str, int]:
        from mempalace.miner import mine

        result = mine(
            project_dir=source_path,
            palace_path=self._palace_path,
            wing=wing or self._default_wing,
        )
        # mine() returns various stats; normalize to a standard dict
        if isinstance(result, dict):
            return result
        return {"files_processed": 0, "entries_created": 0}

    def list_wings(self) -> List[Dict[str, Any]]:
        # Unified mode: aggregate from the Chroma collection metadatas. The
        # mempalace Palace API is not available in mempalace>=3.3, so we read
        # from the same backend that write/search use.
        if self._use_derisk_embedding:
            try:
                collection = self._get_chroma_collection()
                data = collection.get(include=["metadatas"])
                counts: Dict[str, int] = {}
                for m in (data.get("metadatas") or []):
                    w = (m or {}).get("wing", self._default_wing)
                    counts[w] = counts.get(w, 0) + 1
                return [{"name": k, "count": v} for k, v in counts.items()]
            except Exception as e:
                logger.warning(f"list_wings failed: {e}")
                return []
        return []

    def list_rooms(self, wing: str) -> List[Dict[str, Any]]:
        if self._use_derisk_embedding:
            try:
                collection = self._get_chroma_collection()
                data = collection.get(
                    where={"wing": wing}, include=["metadatas"]
                )
                counts: Dict[str, int] = {}
                for m in (data.get("metadatas") or []):
                    r = (m or {}).get("room", "general")
                    counts[r] = counts.get(r, 0) + 1
                return [{"name": k, "count": v} for k, v in counts.items()]
            except Exception as e:
                logger.warning(f"list_rooms failed: {e}")
                return []
        return []

    def get_status(self) -> Dict[str, Any]:
        # Read the count from the backend that actually stores the data. In
        # unified mode (default) this is our own Chroma collection.
        try:
            if self._use_derisk_embedding:
                collection = self._get_chroma_collection()
                return {
                    "total_entries": collection.count(),
                    "kg_triples": 0,
                    "provider": "mempalace-unified",
                    "palace_path": self._palace_path,
                }
            # Builtin mode: use the mempalace function-based API.
            from mempalace.palace import get_collection

            collection = get_collection(self._palace_path, create=False)
            return {
                "total_entries": collection.count(),
                "kg_triples": 0,
                "provider": "mempalace",
                "palace_path": self._palace_path,
            }
        except Exception as e:
            logger.warning(f"get_status failed: {e}")
            return {"total_entries": 0, "error": str(e)}
