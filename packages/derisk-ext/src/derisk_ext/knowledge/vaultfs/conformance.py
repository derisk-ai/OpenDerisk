"""VaultFS conformance test suite (RFC 002 §6).

Every VaultFS implementation (LocalVaultFS, DistributedVaultFS, future
third-party backends) must pass this entire suite. CI enforces it across
all backends to prevent the "local mode is feature-stripped" anti-pattern
seen in llmwiki.

Usage:
    from derisk_ext.knowledge.vaultfs.conformance import run_conformance

    async def test_local_conformance():
        vault = LocalVaultFS(space_id="s_test", root=tmp_path)
        await vault.initialize()
        try:
            await run_conformance(vault)
        finally:
            await vault.close()

The suite is backend-agnostic: it operates purely through the VaultFS
Protocol, so the same tests run against any implementation.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Callable

from derisk.knowledge.types import (
    ChangeEvent,
    Edge,
    ExtractMode,
    Verbat,
    new_doc_id,
    new_edge_id,
    new_verbat_id,
    sha256_hash,
)


class ConformanceFailure(AssertionError):
    """Raised when a conformance check fails."""


async def run_conformance(vault) -> None:
    """Run the full conformance suite against a VaultFS instance."""
    checks = [
        # L0
        ("L0 verbat_add returns id", test_verbat_add_returns_id),
        ("L0 verbat_add dedupes by content_hash", test_verbat_add_dedupes),
        ("L0 verbat is immutable (deprecate keeps content)", test_verbat_immutable),
        ("L0 verbat_search by extract_mode", test_verbat_search_extract_mode),
        ("L0 verbat_list paginates", test_verbat_list_paginates),
        # L1
        ("L1 doc_create returns id", test_doc_create_returns_id),
        ("L1 doc_edit updates version", test_doc_edit_bumps_version),
        ("L1 doc_delete refuses protected files", test_doc_delete_protected),
        ("L1 doc_search documents mode", test_doc_search_documents),
        ("L1 doc_append_log appends", test_doc_append_log),
        # L2
        ("L2 edge_add creates edge", test_edge_add),
        ("L2 edge_invalidate keeps history", test_edge_invalidate_keeps_history),
        ("L2 graph_traverse BFS", test_graph_traverse_bfs),
        ("L2 graph_backlinks reverse lookup", test_graph_backlinks),
        ("L2 reindex L2 rebuilds from L1", test_reindex_l2),
        # Cross-cutting
        ("Lock writer_lock excludes concurrent", test_write_lock_exclusion),
        ("Events publish + subscribe", test_event_pubsub),
        ("Embedder identity state machine", test_embedder_identity),
    ]

    failures: list[str] = []
    for name, fn in checks:
        try:
            result = fn(vault)
            if inspect.isawaitable(result):
                await result
            print(f"  ✓ {name}")
        except Exception as e:
            failures.append(f"{name}: {e}")
            print(f"  ✗ {name}: {e}")

    if failures:
        raise ConformanceFailure(
            f"{len(failures)}/{len(checks)} conformance checks failed:\n  - "
            + "\n  - ".join(failures)
        )


# ---------------------------------------------------------------------------
# L0 tests
# ---------------------------------------------------------------------------


async def test_verbat_add_returns_id(vault):
    v = Verbat.create(
        space_id=vault.space_id,
        content="hello world",
        source_file="test.txt",
        extract_mode=ExtractMode.UPLOAD,
    )
    vid = await vault.verbat_add(v)
    assert vid, "verbat_add must return an id"
    fetched = await vault.verbat_get(vid)
    assert fetched is not None, "verbat_get must return the verbatim"
    assert fetched.content == "hello world"


async def test_verbat_add_dedupes(vault):
    v1 = Verbat.create(
        space_id=vault.space_id,
        content="duplicate content",
        source_file="a.txt",
        extract_mode=ExtractMode.UPLOAD,
    )
    v2 = Verbat.create(
        space_id=vault.space_id,
        content="duplicate content",
        source_file="b.txt",
        extract_mode=ExtractMode.UPLOAD,
    )
    id1 = await vault.verbat_add(v1)
    id2 = await vault.verbat_add(v2)
    assert id1 == id2, f"dedupe failed: {id1} != {id2}"


async def test_verbat_immutable(vault):
    v = Verbat.create(
        space_id=vault.space_id,
        content="to be deprecated",
        source_file="dep.txt",
        extract_mode=ExtractMode.UPLOAD,
    )
    vid = await vault.verbat_add(v)
    await vault.verbat_deprecate(vid)
    fetched = await vault.verbat_get(vid)
    assert fetched is not None
    assert fetched.deprecated is True
    assert fetched.content == "to be deprecated", "content must remain after deprecate"


async def test_verbat_search_extract_mode(vault):
    v1 = Verbat.create(
        space_id=vault.space_id,
        content="convo fragment about X",
        source_file="chat.json",
        extract_mode=ExtractMode.CONVO,
    )
    v2 = Verbat.create(
        space_id=vault.space_id,
        content="uploaded note about X",
        source_file="note.md",
        extract_mode=ExtractMode.UPLOAD,
    )
    await vault.verbat_add(v1)
    await vault.verbat_add(v2)

    convo_hits = await vault.verbat_search("X", extract_mode="convo")
    assert len(convo_hits) == 1
    assert convo_hits[0].extract_mode == ExtractMode.CONVO

    upload_hits = await vault.verbat_search("X", extract_mode="upload")
    assert len(upload_hits) == 1
    assert upload_hits[0].extract_mode == ExtractMode.UPLOAD


async def test_verbat_list_paginates(vault):
    for i in range(5):
        v = Verbat.create(
            space_id=vault.space_id,
            content=f"page item {i}",
            source_file=f"p{i}.txt",
            extract_mode=ExtractMode.UPLOAD,
        )
        await vault.verbat_add(v)
    page1 = await vault.verbat_list(limit=2, offset=0)
    page2 = await vault.verbat_list(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


# ---------------------------------------------------------------------------
# L1 tests
# ---------------------------------------------------------------------------


async def test_doc_create_returns_id(vault):
    content = """---
