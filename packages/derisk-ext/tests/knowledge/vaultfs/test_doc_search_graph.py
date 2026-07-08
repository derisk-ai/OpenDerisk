"""RFC-005 Phase 3 tests: doc_search mode="graph" + temporal filtering.

Verifies graph expansion (seed -> entity -> neighbor via `about` edges)
recalls docs that don't contain the query keywords, and that superseded
docs are filtered out by default.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import Edge, new_edge_id, new_space_id
from derisk_ext.knowledge.vaultfs import LocalVaultFS


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    root = tmp_path / "ks_graph"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


async def _mkdoc(vault, path, title, body):
    md = f"---\ntype: source\ntitle: {title}\n---\n\n{body}\n"
    return await vault.doc_create(path=path, content=md)


async def _mkentity(vault, name, desc, body):
    md = f"---\ntype: entity\ntitle: {name}\ndescription: {desc}\n---\n\n{body}\n"
    return await vault.doc_create(path=f"entities/{name}.md", content=md)


@pytest.mark.asyncio
async def test_graph_mode_recalls_neighbor_without_keyword(vault):
    """D1 has the query keyword; D2 (about same entity) does NOT. graph mode
    should recall D2 via D1 -> entity -> D2 about edges.

    Uses ASCII keywords because the default FTS tokenizer (porter unicode61)
    is weak on CJK — the test's focus is graph expansion, not CJK FTS.
    """
    d1 = await _mkdoc(vault, "sources/d1.md", "D1", "scoring card risk model details")
    d2 = await _mkdoc(vault, "sources/d2.md", "D2", "xgboost training parameters")  # no "scoring"
    ent = await _mkentity(vault, "e1", "scoring-card", "a scoring card model")

    # entity is about both D1 and D2
    now = datetime.utcnow()
    for src in (d1, d2):
        await vault.edge_add(
            Edge(
                id=new_edge_id(),
                space_id=vault.space_id,
                subject=f"doc:{ent}",
                predicate="about",
                object=f"doc:{src}",
                source_document_id=ent,
                valid_from=now,
                created_at=now,
            )
        )

    # hybrid only finds D1 (D2 lacks the keyword)
    hybrid = await vault.doc_search("scoring", mode="hybrid", limit=10)
    hybrid_ids = {h.document_id for h in hybrid}
    assert d1 in hybrid_ids
    assert d2 not in hybrid_ids, "D2 has no keyword, must not be a hybrid hit"

    # graph mode pulls D2 in via the entity
    graph = await vault.doc_search("scoring", mode="graph", limit=10)
    graph_ids = {h.document_id for h in graph}
    assert d1 in graph_ids
    assert d2 in graph_ids, "graph mode must recall D2 via about edges"


@pytest.mark.asyncio
async def test_graph_mode_filters_superseded_docs(vault):
    """A doc that is the object of an active `supersedes` edge should be
    filtered out of graph results (only-latest-version on chains)."""
    old_doc = await _mkdoc(vault, "sources/old.md", "Old", "scoring card old version")
    new_doc = await _mkdoc(vault, "sources/new.md", "New", "scoring card new version")
    now = datetime.utcnow()
    # new supersedes old -> old is the object, should be filtered
    await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject=f"doc:{new_doc}",
            predicate="supersedes",
            object=f"doc:{old_doc}",
            source_document_id=new_doc,
            valid_from=now,
            created_at=now,
        )
    )

    # both have the keyword, so hybrid would return both
    hybrid = await vault.doc_search("scoring", mode="hybrid", limit=10)
    hybrid_ids = {h.document_id for h in hybrid}
    assert old_doc in hybrid_ids and new_doc in hybrid_ids

    # graph mode drops the superseded old doc
    graph = await vault.doc_search("scoring", mode="graph", limit=10)
    graph_ids = {h.document_id for h in graph}
    assert new_doc in graph_ids
    assert old_doc not in graph_ids, "superseded doc must be filtered"


@pytest.mark.asyncio
async def test_expired_about_edge_excluded_from_expansion(vault):
    """An about edge with valid_to in the past must not pull its doc in."""
    seed = await _mkdoc(vault, "sources/seed.md", "Seed", "scoring card main entry")
    stale_neighbor = await _mkdoc(vault, "sources/stale.md", "Stale", "stale expired content")
    ent = await _mkentity(vault, "e2", "scoring-card-2", "entity")
    now = datetime.utcnow()
    # active edge: entity -> seed
    await vault.edge_add(
        Edge(
            id=new_edge_id(), space_id=vault.space_id,
            subject=f"doc:{ent}", predicate="about", object=f"doc:{seed}",
            source_document_id=ent, valid_from=now, created_at=now,
        )
    )
    # expired edge: entity -> stale_neighbor (born expired via Phase 1 fix)
    await vault.edge_add(
        Edge(
            id=new_edge_id(), space_id=vault.space_id,
            subject=f"doc:{ent}", predicate="about", object=f"doc:{stale_neighbor}",
            source_document_id=ent, valid_from=now - timedelta(days=2),
            valid_to=now - timedelta(days=1), created_at=now - timedelta(days=2),
        )
    )

    graph = await vault.doc_search("scoring", mode="graph", limit=10)
    graph_ids = {h.document_id for h in graph}
    assert seed in graph_ids
    assert stale_neighbor not in graph_ids, "expired about edge must not expand"