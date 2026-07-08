"""RFC-005 Phase 1 tests: space_type abstraction + schema selection.

Verifies that create_space(space_type=...) selects the right schema.md
(personal vs agent_memory) and persists space_type so it survives a reopen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from derisk.component import SystemApp
from derisk.knowledge.schema import parse_schema, validate_predicate
from derisk_serve.knowledge.config import ServeConfig
from derisk_serve.knowledge.service.service import Service


@pytest_asyncio.fixture
async def service(tmp_path: Path):
    cfg = ServeConfig()
    cfg.local_root = str(tmp_path / "spaces")
    Path(cfg.local_root).mkdir(parents=True, exist_ok=True)
    svc = Service(system_app=SystemApp(), serve_config=cfg)
    yield svc
    await svc.close_all()


@pytest.mark.asyncio
async def test_personal_space_schema_has_entity_curation_predicates(service):
    """RFC-005: personal schema includes entity-curation predicates so
    cross-doc entity linking works in both space forms."""
    res = await service.create_space(slug="personal-1", backend="local")
    assert res["space_type"] == "personal"

    vault = await service.get_vault("personal-1")
    schema = parse_schema(await vault.read_schema_md())
    for pred in ("about", "relates-to", "supersedes", "merged-into"):
        assert validate_predicate(schema, pred) is True, f"{pred} missing"
    # personal carries the source page type; memory schema drops it
    assert "source" in schema.page_types


@pytest.mark.asyncio
async def test_agent_memory_space_schema_has_memory_predicates(service):
    res = await service.create_space(
        slug="mem-1", backend="local", space_type="agent_memory"
    )
    assert res["space_type"] == "agent_memory"

    vault = await service.get_vault("mem-1")
    schema = parse_schema(await vault.read_schema_md())
    for pred in ("merged-into", "supersedes", "about", "relates-to"):
        assert validate_predicate(schema, pred) is True, f"{pred} missing"


@pytest.mark.asyncio
async def test_agent_memory_edge_add_supersedes_accepted(service):
    """agent_memory schema must allow edge_add(predicate='supersedes')."""
    from derisk.knowledge.types import Edge, new_edge_id

    await service.create_space(
        slug="mem-2", backend="local", space_type="agent_memory"
    )
    vault = await service.get_vault("mem-2")
    eid = await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject="doc:old",
            predicate="supersedes",
            object="doc:new",
        )
    )
    assert eid


@pytest.mark.asyncio
async def test_personal_edge_add_supersedes_accepted(service):
    """RFC-005: personal schema also allows supersedes (entity curation is
    form-agnostic). The two forms differ in page types (memory/insight vs
    source), not in curation predicates."""
    from derisk.knowledge.types import Edge, new_edge_id

    await service.create_space(slug="personal-2", backend="local")
    vault = await service.get_vault("personal-2")
    eid = await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject="doc:old",
            predicate="supersedes",
            object="doc:new",
        )
    )
    assert eid


@pytest.mark.asyncio
async def test_space_type_persists_across_reopen(service, tmp_path: Path):
    """space_type must survive dropping the in-memory cache and re-resolving."""
    await service.create_space(
        slug="mem-3", backend="local", space_type="agent_memory"
    )
    # Drop in-memory cache to force re-resolve from SQLite
    service._vaults.pop("mem-3", None)
    service._spaces.pop("mem-3", None)

    space = await service.get_space_config("mem-3")
    assert space.space_type == "agent_memory"