type: concept
title: Test Concept
created: 2026-06-23
updated: 2026-06-23
---

# Test Concept

This is a test page about [[other]].
"""
    doc_id = await vault.doc_create(path="concepts/test.md", content=content)
    assert doc_id, "doc_create must return an id"
    doc = await vault.doc_read("concepts/test.md")
    assert doc is not None
    assert doc.title == "Test Concept"
    assert doc.type == "concept"


async def test_doc_edit_bumps_version(vault):
    content_v1 = """---
type: concept
title: V1
created: 2026-06-23
updated: 2026-06-23
---

Body v1.
"""
    await vault.doc_create(path="concepts/v.md", content=content_v1)
    content_v2 = """---
type: concept
title: V2
created: 2026-06-23
updated: 2026-06-23
---

Body v2.
"""
    await vault.doc_edit(path="concepts/v.md", content=content_v2)
    doc = await vault.doc_read("concepts/v.md")
    assert doc.title == "V2"
    assert doc.version == 2, f"version should be 2, got {doc.version}"


async def test_doc_delete_protected(vault):
    # Try to delete log.md - should raise
    try:
        await vault.doc_delete("log.md")
        raise ConformanceFailure("doc_delete should have refused log.md")
    except PermissionError:
        pass  # expected
    except Exception as e:
        raise ConformanceFailure(
            f"doc_delete should raise PermissionError for log.md, got {type(e).__name__}"
        )


async def test_doc_search_documents(vault):
    content = """---
type: concept
title: Attention Mechanism
created: 2026-06-23
updated: 2026-06-23
---

