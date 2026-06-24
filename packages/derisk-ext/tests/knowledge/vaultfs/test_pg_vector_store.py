"""Tests for PgVectorStore — skipped unless a Postgres+pgvector DSN is available.

Set `KNOWLEDGE_PG_DSN` to a Postgres DSN (e.g.
`postgresql://user:pass@localhost:5432/derisk_test`) with the `vector`
extension installed (`CREATE EXTENSION vector;`) to run these tests
against a live DB.

Without the env var, the entire module skips — local CI doesn't require
Postgres.
"""

from __future__ import annotations

import os
import uuid

import pytest

pg_dsn = os.getenv("KNOWLEDGE_PG_DSN")
pytestmark = pytest.mark.skipif(
    not pg_dsn,
    reason="set KNOWLEDGE_PG_DSN to a Postgres+pgvector DSN to run this suite",
)


@pytest.fixture
async def store():
    from derisk_ext.knowledge.vaultfs.pg_vector_store import PgVectorStore

    table = f"ks_test_{uuid.uuid4().hex[:8]}"
    s = PgVectorStore(dsn=pg_dsn, table_name=table, dimension=3)
    yield s
    # Cleanup: drop the test table
    try:
        await s._ensure()
        async with s._pool.acquire() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {table}")
    except Exception:
        pass
    await s.close()


@pytest.mark.asyncio
async def test_dimension_property(store):
    assert store.dimension == 3


@pytest.mark.asyncio
async def test_upsert_and_query_returns_nearest(store):
    await store.upsert("a", [1.0, 0.0, 0.0], {"label": "x"})
    await store.upsert("b", [0.0, 1.0, 0.0], {"label": "y"})
    await store.upsert("c", [1.0, 0.1, 0.0], {"label": "z"})

    hits = await store.query([1.0, 0.0, 0.0], top_k=2)
    assert len(hits) == 2
    # Nearest to [1,0,0] is "a" (exact match), then "c"
    assert hits[0].id == "a"
    assert hits[0].score > 0.99
    assert hits[1].id == "c"
    assert hits[1].metadata.get("label") == "z"


@pytest.mark.asyncio
async def test_upsert_is_idempotent_on_id(store):
    await store.upsert("k", [1.0, 0.0, 0.0], {"v": 1})
    await store.upsert("k", [0.0, 1.0, 0.0], {"v": 2})  # replace
    hits = await store.query([0.0, 1.0, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0].id == "k"
    assert hits[0].metadata.get("v") == 2


@pytest.mark.asyncio
async def test_query_with_meta_filter(store):
    await store.upsert("a", [1.0, 0.0, 0.0], {"kind": "doc", "n": 1})
    await store.upsert("b", [1.0, 0.0, 0.0], {"kind": "verbat", "n": 2})

    hits = await store.query([1.0, 0.0, 0.0], top_k=10, filter={"kind": "doc"})
    assert len(hits) == 1
    assert hits[0].id == "a"


@pytest.mark.asyncio
async def test_delete_removes_vector(store):
    await store.upsert("a", [1.0, 0.0, 0.0], {})
    await store.delete("a")
    hits = await store.query([1.0, 0.0, 0.0], top_k=5)
    assert len(hits) == 0


@pytest.mark.asyncio
async def test_clear_empties_table(store):
    await store.upsert("a", [1.0, 0.0, 0.0], {})
    await store.upsert("b", [0.0, 1.0, 0.0], {})
    await store.clear()
    hits = await store.query([1.0, 0.0, 0.0], top_k=5)
    assert len(hits) == 0


@pytest.mark.asyncio
async def test_upsert_rejects_wrong_dimension(store):
    with pytest.raises(ValueError, match="dim"):
        await store.upsert("a", [1.0, 0.0], {})  # dim 2 vs store dim 3
