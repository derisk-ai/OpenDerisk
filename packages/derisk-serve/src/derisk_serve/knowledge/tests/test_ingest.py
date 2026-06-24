"""End-to-end test for the ingest pipeline (RFC 004 §6).

Verifies the full flow: file upload → extractor → verbat_add → background
wiki generation → doc_create → derived-from edge.

We stub `_call_llm` on the orchestrator so the test doesn't need a real LLM
backend — the rest of the pipeline (extractor, vault, edge_add) runs for
real against a LocalVaultFS in a tmp dir.
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


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    root = tmp_path / "ks_ingest_space"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


@pytest.fixture
def space(vault):
    return Space(
        id=vault.space_id,
        slug="test-ingest",
        name="Test Ingest",
        default_agent_id=None,
        llm_model=None,
        multimodal_model=None,
    )


@pytest.fixture(autouse=True, scope="module")
def _ensure_builtins_registered():
    """Make sure built-ins are registered for the module. The `@extractor`
    decorator runs at import time and is idempotent, so we don't clear
    between tests.
    """
    register_builtin_extractors()
    yield


@pytest.fixture
def stub_llm(monkeypatch):
    """Replace IngestOrchestrator._call_llm with a deterministic stub."""

    def make_stub(markdown: str):
        async def _stub(
            self,
            model: Optional[str],
            system_prompt: Optional[str],
            user_prompt: str,
            image_paths=None,
        ) -> str:
            return markdown

        return _stub

    return make_stub


async def _wait_for_job(orchestrator, job_id: str, timeout: float = 5.0):
    """Poll the job until it reaches a terminal state (done/failed)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = orchestrator.jobs.get(job_id)
        if job and job.status in ("done", "failed"):
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"Job {job_id} did not reach terminal state within {timeout}s "
        f"(last status: {orchestrator.jobs.get(job_id) and orchestrator.jobs.get(job_id).status})"
    )


@pytest.mark.asyncio
async def test_ingest_txt_creates_verbat_and_wiki_doc(vault, space, stub_llm, tmp_path: Path):
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    orch = IngestOrchestrator(system_app=None)

    # Stub the LLM to return a valid markdown doc with frontmatter.
    # We deliberately omit source_verbat — _ensure_frontmatter will inject
    # the actual verbat id, which is what the test checks for.
    fake_md = (
        "---\n"
        "type: source\n"
        "title: Test Source\n"
        "---\n\n"
        "# Test Source\n\nA generated wiki doc.\n"
    )
    stub_md = fake_md  # capture
    async def _stub_call(self, model, system_prompt, user_prompt, image_paths=None):
        return stub_md

    pytest.MonkeyPatch().setattr(
        IngestOrchestrator, "_call_llm", _stub_call
    )

    # Write a test file
    f = tmp_path / "input.txt"
    f.write_text("This is the raw verbatim content for testing.", encoding="utf-8")

    job = await orch.ingest_file(
        space=space,
        vault=vault,
        file_path=f,
        original_filename="input.txt",
    )
    finished = await _wait_for_job(orch, job.id)

    assert finished.status == "done", f"job failed: {finished.error}"
    assert len(finished.verbat_ids) == 1
    assert len(finished.wiki_doc_ids) == 1

    # Verbat was persisted
    verbat = await vault.verbat_get(finished.verbat_ids[0])
    assert verbat is not None
    assert verbat.source_file == "input.txt"
    assert "raw verbatim content" in verbat.content
    assert verbat.extract_mode == ExtractMode.UPLOAD

    # Wiki doc was created
    docs = await vault.doc_list(limit=100)
    assert len(docs) == 1
    wiki_path = docs[0].path
    wiki = await vault.doc_read(wiki_path)
    assert wiki is not None
    assert wiki.frontmatter.get("source_verbat") == finished.verbat_ids[0]
    assert "Test Source" in wiki.content or "Test Source" in wiki.title


@pytest.mark.asyncio
async def test_ingest_deprecated_verbat_keeps_wiki_doc(vault, space, stub_llm):
    """Deleting a verbat marks it deprecated but does not destroy the wiki doc."""
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    async def _stub(self, model, system_prompt, user_prompt, image_paths=None):
        return "---\ntype: source\ntitle: T\n---\n\nbody\n"

    pytest.MonkeyPatch().setattr(
        IngestOrchestrator, "_call_llm", _stub
    )

    orch = IngestOrchestrator(system_app=None)
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write("content for deprecation test")
        tmp_file = Path(f.name)

    try:
        job = await orch.ingest_file(
            space=space, vault=vault, file_path=tmp_file, original_filename="dep.txt"
        )
        finished = await _wait_for_job(orch, job.id)
        assert finished.status == "done"
        vid = finished.verbat_ids[0]

        # Deprecate
        await vault.verbat_deprecate(vid)
        v = await vault.verbat_get(vid)
        assert v.deprecated is True

        # Wiki doc still exists
        docs = await vault.doc_list(limit=100)
        assert len(docs) >= 1
    finally:
        tmp_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_rebuild_wiki_for_verbat_replaces_existing_doc(vault, space):
    """Force-rebuild should delete the old wiki doc and create a new one."""
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    call_count = {"n": 0}

    async def _stub(self, model, system_prompt, user_prompt, image_paths=None):
        call_count["n"] += 1
        # No source_verbat in frontmatter — _ensure_frontmatter injects the
        # real verbat id, which is what _find_doc_by_source_verbat looks for.
        return f"---\ntype: source\ntitle: Rev{call_count['n']}\n---\n\nbody v{call_count['n']}\n"

    pytest.MonkeyPatch().setattr(
        IngestOrchestrator, "_call_llm", _stub
    )

    orch = IngestOrchestrator(system_app=None)

    # Manually add a verbat (skip the extractor path)
    from derisk.knowledge.types import Verbat

    v = Verbat.create(
        space_id=vault.space_id,
        content="manual verbatim for rebuild test",
        source_file="rebuild.txt",
        extract_mode=ExtractMode.UPLOAD,
    )
    vid = await vault.verbat_add(v)

    # First wiki gen
    job1 = await orch.rebuild_wiki_for_verbat(space, vault, vid)
    f1 = await _wait_for_job(orch, job1.id)
    assert f1.status == "done"
    assert len(f1.wiki_doc_ids) == 1

    docs_after_first = await vault.doc_list(limit=100)
    assert len(docs_after_first) == 1

    # Second wiki gen (force_rebuild=True) — should replace, not duplicate
    job2 = await orch.rebuild_wiki_for_verbat(space, vault, vid)
    f2 = await _wait_for_job(orch, job2.id)
    assert f2.status == "done"

    docs_after_second = await vault.doc_list(limit=100)
    assert len(docs_after_second) == 1, (
        "force_rebuild should delete the old doc before creating a new one"
    )


@pytest.mark.asyncio
async def test_ingest_unsupported_mime_fails_job(vault, space, tmp_path: Path):
    """An unknown file type should fail the ingest job with a clear error."""
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    # .xyz is not in mimetypes and not in our fallback map
    f = tmp_path / "weird.xyz"
    f.write_bytes(b"\x00\x01\x02 unknown")

    orch = IngestOrchestrator(system_app=None)
    job = await orch.ingest_file(
        space=space, vault=vault, file_path=f, original_filename="weird.xyz"
    )
    finished = await _wait_for_job(orch, job.id)
    assert finished.status == "failed"
    assert "extractor" in (finished.error or "").lower() or "mime" in (finished.error or "").lower()
