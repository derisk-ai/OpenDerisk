"""Job engine v2 features: scheduling (not_before), worker affinity
(required_worker), execution records (executed_by/at + attempts_history),
and worker subscribe_types."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine

from derisk.storage.metadata import DatabaseManager
from derisk_serve.job.api.schemas import ServeRequest
from derisk_serve.job.models.models import JobDao, JobEntity
from derisk_serve.job.config import ServeConfig
from derisk_serve.job.service.service import Service as JobService


@pytest.fixture
def dao(tmp_path):
    mgr = DatabaseManager.build_from(f"sqlite:///{tmp_path}/jv2.db", base=None)
    JobEntity.__table__.create(mgr._engine, checkfirst=True)
    return JobDao(db_manager=mgr)


def _submit(dao, **kw):
    return dao.submit(ServeRequest(job_type=kw.get("job_type", "t"), payload={}, **{k: v for k, v in kw.items() if k != "job_type"}))


# ---- not_before (scheduling) ----

@pytest.mark.asyncio
async def test_not_before_blocks_claim(dao):
    """A job scheduled in the future is not claimable until not_before passes."""
    future = (datetime.utcnow() + timedelta(seconds=60)).isoformat()
    _submit(dao, not_before=future)
    # claim now → None (not_before in the future)
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"default"})
    assert got is None, "future-scheduled job must not be claimable"


@pytest.mark.asyncio
async def test_not_before_past_claimable(dao):
    past = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    _submit(dao, not_before=past)
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"default"})
    assert got is not None
    assert got.status == "running"


@pytest.mark.asyncio
async def test_run_after_seconds_resolves(dao):
    _submit(dao, run_after_seconds=3600)  # 1h from now
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"default"})
    assert got is None
    row = dao.list_jobs(limit=10)[0]
    assert row.not_before is not None


@pytest.mark.asyncio
async def test_no_not_before_claimable_immediately(dao):
    _submit(dao)
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"default"})
    assert got is not None


# ---- required_worker (affinity) ----

@pytest.mark.asyncio
async def test_required_worker_blocks_unmatched_worker(dao):
    _submit(dao, required_worker=["gpu"])
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"knowledge"})  # no gpu tag
    assert got is None, "worker without required tag must not claim"


@pytest.mark.asyncio
async def test_required_worker_allows_matched_worker(dao):
    _submit(dao, required_worker=["gpu"])
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"knowledge", "gpu"})
    assert got is not None
    assert got.claimed_by == "w1"


@pytest.mark.asyncio
async def test_required_worker_empty_any_worker(dao):
    _submit(dao, required_worker=None)
    got = dao.claim_next(["t"], "w1", 300, worker_tags={"default"})
    assert got is not None


# ---- executed_by / attempts_history ----

@pytest.mark.asyncio
async def test_ack_records_executor(dao):
    e = _submit(dao)
    dao.claim_next(["t"], "worker-A", 300, worker_tags={"default"})
    ok = dao.ack(e.id, {"done": True})
    assert ok is True
    row = dao.get(e.id)
    assert row.status == "done"
    assert row.executed_by == "worker-A"
    assert row.executed_at is not None
    assert row.claimed_by is None  # cleared, but executed_by preserved
    assert row.attempts_history is not None and len(row.attempts_history) >= 1
    # the last attempt record reflects done
    last = row.attempts_history[-1]
    assert last["worker"] == "worker-A"
    assert last["status"] == "done"


@pytest.mark.asyncio
async def test_nack_records_executor_and_history(dao):
    e = _submit(dao, max_attempts=2)
    # 1st attempt: claim by worker-A, nack → pending (attempts=1 < max=2)
    dao.claim_next(["t"], "worker-A", 300, worker_tags={"default"})
    st = dao.nack(e.id, "boom1")
    assert st == "pending"
    row = dao.get(e.id)
    assert row.executed_by == "worker-A"
    assert len(row.attempts_history) == 1

    # 2nd attempt: claim by worker-B, nack → failed (attempts=2 >= max=2)
    dao.claim_next(["t"], "worker-B", 300, worker_tags={"default"})
    st2 = dao.nack(e.id, "boom2")
    assert st2 == "failed"
    row = dao.get(e.id)
    assert row.executed_by == "worker-B"  # last executor
    assert len(row.attempts_history) == 2
    workers = [a["worker"] for a in row.attempts_history]
    assert workers == ["worker-A", "worker-B"]
    statuses = [a["status"] for a in row.attempts_history]
    assert "failed" in statuses


@pytest.mark.asyncio
async def test_stats_by_executor(dao):
    e1 = _submit(dao, job_type="a")
    e2 = _submit(dao, job_type="b")
    dao.claim_next(["a", "b"], "wX", 300, worker_tags={"default"})
    dao.claim_next(["a", "b"], "wX", 300, worker_tags={"default"})
    dao.ack(e1.id, None)
    dao.ack(e2.id, None)
    s = dao.stats()
    assert s["by_executor"].get("wX") == 2


# ---- worker subscribe_types ----

@pytest.mark.asyncio
async def test_worker_subscribe_types(tmp_path):
    """A worker with subscribe_types=['a'] only consumes type 'a', not 'b'."""
    mgr = DatabaseManager.build_from(f"sqlite:///{tmp_path}/sub.db", base=None)
    JobEntity.__table__.create(mgr._engine, checkfirst=True)
    dao = JobDao(db_manager=mgr)
    cfg = ServeConfig(enabled=True, poll_interval_seconds=0.05,
                      lease_seconds=60, concurrency=2, subscribe_types="a")
    from derisk.component import SystemApp
    svc = JobService(system_app=SystemApp(), config=cfg, dao=dao)

    ran = []
    async def handler_a(job):
        ran.append(("a", job.id))
    async def handler_b(job):
        ran.append(("b", job.id))
    svc.register_handler("a", handler_a)
    svc.register_handler("b", handler_b)
    # worker subscribes only to 'a' → _subscribed_types should be ['a']
    assert set(svc._subscribed_types()) == {"a"}

    await svc.start()
    try:
        jid_a = await svc.submit("a", {})
        jid_b = await svc.submit("b", {})
        import asyncio
        # wait for 'a' to be consumed
        deadline = asyncio.get_event_loop().time() + 3
        while asyncio.get_event_loop().time() < deadline:
            if svc.get(jid_a) and svc.get(jid_a).status == "done":
                break
            await asyncio.sleep(0.05)
        # 'b' must remain pending (no worker subscribes to it)
        row_b = svc.get(jid_b)
        assert row_b.status == "pending", f"b should not be consumed, status={row_b.status}"
        assert any(t == "a" for t, _ in ran)
        assert not any(t == "b" for t, _ in ran)
    finally:
        await svc.stop()