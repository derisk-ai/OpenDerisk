"""JobService worker loop tests: concurrency cap, ack/nack dispatch, stall reclaim."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine

from derisk.storage.metadata import DatabaseManager
from derisk_serve.job.config import ServeConfig
from derisk_serve.job.models.models import JobDao, JobEntity
from derisk_serve.job.service.service import Service as JobService


@pytest.fixture
def service(tmp_path):
    mgr = DatabaseManager.build_from(f"sqlite:///{tmp_path}/w.db", base=None)
    JobEntity.__table__.create(mgr._engine, checkfirst=True)
    dao = JobDao(db_manager=mgr)
    cfg = ServeConfig(
        enabled=True, poll_interval_seconds=0.05, lease_seconds=2,
        concurrency=2, max_attempts_default=3,
    )
    from derisk.component import SystemApp
    svc = JobService(system_app=SystemApp(), config=cfg, dao=dao)
    return svc


async def _submit(service, job_type="t", payload=None, max_attempts=3):
    return await service.submit(job_type, payload or {"n": 0}, max_attempts=max_attempts)


@pytest.mark.asyncio
async def test_worker_runs_handler_and_acks(service):
    ran = []
    async def handler(job):
        ran.append(job.id)
        return {"ok": True}
    service.register_handler("t", handler)
    await service.start()
    try:
        jid = await _submit(service)
        await _wait_done(service, jid, timeout=3)
    finally:
        await service.stop()
    assert jid in ran
    row = service.get(jid)
    assert row.status == "done"
    assert row.result == {"ok": True}


@pytest.mark.asyncio
async def test_worker_nacks_on_exception(service):
    async def handler(job):
        raise RuntimeError("boom")
    service.register_handler("t", handler)
    await service.start()
    try:
        jid = await _submit(service, max_attempts=1)
        await _wait_done(service, jid, timeout=3)
    finally:
        await service.stop()
    row = service.get(jid)
    assert row.status == "failed"
    assert "boom" in row.last_error


@pytest.mark.asyncio
async def test_worker_concurrency_cap(service):
    """With concurrency=2, no more than 2 handlers run at once."""
    inflight = 0
    max_inflight = 0
    async def handler(job):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.2)
        inflight -= 1
        return None
    service.register_handler("t", handler)
    await service.start()
    try:
        for _ in range(6):
            await _submit(service)
        # wait for all to finish
        await asyncio.sleep(1.5)
    finally:
        await service.stop()
    assert max_inflight <= 2, f"concurrency exceeded: {max_inflight}"


@pytest.mark.asyncio
async def test_worker_reclaims_stalled(service):
    """A job whose lease already expired (stalled worker) gets reclaimed on
    the next worker tick and then run to completion.

    We manually plant a running+expired-lease row (simulating a crashed
    worker) rather than racing the renew-lease loop, which keeps long jobs
    alive and would never stall.
    """
    runs = []
    async def handler(job):
        runs.append(job.id)
        return {"done": True}
    service.register_handler("t", handler)

    # Plant a stalled job: claimed by a dead worker, lease expired.
    from derisk_serve.job.api.schemas import ServeRequest
    stalled = service.dao.submit(ServeRequest(job_type="t", payload={}, priority=5, max_attempts=3))
    from datetime import datetime, timedelta
    with service.dao.session() as session:
        row = session.query(JobEntity).filter(JobEntity.id == stalled.id).first()
        row.status = "running"
        row.claimed_by = "dead-worker"
        row.claimed_at = datetime.utcnow() - timedelta(seconds=100)
        row.lease_until = datetime.utcnow() - timedelta(seconds=60)  # expired
        row.attempts = 1

    await service.start()
    try:
        await _wait_done(service, stalled.id, timeout=5)
    finally:
        await service.stop()
    assert len(runs) == 1, f"stalled job should be reclaimed and run once, runs={runs}"
    row = service.get(stalled.id)
    assert row.status == "done"


async def _wait_done(service, jid, timeout=5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        row = service.get(jid)
        if row and row.status in ("done", "failed"):
            return row
        await asyncio.sleep(0.05)
    row = service.get(jid)
    raise AssertionError(f"job {jid} did not finish: status={row.status if row else None}")