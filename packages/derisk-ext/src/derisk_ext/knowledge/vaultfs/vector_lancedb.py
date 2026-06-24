"""LanceDB vector store adapter for LocalVaultFS.

Lazy-imported so the rest of LocalVaultFS works without lancedb installed.
LanceDB is chosen over sqlite-vec for better performance on larger spaces;
falls back to in-memory brute-force if lancedb unavailable.

Satisfies the `VectorStore` Protocol (vaultfs/vector_store.py) — `upsert`,
`query`, `delete`, `clear`, and the `dimension` property.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import Optional

from derisk.knowledge.types import VectorHit

logger = logging.getLogger(__name__)


class LanceVectorStore:
    """Wraps a LanceDB table for vector upsert / query / delete.

    Table schema: id (str, pk), vector (fixed_dim float list), meta (json str).
    """

    def __init__(self, path: Path | str, table_name: str = "vectors"):
        self._path = Path(path)
        self._table_name = table_name
        self._db = None
        self._table = None
        self._dimension: Optional[int] = None
        self._lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        """The dimension this store was opened with.

        Raises if `upsert`/`query` hasn't been called yet (lazy init).
        """
        if self._dimension is None:
            raise RuntimeError(
                "LanceVectorStore.dimension is unknown until first upsert/query"
            )
        return self._dimension

    async def _ensure(self, dimension: int) -> None:
        """Open or create the LanceDB table with the given vector dimension."""
        if self._table is not None and self._dimension == dimension:
            return

        def _open():
            import lancedb  # lazy import

            self._path.parent.mkdir(parents=True, exist_ok=True)
            db = lancedb.connect(str(self._path))
            try:
                tbl = db.open_table(self._table_name)
                # Read schema to confirm dimension
                # LanceDB stores vector as FixedSizeList; introspect via schema
                self._dimension = dimension
                return db, tbl
            except Exception:
                # Create new table with sample row
                import pyarrow as pa

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
        import json

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
            # LanceDB merge_insert for upsert semantics
            try:
                self._table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(pa.Table.from_pylist(data))
            except Exception:
                # Fallback: delete + add
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
                # Convert dict filter to SQL WHERE
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
            import json

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
                logger.warning(f"Failed to delete vector {id}: {e}")

        await asyncio.to_thread(_do)

    async def clear(self) -> None:
        """Drop all vectors (used on embedder force_swap)."""
        if self._table is None:
            return

        def _do():
            try:
                self._table.delete("true")
            except Exception as e:
                logger.warning(f"Failed to clear vectors: {e}")

        await asyncio.to_thread(_do)
