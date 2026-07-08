"""RFC-005 Phase 2 end-to-end: cross-document entity curation.

Scenario A: upload three docs about "风控模型A" (D1, D2 consistent, D3
contradicts). Verify entity pages are created/merged/superseded with
`about` edges anchoring the source docs — the real cross-document link.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from derisk.knowledge.types import ExtractMode, Space, new_space_id
from derisk_ext.knowledge.extractors.registry_init import register_builtin_extractors
from derisk_ext.knowledge.vaultfs import LocalVaultFS

ENTITY_NAME = "风控模型A"


def _wiki_md(title: str, body: str) -> str:
    return f"---\ntype: source\ntitle: {title}\n---\n\n# {title}\n\n{body}\n"


def _entity_md(name: str, desc: str, body: str) -> str:
    return (
        f"---\ntype: entity\ntitle: {name}\ndescription: {desc}\n---\n\n"
        f"# {name}\n\n{body}\n"
    )


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    root = tmp_path / "ks_curation"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


@pytest.fixture
def space(vault):
    return Space(
        id=vault.space_id,
        slug="test-curation",
        name="Curation Test",
        default_agent_id=None,
        llm_model=None,
        multimodal_model=None,
    )


@pytest.fixture(autouse=True, scope="module")
def _ensure_builtins():
    register_builtin_extractors()
    yield


def _make_stub(wiki_md: str, curation_json: str):
    """Stub _call_llm: route by system_prompt content."""
    async def _stub(self, model, system_prompt, user_prompt, image_paths=None, **kwargs):
        if system_prompt and "实体归并" in system_prompt:
            return curation_json
        return wiki_md

    return _stub


async def _wait(orch, job_id, timeout=8.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = orch.jobs.get(job_id)
        if job and job.status in ("done", "failed"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} timed out")


async def _ingest(orch, space, vault, tmp_path, filename: str, content: str,
                  wiki_md: str, curation_json: str, monkeypatch):
    from derisk_serve.knowledge.ingest import IngestOrchestrator
    monkeypatch.setattr(
        IngestOrchestrator, "_call_llm", _make_stub(wiki_md, curation_json)
    )
    f = tmp_path / filename
    f.write_text(content, encoding="utf-8")
    job = await orch.ingest_file(
        space=space, vault=vault, file_path=f, original_filename=filename
    )
    finished = await _wait(orch, job.id)
    assert finished.status == "done", f"job failed: {finished.error}"
    return finished


@pytest.mark.asyncio
async def test_scenario_a_new_merge_supersede(vault, space, tmp_path: Path, monkeypatch):
    from derisk_serve.knowledge.ingest import IngestOrchestrator
    from derisk.knowledge.types import Edge

    orch = IngestOrchestrator(system_app=None)

    # D1: first doc -> new entity page + about edge to D1
    d1_finished = await _ingest(
        orch, space, vault, tmp_path, "d1.txt", "风控模型A 的基本介绍",
        wiki_md=_wiki_md("D1", "风控模型A 是一个评分卡模型。"),
        curation_json='{"entities": [{"name": "'
        + ENTITY_NAME
        + '", "action": "new", "new_body": "'
        + _entity_md(ENTITY_NAME, "评分卡模型", "风控模型A 是一个评分卡模型。").replace('"', '\\"').replace("\n", "\\n")
        + '"}]}',
        monkeypatch=monkeypatch,
    )
    d1_id = d1_finished.wiki_doc_ids[0]

    # entity page exists + about edge D-ent -> D1
    ents = await vault.doc_list(type="entity", limit=50)
    assert len(ents) == 1
    ent_path = ents[0].path
    g = await vault.graph_query(
        entity=f"doc:{ents[0].id}", predicate="about", include_invalid=False
    )
    assert any(e.object == f"doc:{d1_id}" for e in g.edges)

    # D2: consistent doc -> merge (no second entity page), about edge to D2 too
    d2_finished = await _ingest(
        orch, space, vault, tmp_path, "d2.txt", "风控模型A 的训练细节",
        wiki_md=_wiki_md("D2", "风控模型A 用 XGBoost 训练。"),
        curation_json='{"entities": [{"name": "'
        + ENTITY_NAME
        + '", "action": "merge", "existing_path": "' + ent_path + '", "merged_body": "'
        + _entity_md(ENTITY_NAME, "评分卡模型", "风控模型A 是评分卡模型，用 XGBoost 训练。").replace('"', '\\"').replace("\n", "\\n")
        + '"}]}',
        monkeypatch=monkeypatch,
    )
    d2_id = d2_finished.wiki_doc_ids[0]

    ents2 = await vault.doc_list(type="entity", limit=50)
    assert len(ents2) == 1, "D2 should merge into existing entity, not create a new one"
    # both D1 and D2 anchored via active about edges
    g2 = await vault.graph_query(
        entity=f"doc:{ents2[0].id}", predicate="about", include_invalid=False
    )
    about_objs = {e.object for e in g2.edges}
    assert f"doc:{d1_id}" in about_objs, "merge must preserve old about edge"
    assert f"doc:{d2_id}" in about_objs, "merge must add new about edge"

    # D3: contradicts -> supersede; new entity page + supersedes edge,
    # old entity's about edges invalidated
    d3_finished = await _ingest(
        orch, space, vault, tmp_path, "d3.txt", "风控模型A 其实是规则引擎",
        wiki_md=_wiki_md("D3", "风控模型A 是规则引擎不是评分卡。"),
        curation_json='{"entities": [{"name": "'
        + ENTITY_NAME
        + '", "action": "supersede", "existing_path": "' + ent_path + '", "new_body": "'
        + _entity_md(ENTITY_NAME, "规则引擎", "风控模型A 是规则引擎。").replace('"', '\\"').replace("\n", "\\n")
        + '", "reason": "contradicts scoring-card claim"}]}',
        monkeypatch=monkeypatch,
    )
    d3_id = d3_finished.wiki_doc_ids[0]

    ents3 = await vault.doc_list(type="entity", limit=50)
    assert len(ents3) == 2, "supersede should create a second entity page"

    # Find new vs old
    new_ent = [e for e in ents3 if e.path != ent_path][0]
    old_ent = [e for e in ents3 if e.path == ent_path][0]

    # supersedes edge: new -> old
    g3 = await vault.graph_query(
        entity=f"doc:{new_ent.id}", predicate="supersedes", include_invalid=False
    )
    assert any(e.object == f"doc:{old_ent.id}" for e in g3.edges)

    # old entity's about edges are now invalid (valid_to set)
    g_old_all = await vault.graph_query(
        entity=f"doc:{old_ent.id}", predicate="about", include_invalid=True
    )
    g_old_active = await vault.graph_query(
        entity=f"doc:{old_ent.id}", predicate="about", include_invalid=False
    )
    assert len(g_old_active.edges) == 0, "old entity about edges should be invalidated"
    assert len(g_old_all.edges) >= 1, "old entity about edges kept in history"

    # new entity anchored to D3
    g_new = await vault.graph_query(
        entity=f"doc:{new_ent.id}", predicate="about", include_invalid=False
    )
    assert any(e.object == f"doc:{d3_id}" for e in g_new.edges)