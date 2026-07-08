"""RFC-005: valid_to binding at edge INSERT time.

Regression: both local and (formerly) distributed backends hardcoded
valid_to=NULL in the INSERT SQL, silently dropping any caller-supplied
valid_to. This test pins the fix: an edge created with valid_to in the
past is born expired and filtered out by include_invalid=False.
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
    root = tmp_path / "vt_space"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


@pytest.mark.asyncio
async def test_edge_born_expired_is_filtered(vault):
    past_dt = datetime.utcnow() - timedelta(days=1)
    eid = await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject="doc:a",
            predicate="links-to",
            object="doc:b",
            valid_to=past_dt,
        )
    )

    # include_invalid=False -> born-expired edge hidden
    g_active = await vault.graph_query(
        entity="doc:a", predicate="links-to", include_invalid=False
    )
    assert all(e.id != eid for e in g_active.edges)

    # include_invalid=True -> visible with valid_to set
    g_all = await vault.graph_query(
        entity="doc:a", predicate="links-to", include_invalid=True
    )
    matched = [e for e in g_all.edges if e.id == eid]
    assert len(matched) == 1
    assert matched[0].valid_to is not None
    assert matched[0].valid_to.isoformat() == past_dt.isoformat()


@pytest.mark.asyncio
async def test_edge_active_when_valid_to_none(vault):
    eid = await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject="doc:c",
            predicate="links-to",
            object="doc:d",
        )
    )
    g = await vault.graph_query(
        entity="doc:c", predicate="links-to", include_invalid=False
    )
    assert any(e.id == eid for e in g.edges)