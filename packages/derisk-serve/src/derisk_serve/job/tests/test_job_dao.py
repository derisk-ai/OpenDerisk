"""JobDao claim/consume unit tests (SQLite fallback path — exercises the
atomic conditional UPDATE since the test DB has no SKIP LOCKED)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from derisk_serve.job.api.schemas import ServeRequest
from derisk_serve.job.models.models import JobDao


@pytest.fixture
def dao(tmp_path):
    """A JobDao backed by an isolated SQLite file (no SKIP LOCKED → exercises
    the atomic conditional UPDATE fallback path)."""
    from sqlalchemy import create_engine
    from derisk.storage.metadata import DatabaseManager
    from derisk_serve.job.models.models import JobEntity

    mgr = DatabaseManager.build_from(
        f"sqlite:///{tmp_path}/job.db", base=None
    )
    # Ensure the job table exists on this isolated engine.
    JobEntity.__table__.create(mgr._engine, checkfirst=True)
    return JobDao(db_manager=mgr)


def _submit(dao, job_type="t", priority=5, max_attempts=3, payload=None):
    return dao.submit(ServeRequest(
        job_type=job_type, payload=payload or {}, priority=priority, max_attempts=max_attempts,
    ))


@pytest.mark.asyncio
async def test_claim_next_priority_order(dao):
    _submit(dao, priority=9)   # lower priority
    _submit(dao, priority=1)   # highest
    _submit(dao, priority=5)

    j1 = dao.claim_next(["t"], "w1", 300)
    j2 = dao.claim_next(["t"], "w1", 300)
    j3 = dao.claim_next(["t"], "w1", 300)
    j4 = dao.claim_next(["t"], "w1", 300)

    assert j1.priority == 1
    assert j2.priority == 5
    assert j3.priority == 9
    assert j4 is None
    # claimed + attempts incremented
    assert j1.status == "running"
    assert j1.claimed_by == "w1"
    assert j1.attempts == 1
    assert j1.lease_until is not None


@pytest.mark.asyncio
async def test_ack_sets_done(dao):
    e = _submit(dao)
    dao.claim_next(["t"], "w1", 300)
    ok = dao.ack(e.id, {"verbat_ids": ["v1"]})
    assert ok is True
    row = dao.get(e.id)
    assert row.status == "done"
    assert row.result == {"verbat_ids": ["v1"]}
    assert row.claimed_by is None


@pytest.mark.asyncio
async def test_nack_requeue_then_fail(dao):
    e = _submit(dao, max_attempts=2)
    # 1st attempt
    dao.claim_next(["t"], "w1", 300)
    st = dao.nack(e.id, "boom1")
    assert st == "pending"   # attempts=1 < max=2
    row = dao.get(e.id)
    assert row.status == "pending"
    assert "boom1" in row.last_error
    # 2nd attempt (claim increments attempts to 2)
    dao.claim_next(["t"], "w2", 300)
    st2 = dao.nack(e.id, "boom2")
    assert st2 == "failed"   # attempts=2 >= max=2
    assert dao.get(e.id).status == "failed"


@pytest.mark.asyncio
async def test_reclaim_stalled(dao):
    e = _submit(dao)
    dao.claim_next(["t"], "w1", 300)
    # Simulate lease expiry by backdating lease_until
    from derisk_serve.job.models.models import JobEntity
    with dao.session() as session:
        session.query(JobEntity).filter(JobEntity.id == e.id).update(
            {"lease_until": datetime.utcnow() - timedelta(seconds=10)}
        )
    reclaimed = dao.reclaim_stalled(["t"], datetime.utcnow())
    assert reclaimed == 1
    row = dao.get(e.id)
    assert row.status == "pending"
    assert row.claimed_by is None


@pytest.mark.asyncio
async def test_concurrent_claim_no_double(dao):
    """Two coroutines claiming on SQLite — the `AND status='pending'` guard
    ensures only one wins each row, no double-consumption."""
    _submit(dao)
    _submit(dao)
    import asyncio

    async def claim(wid):
        return await asyncio.to_thread(dao.claim_next, ["t"], wid, 300)

    r1, r2 = await asyncio.gather(claim("w1"), claim("w2"))
    claimed_ids = {r1.id, r2.id} if r1 and r2 else set()
    assert r1 is not None and r2 is not None
    assert r1.id != r2.id, "two workers must get distinct jobs"
    # third claim returns None
    r3 = await asyncio.to_thread(dao.claim_next, ["t"], "w1", 300)
    assert r3 is None


@pytest.mark.asyncio
async def test_retry_and_cancel(dao):
    e = _submit(dao)
    dao.claim_next(["t"], "w1", 300)
    dao.nack(e.id, "x")
    # burn attempts to fail it (max_attempts=3 → need 3 claims)
    dao.claim_next(["t"], "w1", 300)
    dao.nack(e.id, "x")
    dao.claim_next(["t"], "w1", 300)
    dao.nack(e.id, "x")
    assert dao.get(e.id).status == "failed"

    # retry resets to pending
    row = dao.retry(e.id)
    assert row.status == "pending"
    assert row.last_error is None

    # cancel a pending job
    ok = dao.cancel(e.id)
    assert ok is True
    assert dao.get(e.id).status == "failed"


@pytest.mark.asyncio
async def test_stats(dao):
    fa = _submit(dao, job_type="a")
    _submit(dao, job_type="b")
    _submit(dao, job_type="a")
    # claim + ack the first 'a' so we have one done, two pending
    claimed = dao.claim_next(["a"], "w1", 300)
    assert claimed.id == fa.id
    dao.ack(claimed.id, None)
    s = dao.stats()
    assert s["total"] == 3
    assert s["by_type"]["a"] == 2
    assert s["by_type"]["b"] == 1
    assert s["by_status"]["done"] == 1
    assert s["by_status"]["pending"] == 2