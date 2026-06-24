"""VectorStore protocol — abstract vector upsert/query/delete/clear interface.

Every VaultFS backend resolves a VectorStore instance lazily (only when an
embedder identity is set). LocalVaultFS uses LanceVectorStore;
DistributedVaultFS uses PgVectorStore (or future Milvus/Chroma adapters).

The interface mirrors LanceVectorStore's shape so existing LocalVaultFS
call sites (`self._vector_store.upsert(...)` etc.) work unchanged across
backends.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from derisk.knowledge.types import VectorHit


@runtime_checkable
class VectorStore(Protocol):
    """Async vector store with upsert / query / delete / clear semantics.

    `id` is the caller-chosen stable key (typically `doc:<id>` or `verbat:<id>`).
    `meta` is a JSON-serializable dict — implementations may persist it as
    JSONB, JSON string, or structured columns.

    Concrete classes also expose a `dimension` attribute/property, but it's
    not part of the Protocol because LanceVectorStore only learns its
    dimension on first upsert (lazy init). Callers that need the dimension
    should read it from `embedder_identity.dimension` in the vault DB.
    """

    async def upsert(self, id: str, embedding: list[float], meta: dict) -> None:
        """Insert or replace the vector for `id`."""
        ...

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filter: Optional[dict] = None,
    ) -> list[VectorHit]:
        """Return the top_k nearest vectors to `embedding`.

        `filter` is an optional dict of metadata equality predicates. The
        caller treats results as ranked by similarity (higher score = closer).
        """
        ...

    async def delete(self, id: str) -> None:
        """Remove the vector for `id`. No-op if missing."""
        ...

    async def clear(self) -> None:
        """Drop all vectors. Used by `set_embedder_identity(force_swap=True)`."""
        ...
