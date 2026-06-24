"""End-to-end test of knowledge tools against a live LocalVaultFS."""

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import new_space_id
from derisk_ext.knowledge.resource import (
    KnowledgeSpaceResource,
    set_vault_factory,
)
from derisk_ext.knowledge.tools import (
    DocCreateTool,
    DocReadTool,
    DocSearchTool,
    EdgeAddTool,
    GraphQueryTool,
    SchemaReadTool,
    VerbatAddTool,
    VerbatSearchTool,
)
from derisk_ext.knowledge.vaultfs import LocalVaultFS


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "ks_e2e")
    await v.initialize()
    # Register a sync vault factory keyed by slug
    set_vault_factory(lambda slug: v)
    yield v
    set_vault_factory(None)  # reset for other tests
    await v.close()


@pytest.mark.asyncio
async def test_verbat_add_then_search(vault):
    add = VerbatAddTool()
    r = await add.execute(
        {
            "space_slug": "test",
            "content": "The quick brown fox jumps over the lazy dog.",
            "source_file": "fox.txt",
            "extract_mode": "upload",
        }
    )
    assert r.success, r.error
    vid = r.output["verbat_id"]

    search = VerbatSearchTool()
    r2 = await search.execute({"space_slug": "test", "query": "fox"})
    assert r2.success
    assert any(h["verbat_id"] == vid for h in r2.output)


@pytest.mark.asyncio
async def test_doc_create_read_search(vault):
    create = DocCreateTool()
    r = await create.execute(
        {
            "space_slug": "test",
            "path": "concepts/attention.md",
            "content": """---
type: concept
title: Attention Mechanism
created: 2026-06-23
updated: 2026-06-23
---

The attention mechanism lets neural networks focus on relevant parts.
Links to [[transformer]].
""",
        }
    )
    assert r.success, r.error
    doc_id = r.output["doc_id"]

    read = DocReadTool()
    r2 = await read.execute(
        {"space_slug": "test", "path": "concepts/attention.md"}
    )
    assert r2.success
    assert r2.output["title"] == "Attention Mechanism"
    assert r2.output["id"] == doc_id

    search = DocSearchTool()
    r3 = await search.execute({"space_slug": "test", "query": "attention"})
    assert r3.success
    assert any(h["path"] == "concepts/attention.md" for h in r3.output)


@pytest.mark.asyncio
async def test_edge_add_validates_predicate(vault):
    add = EdgeAddTool()
    # links-to is in default schema
    r = await add.execute(
        {
            "space_slug": "test",
            "subject": "alpha",
            "predicate": "links-to",
            "object": "beta",
        }
    )
    assert r.success, r.error

    # Bogus predicate should fail
    r2 = await add.execute(
        {
            "space_slug": "test",
            "subject": "alpha",
            "predicate": "totally-fake",
            "object": "gamma",
        }
    )
    assert not r2.success
    assert "schema.md" in r2.error or "Relation Types" in r2.error


@pytest.mark.asyncio
async def test_doc_create_validates_page_type(vault):
    create = DocCreateTool()
    r = await create.execute(
        {
            "space_slug": "test",
            "path": "concepts/x.md",
            "content": """---
type: nonexistent_type
title: X
created: 2026-06-23
updated: 2026-06-23
---

Body.
""",
        }
    )
    assert not r.success
    assert "schema.md" in r.error or "Page Types" in r.error


@pytest.mark.asyncio
async def test_schema_read_returns_default(vault):
    read = SchemaReadTool()
    r = await read.execute({"space_slug": "test"})
    assert r.success
    assert "Page Types" in r.output["schema_md"]
    assert "Relation Types" in r.output["schema_md"]


@pytest.mark.asyncio
async def test_graph_query_after_edge_add(vault):
    add = EdgeAddTool()
    await add.execute(
        {
            "space_slug": "test",
            "subject": "alpha",
            "predicate": "links-to",
            "object": "beta",
        }
    )
    q = GraphQueryTool()
    r = await q.execute({"space_slug": "test", "entity": "alpha"})
    assert r.success
    assert "alpha" in r.output["nodes"]
    assert "beta" in r.output["nodes"]


@pytest.mark.asyncio
async def test_resource_resolves_vault_lazily(vault):
    # Without a pre-attached vault, the resource should resolve via factory
    r = KnowledgeSpaceResource(name="ks", space_slug="test")
    resolved = await r.get_vault()
    assert resolved is vault
