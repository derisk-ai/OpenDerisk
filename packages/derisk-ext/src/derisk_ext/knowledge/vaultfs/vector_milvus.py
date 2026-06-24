"""Milvus vector store adapter for DistributedVaultFS.

Uses pymilvus (lazy import) to talk to a Milvus cluster. Each space
gets its own collection named `{prefix}{space_id_hash}` so multiple
spaces can coexist in the same Milvus instance.

Collection schema:
- `id` (VARCHAR, primary key): caller-chosen stable key (doc:<id> / verbat:<id>)
- `embedding` (FLOAT_VECTOR, dim from embedder identity)
- `meta` (JSON): metadata for filtering + hit enrichment

HNSW index for cosine similarity (Milvus metric_type IP + normalized
vectors ≈ cosine, but we use COSINE directly which Milvus supports).

Satisfies the `VectorStore` Protocol (vaultfs/vector_store.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Optional

from derisk.knowledge.types import VectorHit

logger = logging.getLogger(__name__)


def _collection_name(prefix: str, space_id: str) -> str:
    """Stable, Milvus-safe collection name from a space id.

    Milvus collection names must match `^[a-zA-Z_][a-zA-Z0-9_]*$` and
    be ≤ 255 chars. Space ids are ULIDs (safe), but hash anyway to
    bound length and guarantee the prefix+name stays valid.
    """
    h = hashlib.sha256(space_id.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}{h}"


class MilvusVectorStore:
    """Milvus-backed vector store.

    All pymilvus calls are sync — wrapped in `asyncio.to_thread` to
    avoid blocking the event loop.
    """

    def __init__(
        self,
        uri: str,
        collection_name: str,
        dimension: int,
    ):
        self._uri = uri
        self._collection_name = collection_name
        self._dimension = dimension
        self._client = None  # pymilvus.MilvusClient, lazy
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _ensure(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return

            def _connect():
                from pymilvus import MilvusClient, DataType  # lazy

                client = MilvusClient(uri=self._uri)
                if not client.has_collection(self._collection_name):
                    schema = client.create_schema(
                        auto_id=False, enable_dynamic_field=False
                    )
                    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
                    schema.add_field(
                        "embedding", DataType.FLOAT_VECTOR, dim=self._dimension
                    )
                    schema.add_field("meta", DataType.JSON)
                    index_params = client.prepare_index_params()
                    index_params.add_index(
                        field_name="embedding",
                        index_type="HNSW",
                        metric_type="COSINE",
                        params={"M": 16, "efConstruction": 64},
                    )
                    client.create_collection(
                        collection_name=self._collection_name,
                        schema=schema,
                        index_params=index_params,
                    )
                return client

            self._client = await asyncio.to_thread(_connect)
            self._initialized = True

    async def upsert(self, id: str, embedding: list[float], meta: dict) -> None:
        await self._ensure()
        if len(embedding) != self._dimension:
            raise ValueError(
                f"embedding dim {len(embedding)} != store dim {self._dimension}"
            )

        def _do():
            self._client.upsert(
                collection_name=self._collection_name,
                data=[
                    {
                        "id": id,
                        "embedding": embedding,
                        "meta": meta,
                    }
                ],
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

        # Milvus filter is a SQL-like string; build from the dict filter.
        # meta is a JSON field; pymilvus supports `meta["key"] == value`.
        expr = ""
        if filter:
            clauses = []
            for k, v in filter.items():
                if isinstance(v, str):
                    clauses.append(f'meta["{k}"] == "{v}"')
                elif isinstance(v, bool):
                    clauses.append(f'meta["{k}"] == {str(v).lower()}')
                elif isinstance(v, (int, float)):
                    clauses.append(f'meta["{k}"] == {v}')
                elif v is None:
                    clauses.append(f'meta["{k}"] == null')
            expr = " and ".join(clauses)

        def _do():
            results = self._client.search(
                collection_name=self._collection_name,
                data=[embedding],
                limit=top_k,
                filter=expr or None,
                output_fields=["meta"],
            )
            # results is a list of list (one per query vector); we sent 1
            hits = []
            for r in (results[0] if results else []):
                entity = r.get("entity", {}) if isinstance(r, dict) else {}
                meta = entity.get("meta") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                hits.append(
                    VectorHit(
                        id=r.get("id"),
                        score=float(r.get("distance", 0.0)),
                        metadata=meta if isinstance(meta, dict) else {},
                        document_id=meta.get("document_id") if isinstance(meta, dict) else None,
                        verbat_id=meta.get("verbat_id") if isinstance(meta, dict) else None,
                    )
                )
            return hits

        return await asyncio.to_thread(_do)

    async def delete(self, id: str) -> None:
        if not self._initialized:
            return

        def _do():
            self._client.delete(
                collection_name=self._collection_name,
                filter=f'id == "{id}"',
            )

        await asyncio.to_thread(_do)

    async def clear(self) -> None:
        if not self._initialized:
            return

        def _do():
            # Drop and recreate (Milvus doesn't have a "delete all" op).
            self._client.drop_collection(self._collection_name)
            self._initialized = False

        await asyncio.to_thread(_do)
        # Next op will re-create via _ensure
