"""LanceDB-on-S3 vector store adapter for DistributedVaultFS.

Same shape as the local `LanceVectorStore`, but connects LanceDB to an
S3 bucket so multiple processes (and multiple service replicas) share
the same vector set. Required for distributed mode where LocalVaultFS's
file-backed Lance isn't shareable.

LanceDB natively supports S3 via the connection URI:
    lancedb.connect("s3://bucket/prefix")

S3 credentials are read from the standard AWS env vars
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) or the
bucket's IAM role. For MinIO / OSS / other S3-compatible stores, set
`AWS_ENDPOINT` and `AWS_ALLOW_HTTP=true` (for non-TLS endpoints).

Satisfies the `VectorStore` Protocol (vaultfs/vector_store.py) — `upsert`,
`query`, `delete`, `clear`, and the `dimension` property.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from derisk.knowledge.types import VectorHit

logger = logging.getLogger(__name__)


class LanceS3VectorStore:
    """LanceDB-backed vector store on S3 (multi-process shared).

    Each space gets its own table inside the LanceDB database at
    `s3_uri`. The table is created on first upsert with the embedder's
    dimension.
    """

    def __init__(self, s3_uri: str, table_name: str):
        """Args:
            s3_uri: S3 URI prefix for the LanceDB database,
                e.g. "s3://my-bucket/knowledge-vectors"
            table_name: per-space table name, e.g. "ks_vectors_<space_id>"
        """
        self._s3_uri = s3_uri.rstrip("/")
        self._table_name = table_name
        self._db = None
        self._table = None
        self._dimension: Optional[int] = None
        self._lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError(
                "LanceS3VectorStore.dimension unknown until first upsert/query"
            )
        return self._dimension

    async def _ensure(self, dimension: int) -> None:
        """Open or create the LanceDB table on S3 with the given dimension."""
        if self._table is not None and self._dimension == dimension:
            return

        def _open():
            import lancedb  # lazy
            import pyarrow as pa

            db = lancedb.connect(self._s3_uri)
            try:
                tbl = db.open_table(self._table_name)
                self._dimension = dimension
                return db, tbl
            except Exception:
                schema = pa.schema(
                    [
                        pa.field("id", pa.string()),
                        pa.field(
                            "vector",
                            pa.list_(pa.float32(), dimension),
                        ),
                        pa.field("meta", pa.string()),
                    ]
                )
                tbl = db.create_table(
                    self._table_name, schema=schema, mode="overwrite"
                )
                self._dimension = dimension
                return db, tbl

        async with self._lock:
            if self._table is not None and self._dimension == dimension:
                return
            self._db, self._table = await asyncio.to_thread(_open)

    async def upsert(self, id: str, embedding: list[float], meta: dict) -> None:
        await self._ensure(len(embedding))

        def _do():
            import pyarrow as pa

            data = [
                {
                    "id": id,
                    "vector": embedding,
                    "meta": json.dumps(meta, ensure_ascii=False),
                }
            ]
            try:
                self._table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(
                    pa.Table.from_pylist(data)
                )
            except Exception:
                try:
                    self._table.delete(f'id = "{id}"')
                except Exception:
                    pass
                self._table.add(data)

        await asyncio.to_thread(_do)

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filter: Optional[dict] = None,
    ) -> list[VectorHit]:
        await self._ensure(len(embedding))

        def _do():
            q = self._table.search(embedding).limit(top_k)
            if filter:
                clauses = []
                for k, v in filter.items():
                    if isinstance(v, str):
                        clauses.append(f'meta LIKE \'%"{k}": "{v}"%\'')
                    elif isinstance(v, bool):
                        clauses.append(f'meta LIKE \'%"{k}": {str(v).lower()}\'')
                    elif isinstance(v, (int, float)):
                        clauses.append(f'meta LIKE \'%"{k}": {v}\'')
                if clauses:
                    q = q.where(" AND ".join(clauses))
            results = q.to_list()
            hits = []
            for r in results:
                meta = json.loads(r["meta"]) if r.get("meta") else {}
                hits.append(
                    VectorHit(
                        id=r["id"],
                        score=1.0 - r.get("_distance", 0.0),
                        metadata=meta,
                        document_id=meta.get("document_id"),
                        verbat_id=meta.get("verbat_id"),
                    )
                )
            return hits

        return await asyncio.to_thread(_do)

    async def delete(self, id: str) -> None:
        if self._table is None:
            return

        def _do():
            try:
                self._table.delete(f'id = "{id}"')
            except Exception as e:
                logger.warning("Failed to delete vector %s: %s", id, e)

        await asyncio.to_thread(_do)

    async def clear(self) -> None:
        if self._table is None:
            return

        def _do():
            try:
                self._table.delete("true")
            except Exception as e:
                logger.warning("Failed to clear Lance vectors: %s", e)

        await asyncio.to_thread(_do)