The attention mechanism allows neural networks to focus on relevant parts.
"""
    await vault.doc_create(path="concepts/attention.md", content=content)
    hits = await vault.doc_search("attention", mode="documents", limit=10)
    assert len(hits) >= 1, "expected at least one hit"
    assert any("attention" in h.title.lower() for h in hits)


async def test_doc_append_log(vault):
    await vault.doc_append_log("## [2026-06-23] test | some event")
    log = await vault.doc_read("log.md")
    # log.md may or may not be a tracked document; read raw via the
    # public wiki-file accessor so the check is backend-agnostic.
    text = await vault.read_wiki_file("log.md")
    assert "some event" in text


# ---------------------------------------------------------------------------
# L2 tests
# ---------------------------------------------------------------------------


async def test_edge_add(vault):
    e = Edge(
        id=new_edge_id(),
        space_id=vault.space_id,
        subject="entity_a",
        predicate="links-to",
        object="entity_b",
    )
    eid = await vault.edge_add(e)
    assert eid
    sub = await vault.graph_query(entity="entity_a")
    assert "entity_a" in sub.nodes
    assert "entity_b" in sub.nodes
    assert any(
        e.subject == "entity_a" and e.object == "entity_b" for e in sub.edges
    )


async def test_edge_invalidate_keeps_history(vault):
    e = Edge(
        id=new_edge_id(),
        space_id=vault.space_id,
        subject="x",
        predicate="links-to",
        object="y",
    )
    eid = await vault.edge_add(e)
    await vault.edge_invalidate(eid)
    # Active query should not return it
    active = await vault.graph_query(entity="x", include_invalid=False)
    assert not any(e.id == eid for e in active.edges)
    # But timeline should still have it
    timeline = await vault.graph_timeline("x")
    assert any(e.id == eid for e in timeline), "edge must remain in history"


async def test_graph_traverse_bfs(vault):
    # Build a chain: a -> b -> c
    for s, o in [("a", "b"), ("b", "c")]:
        e = Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject=s,
            predicate="links-to",
            object=o,
        )
        await vault.edge_add(e)
    sub = await vault.graph_traverse("a", hop=2, mode="bfs")
    assert "a" in sub.nodes
    assert "b" in sub.nodes
    assert "c" in sub.nodes


async def test_graph_backlinks(vault):
    # edge: a -> b ; backlinks of b should include this edge
    e = Edge(
        id=new_edge_id(),
        space_id=vault.space_id,
        subject="a",
        predicate="links-to",
        object="b",
    )
    await vault.edge_add(e)
    backlinks = await vault.graph_backlinks("b")
    assert any(e.subject == "a" for e in backlinks)


async def test_reindex_l2(vault):
    # Create a doc with wikilinks
    content = """---
type: concept
title: Reindex Test
created: 2026-06-23
updated: 2026-06-23
---

Links to [[alpha]] and [[beta]].
"""
    await vault.doc_create(path="concepts/reindex.md", content=content)

    # Invalidate all edges
    from datetime import datetime

    # Reindex L2
    report = await vault.reindex(layer="L2")
    assert report.edges_built >= 1

    # After reindex, edges should exist
    sub = await vault.graph_query(entity="Reindex Test")
    assert any(
        e.object in ("alpha", "beta") for e in sub.edges
    ), "reindex must rebuild edges from L1 wikilinks"


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------


async def test_write_lock_exclusion(vault):
    """Two concurrent acquire_write_lock calls must serialize."""
    lock1 = await vault.acquire_write_lock(timeout=5)
    try:
        # Second acquire should time out
        try:
            await asyncio.wait_for(
                vault.acquire_write_lock(timeout=1), timeout=2.0
            )
            raise ConformanceFailure(
                "second acquire_write_lock should have timed out"
            )
        except (TimeoutError, asyncio.TimeoutError):
            pass  # expected
    finally:
        await lock1.release()

    # After release, can acquire again
    lock2 = await vault.acquire_write_lock(timeout=5)
    await lock2.release()


async def test_event_pubsub(vault):
    received: list[ChangeEvent] = []

    async def callback(event: ChangeEvent):
        received.append(event)

    sub = await vault.subscribe_events(callback)
    try:
        v = Verbat.create(
            space_id=vault.space_id,
            content="event test",
            source_file="evt.txt",
            extract_mode=ExtractMode.UPLOAD,
        )
        await vault.verbat_add(v)
        # Give the subscriber a moment to drain
        await asyncio.sleep(0.1)
        assert any(e.layer == "L0" and e.op == "create" for e in received), (
            f"expected L0 create event, got: {received}"
        )
    finally:
        sub.cancel()


async def test_embedder_identity(vault):
    # First set: unknown -> known_match
    await vault.set_embedder_identity("test-model", 384)
    ident = await vault.get_embedder_identity()
    assert ident is not None
    assert ident.model_name == "test-model"
    assert ident.dimension == 384

    # Mismatch without force_swap: should raise
    try:
        await vault.set_embedder_identity("other-model", 768)
        raise ConformanceFailure("mismatch should have raised")
    except Exception as e:
        if "mismatch" not in str(e).lower() and "identity" not in str(e).lower():
            raise

    # Force swap: should succeed
    await vault.set_embedder_identity("other-model", 768, force_swap=True)
    ident = await vault.get_embedder_identity()
    assert ident.model_name == "other-model"
    assert ident.dimension == 768
