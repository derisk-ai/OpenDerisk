"""RFC-005: knowledge ingest via the persistent job engine (end-to-end)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
import pytest_asyncio

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager
from derisk_serve.job.config import ServeConfig as JobServeConfig
from derisk_serve.job.models.models import JobDao, JobEntity
from derisk_serve.job.service.service import Service as JobService
from derisk_serve.knowledge.config import ServeConfig as KnowledgeServeConfig
from derisk_serve.knowledge.service.service import Service as KnowledgeService
from derisk_ext.knowledge.extractors.registry_init import register_builtin_extractors


def _wiki_md(title, body):
    return f"---\ntype: source\ntitle: {title}\nsource_verbat: x\n---\n\n# {title}\n\n{body}\n"


def _stub_llm(monkeypatch, wiki_md_text, curation_json):
    async def _stub(self, model, system_prompt, user_prompt, image_paths=None, **kwargs):
        if system_prompt and "实体归并" in system_prompt:
            return curation_json
        return wiki_md_text
    from derisk_serve.knowledge.ingest import IngestOrchestrator
    monkeypatch.setattr(IngestOrchestrator, "_call_llm", _stub)


async def _wait_job_done(job_svc, job_id, timeout=10.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        row = job_svc.get(job_id)
        if row and row.status in ("done", "failed"):
            return row
        await asyncio.sleep(0.05)
    row = job_svc.get(job_id)
    raise AssertionError(
        f"job {job_id} did not finish: status={row.status if row else None} "
        f"err={row.last_error if row else None}"
    )


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    register_builtin_extractors()
    system_app = SystemApp()

    job_db = DatabaseManager.build_from(f"sqlite:///{tmp_path}/job.db", base=None)
    JobEntity.__table__.create(job_db._engine, checkfirst=True)
    job_dao = JobDao(db_manager=job_db)
    job_cfg = JobServeConfig(
        enabled=True, poll_interval_seconds=0.05, lease_seconds=60,
        concurrency=2, max_attempts_default=2,
    )
    job_svc = JobService(system_app=system_app, config=job_cfg, dao=job_dao)
    system_app.register_instance(job_svc)

    kcfg = KnowledgeServeConfig()
    kcfg.local_root = str(tmp_path / "spaces")
    Path(kcfg.local_root).mkdir(parents=True, exist_ok=True)
    ksvc = KnowledgeService(system_app=system_app, serve_config=kcfg)
    ksvc.init_app(system_app)
    system_app.register_instance(ksvc)

    orch = ksvc.orchestrator
    job_svc.register_handler("knowledge_ingest", orch.handle_ingest_job)
    await job_svc.start()

    yield system_app, ksvc, job_svc

    await job_svc.stop()


@pytest.mark.asyncio
async def test_ingest_via_job_engine(env, monkeypatch):
    _, ksvc, job_svc = env
    _stub_llm(monkeypatch, _wiki_md("EngineDoc", "scoring card model details"), '{"entities": []}')

    await ksvc.create_space(slug="eng-1", backend="local")
    vault = await ksvc.get_vault("eng-1")
    space = await ksvc.get_space_config("eng-1")

    raw_path = vault.root / "raw" / "report.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("scoring card raw content for job engine", encoding="utf-8")
    tmp = Path(str(raw_path) + ".tmp")
    shutil.copy2(raw_path, tmp)

    job = await ksvc.orchestrator.ingest_file(
        space=space, vault=vault, file_path=tmp, original_filename="report.txt",
    )
    assert job.id.startswith("job_"), f"expected a DB job id, got {job.id}"
    assert not tmp.exists(), "temp file should be unlinked after submit"

    row = await _wait_job_done(job_svc, job.id)
    assert row.status == "done", f"job failed: {row.last_error}"
    assert row.result and "verbat_ids" in row.result
    assert len(row.result["verbat_ids"]) >= 1
    assert len(row.result["wiki_doc_ids"]) >= 1

    docs = await vault.doc_list(limit=100)
    assert any("EngineDoc" in (d.title or "") for d in docs)
    verbats = await vault.verbat_list(limit=100)
    assert len(verbats) >= 1


@pytest.mark.asyncio
async def test_ingest_restart_resume_idempotent(env, monkeypatch):
    _, ksvc, job_svc = env
    _stub_llm(monkeypatch, _wiki_md("ResumeDoc", "resume scoring card"), '{"entities": []}')

    await ksvc.create_space(slug="eng-2", backend="local")
    vault = await ksvc.get_vault("eng-2")
    space = await ksvc.get_space_config("eng-2")

    raw_path = vault.root / "raw" / "resume.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("resume raw content", encoding="utf-8")

    # Stop worker before ingest so the job sits pending.
    await job_svc.stop()
    # Use a temp copy so ingest_file's unlink doesn't kill the durable raw.
    tmp = Path(str(raw_path) + ".tmp")
    shutil.copy2(raw_path, tmp)
    job = await ksvc.orchestrator.ingest_file(
        space=space, vault=vault, file_path=tmp, original_filename="resume.txt",
    )
    # raw still exists (we passed a temp). Restart the worker.
    await job_svc.start()
    row = await _wait_job_done(job_svc, job.id, timeout=12)
    assert row.status == "done", f"job failed: {row.last_error}"

    verbats = await vault.verbat_list(limit=100)
    assert len(verbats) == 1, f"expected exactly 1 verbat (idempotent), got {len(verbats)}"


@pytest.mark.asyncio
async def test_ingest_jobs_survives_restart(env, monkeypatch):
    _, ksvc, job_svc = env
    _stub_llm(monkeypatch, _wiki_md("PersistDoc", "persist"), '{"entities": []}')

    await ksvc.create_space(slug="eng-3", backend="local")
    vault = await ksvc.get_vault("eng-3")
    space = await ksvc.get_space_config("eng-3")
    raw_path = vault.root / "raw" / "persist.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("persist raw", encoding="utf-8")
    tmp = Path(str(raw_path) + ".tmp")
    shutil.copy2(raw_path, tmp)

    job = await ksvc.orchestrator.ingest_file(
        space=space, vault=vault, file_path=tmp, original_filename="persist.txt",
    )
    await _wait_job_done(job_svc, job.id)

    # Drop in-memory store; DB listing still finds the job.
    ksvc.orchestrator.jobs._jobs.clear()
    rows = await asyncio.to_thread(job_svc.dao.list_for_space, "eng-3", 50)
    assert any(r.id == job.id for r in rows)
    assert all(r.status == "done" for r in rows)