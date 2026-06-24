"""Chroma vector store adapter for DistributedVaultFS.

Uses chromadb (lazy import) to talk to a Chroma server. Each space
gets its own collection. Distributed mode requires a Chroma server
(`chroma_uri` must be set) — the embedded local mode is unsafe for
multi-process access (file races).

Collection schema:
- `id` (string, primary key): caller-chosen stable key
- `embedding` (float vector, dim from embedder identity)
- `metadata` (dict): for filtering + hit enrichment
- `document` (string): unused, kept for Chroma API compatibility

Chroma's default distance metric is cosine, which matches our
VectorStore Protocol semantics.

Satisfies the `VectorStore` Protocol (vaultfs/vector_store.py).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from derisk.knowledge.types import VectorHit

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Chroma-backed vector store (server mode for distributed)."""

    def __init__(
        self,
        uri: str,
        collection_name: str,
        dimension: int,
    ):
        self._uri = uri.rstrip("/")
        self._collection_name = collection_name
        self._dimension = dimension
        self._client = None  # chromadb.HttpClient, lazy
        self._collection = None
        self._lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _ensure(self) -> None:
        if self._collection is not None:
            return
        async with self._lock:
            if self._collection is not None:
                return

            def _connect():
                import chromadb  # lazy

                client = chromadb.HttpClient(host=self._uri)
                # get_or_create so multiple processes converge on the same
                # collection. cosine distance matches our protocol semantics.
                col = client.get_or_create_collection(
                    name=self._collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                return client, col

            self._client, self._collection = await asyncio.to_thread(_connect)

    async def upsert(self, id: str, embedding: list[float], meta: dict) -> None:
        await self._ensure()
        if len(embedding) != self._dimension:
            raise ValueError(
                f"embedding dim {len(embedding)} != store dim {self._dimension}"
            )

        def _do():
            self._collection.upsert(
                ids=[id],
                embeddings=[embedding],
                metadatas=[meta],
                documents=[""],
            )

        await asyncio.to_thread(_do)

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filter: Optional[dict] = None,
    ) -> list[VectorHit]:
        await self._ensure()
        if len(embedding) != self._dimension:
            raise ValueError(
                f"embedding dim {len(embedding)} != store dim {self._dimension}"
            )

        def _do():
            res = self._collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=filter or None,
            )
            # Chroma returns lists-of-lists (one per query vector). We sent 1.
            ids = (res.get("ids") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            hits = []
            for i, _id in enumerate(ids):
                meta = metas[i] if i < len(metas) else {}
                distance = dists[i] if i < len(dists) else 0.0
                # Chroma cosine distance = 1 - similarity; convert back.
                score = 1.0 - float(distance)
                hits.append(
                    VectorHit(
                        id=_id,
                        score=score,
                        metadata=meta or {},
                        document_id=(meta or {}).get("document_id"),
                        verbat_id=(meta or {}).get("verbat_id"),
                    )
                )
            return hits

        return await asyncio.to_thread(_do)

    async def delete(self, id: str) -> None:
        if self._collection is None:
            return

        def _do():
            self._collection.delete(ids=[id])

        await asyncio.to_thread(_do)

    async def clear(self) -> None:
        if self._collection is None:
            return

        def _do():
            # Delete the collection; next op re-creates via get_or_create.
            try:
                self._client.delete_collection(self._collection_name)
            except Exception as e:
                logger.warning("Chroma clear failed: %s", e)
            self._collection = None

        await asyncio.to_thread(_do)
