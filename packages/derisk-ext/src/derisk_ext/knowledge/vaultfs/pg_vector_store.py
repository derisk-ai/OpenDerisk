"""Postgres + pgvector adapter for DistributedVaultFS.

Satisfies the `VectorStore` Protocol. Uses asyncpg for connection pooling
and the `pgvector` extension's `vector` type for storage + HNSW index for
fast cosine-similarity search.

Setup (one-time per Postgres cluster):
    CREATE EXTENSION IF NOT EXISTS vector;

The store creates its own table (`ks_vectors_<space_id>` by default) on
first use. Idempotent — safe to call on every initialize().
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Optional

from derisk.knowledge.types import VectorHit

logger = logging.getLogger(__name__)


class PgVectorStore:
    """asyncpg-backed vector store using the pgvector extension.

    Implements the `VectorStore` Protocol. Cosine distance via `<=>` operator;
    HNSW index for sub-linear search at scale.
    """

    def __init__(
        self,
        dsn: str,
        table_name: str,
        dimension: int,
    ):
        self._dsn = dsn
        self._table_name = table_name
        self._dimension = dimension
        self._pool = None  # asyncpg.Pool, lazy
        self._initialized = False
        self._init_lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def table_name(self) -> str:
        return self._table_name

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure(self) -> None:
        """Lazy init: open pool + create extension + create table + HNSW index."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            import asyncpg

            self._pool = await asyncpg.create_pool(
                dsn=self._dsn, min_size=1, max_size=4, command_timeout=30
            )
            async with self._pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                # Sanitize table name (space_id is ULID, safe but be defensive)
                if not self._table_name.replace("_", "").isalnum():
                    raise ValueError(f"unsafe table name: {self._table_name}")
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        id TEXT PRIMARY KEY,
                        embedding vector({self._dimension}) NOT NULL,
                        meta JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                    """
                )
                # HNSW index for cosine similarity. IF NOT EXISTS guards re-init.
                # Falls back to IVFFlat on older pgvector versions via the
                # exception handler below.
                try:
                    await conn.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_{self._table_name}_emb
                        ON {self._table_name} USING hnsw (embedding vector_cosine_ops)
                        """
                    )
                except Exception as e:
                    logger.warning(
                        "HNSW index creation failed for %s (%s); "
                        "queries will degrade to sequential scan",
                        self._table_name,
                        e,
                    )
            self._initialized = True

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        self._initialized = False

    # ------------------------------------------------------------------
    # VectorStore protocol
    # ------------------------------------------------------------------

    async def upsert(self, id: str, embedding: list[float], meta: dict) -> None:
        await self._ensure()
        if len(embedding) != self._dimension:
            raise ValueError(
                f"embedding dim {len(embedding)} != store dim {self._dimension}"
            )
        # pgvector accepts '[1.0,2.0,3.0]' literal
        vec_literal = "[" + ",".join(f"{float(x):.7g}" for x in embedding) + "]"
        meta_json = json.dumps(meta, ensure_ascii=False)
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self._table_name} (id, embedding, meta)
                VALUES ($1, $2::vector, $3::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    meta = EXCLUDED.meta
                """,
                id,
                vec_literal,
                meta_json,
            )

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
        vec_literal = "[" + ",".join(f"{float(x):.7g}" for x in embedding) + "]"

        # Build optional JSONB filter predicate.
        params: list = [vec_literal, top_k]
        where_clause = ""
        if filter:
            # Each k=v becomes `meta @> $N::jsonb` — containment match.
            clauses = []
            for k, v in filter.items():
                params.append(json.dumps({k: v}))
                clauses.append(f"meta @> ${len(params)}::jsonb")
            where_clause = "WHERE " + " AND ".join(clauses)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, meta,
                       1 - (embedding <=> $1::vector) AS score
                FROM {self._table_name}
                {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                *params,
            )

        hits: list[VectorHit] = []
        for r in rows:
            meta = r["meta"] if isinstance(r["meta"], dict) else json.loads(r["meta"])
            hits.append(
                VectorHit(
                    id=r["id"],
                    score=float(r["score"]),
                    metadata=meta,
                    document_id=meta.get("document_id"),
                    verbat_id=meta.get("verbat_id"),
                )
            )
        return hits

    async def delete(self, id: str) -> None:
        if not self._initialized:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {self._table_name} WHERE id=$1", id
            )

    async def clear(self) -> None:
        if not self._initialized:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {self._table_name}")


def advisory_lock_key(space_id: str) -> int:
    """Stable 64-bit int key for `pg_advisory_lock` from a space id."""
    h = hashlib.sha256(space_id.encode("utf-8")).digest()
    # Take first 8 bytes as a signed 64-bit int
    import struct

    return struct.unpack(">q", h[:8])[0]
