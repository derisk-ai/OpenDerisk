"""RFC-005: LLM call ledger & token usage stats.

Verifies that ingest records one llm_call_log row per LLM call (with real
token usage captured from ModelOutput.usage), and that the query/summary
APIs + endpoints return correct aggregations.

Stubs AIWrapper.create (NOT _call_llm) so the real collection path runs.
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


def _wiki_md(title: str, body: str) -> str:
    return f"---\ntype: source\ntitle: {title}\n---\n\n{body}\n"


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    root = tmp_path / "ks_usage"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


@pytest.fixture
def space(vault):
    return Space(
        id=vault.space_id,
        slug="test-usage",
        name="Usage Test",
        default_agent_id=None,
        llm_model=None,
        multimodal_model=None,
    )


@pytest.fixture(autouse=True, scope="module")
def _ensure_builtins():
    register_builtin_extractors()
    yield


class _FakeResult:
    """Minimal stand-in for ModelOutput with content + usage + error_code."""
    def __init__(self, text: str, usage: Optional[dict], error_code: int = 0):
        self.content = text
        self.usage = usage
        self.error_code = error_code


def _patch_aiwrapper(monkeypatch, wiki_md_text: str, curation_json: str,
                     wiki_usage: dict, curate_usage: dict):
    """Stub AIWrapper.create to route by system_prompt, shipping usage.

    The real _call_llm reads usage off each yielded result — so this exercises
    the actual collection + ledger-write path.
    """
    async def _fake_create(self, **config):
        msgs = config.get("messages", [])
        sys_prompt = ""
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "system":
                sys_prompt = m.get("content", "")
                break
        if "实体归并" in sys_prompt:
            yield _FakeResult(curation_json, curate_usage)
        else:
            yield _FakeResult(wiki_md_text, wiki_usage)

    from derisk.agent.util.llm.llm_client import AIWrapper
    monkeypatch.setattr(AIWrapper, "create", _fake_create)
    # Register a stub model config so _call_llm's model resolution succeeds
    # without hitting a real provider (AIWrapper.create is stubbed anyway).
    from derisk.agent.util.llm.model_config_cache import ModelConfigCache
    if not ModelConfigCache.has_model("test-model"):
        ModelConfigCache.register_configs({
            "stub/test-model": {
                "provider": "openai", "model": "test-model", "api_key": "sk-x",
                "base_url": "http://x", "protocol": "openai",
            }
        })


async def _wait(orch, job_id, timeout=8.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = orch.jobs.get(job_id)
        if job and job.status in ("done", "failed"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} timed out")


@pytest.mark.asyncio
async def test_ingest_records_llm_calls_with_usage(vault, space, tmp_path, monkeypatch):
    _patch_aiwrapper(
        monkeypatch,
        wiki_md_text=_wiki_md("D1", "scoring card model"),
        curation_json='{"entities": []}',
        wiki_usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
        curate_usage={"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
    )
    from derisk_serve.knowledge.ingest import IngestOrchestrator
    orch = IngestOrchestrator(system_app=None)

    f = tmp_path / "in.txt"
    f.write_text("scoring card raw content", encoding="utf-8")
    job = await orch.ingest_file(
        space=space, vault=vault, file_path=f, original_filename="in.txt"
    )
    finished = await _wait(orch, job.id)
    assert finished.status == "done", finished.error

    rows = await vault.llm_call_log_query(limit=100)
    # one wiki_generate + one entity_curate (entity_curate returns [] but still logs)
    tasks = [r["task_name"] for r in rows]
    assert "wiki_generate" in tasks
    assert "entity_curate" in tasks

    wiki_row = next(r for r in rows if r["task_name"] == "wiki_generate")
    assert wiki_row["prompt_tokens"] == 120
    assert wiki_row["completion_tokens"] == 30
    assert wiki_row["total_tokens"] == 150
    assert wiki_row["model"] != ""
    assert wiki_row["job_id"] == job.id


@pytest.mark.asyncio
async def test_summary_aggregates_by_task_and_model(vault, space, tmp_path, monkeypatch):
    _patch_aiwrapper(
        monkeypatch,
        wiki_md_text=_wiki_md("D2", "another scoring doc"),
        curation_json='{"entities": []}',
        wiki_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        curate_usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    )
    from derisk_serve.knowledge.ingest import IngestOrchestrator
    orch = IngestOrchestrator(system_app=None)
    f = tmp_path / "in2.txt"
    f.write_text("another scoring raw", encoding="utf-8")
    j = await orch.ingest_file(space=space, vault=vault, file_path=f, original_filename="in2.txt")
    await _wait(orch, j.id)

    s = await vault.llm_call_log_summary()
    assert s["total_calls"] >= 2
    assert s["total_tokens"] >= 27
    assert "wiki_generate" in s["by_task"]
    assert "entity_curate" in s["by_task"]
    # by_model keyed by model name
    assert len(s["by_model"]) >= 1


@pytest.mark.asyncio
async def test_query_filter_by_task(vault):
    await vault.llm_call_log_add("j1", "wiki_generate", "m1",
                                 {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, 10, 0)
    await vault.llm_call_log_add("j1", "entity_curate", "m1",
                                 {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6}, 20, 0)
    only_wiki = await vault.llm_call_log_query(task_name="wiki_generate")
    assert len(only_wiki) == 1
    assert only_wiki[0]["task_name"] == "wiki_generate"


@pytest.mark.asyncio
async def test_persists_across_reopen(vault, tmp_path):
    root = vault.root
    await vault.llm_call_log_add("j1", "wiki_generate", "m1",
                                 {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}, 30, 0)
    await vault.close()

    v2 = LocalVaultFS(space_id=vault.space_id, root=root)
    await v2.initialize()
    rows = await v2.llm_call_log_query()
    assert len(rows) == 1
    assert rows[0]["total_tokens"] == 10
    await v2.close()


@pytest.mark.asyncio
async def test_llm_usage_endpoints(vault, space, tmp_path: Path, monkeypatch):
    """End-to-end through the HTTP layer: /llm-usage + /summary."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from derisk_serve.knowledge.api import endpoints as ep
    from derisk.component import SystemApp
    from derisk_serve.knowledge.config import ServeConfig
    from derisk_serve.knowledge.service.service import Service

    # Build a service rooted at the vault's parent so it resolves the same
    # on-disk SQLite (vault.root = <parent>/<slug>).
    cfg = ServeConfig()
    cfg.local_root = str(vault.root.parent)
    svc = Service(system_app=SystemApp(), serve_config=cfg)
    slug2 = vault.root.name
    v2 = await svc.get_vault(slug2)
    await v2.llm_call_log_add("job-x", "wiki_generate", "gpt-4o",
                              {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                              120, 0)
    await v2.llm_call_log_add("job-x", "entity_curate", "gpt-4o",
                              {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
                              90, 0)

    app = FastAPI()
    app.include_router(ep.router)

    async def _get_svc():
        return svc

    app.dependency_overrides[ep.get_service] = _get_svc

    client = TestClient(app)

    r = client.get(f"/spaces/{slug2}/llm-usage/summary")
    assert r.status_code == 200, r.text
    s = r.json()["data"]
    assert s["total_calls"] == 2
    assert s["total_tokens"] == 270
    assert "wiki_generate" in s["by_task"]
    assert "gpt-4o" in s["by_model"]

    r = client.get(f"/spaces/{slug2}/llm-usage?task_name=wiki_generate")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["total_tokens"] == 150
    assert items[0]["task_name"] == "wiki_generate"

    await svc.close_all()
    await vault.close()