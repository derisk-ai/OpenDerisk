import pytest
import tempfile
import os
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_append_and_get_events_ordered(store):
    for i in range(3):
        e = StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={"i": i},
            seq=i,
            timestamp=float(i),
        )
        await store.append_event(e)
    events = await store.get_events("conv-1")
    assert len(events) == 3
    assert [e.seq for e in events] == [0, 1, 2]


async def test_get_events_since_seq(store):
    for i in range(5):
        e = StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={},
            seq=i,
            timestamp=float(i),
        )
        await store.append_event(e)
    events = await store.get_events("conv-1", since_seq=2)
    assert [e.seq for e in events] == [2, 3, 4]


async def test_set_and_get_step_state(store):
    await store.set_step_state("step-1", "conv-1", StepState.AWAITING_USER, {"input": "x"})
    result = await store.get_step_state("step-1")
    assert result is not None
    state, snapshot = result
    assert state == StepState.AWAITING_USER
    assert snapshot == {"input": "x"}


async def test_get_step_state_returns_none_if_absent(store):
    assert await store.get_step_state("nope") is None


async def test_acquire_and_renew_lease(store):
    assert await store.acquire_lease("conv-1", "agent-1", ttl_seconds=30) is True
    # 同一 conv 被同一 agent 再次 acquire 也算续期成功
    assert await store.renew_lease("conv-1", "agent-1", ttl_seconds=30) is True


async def test_acquire_lease_conflict(store):
    assert await store.acquire_lease("conv-1", "agent-1", ttl_seconds=30) is True
    # 不同 agent 在 lease 未过期时不能抢
    assert await store.acquire_lease("conv-1", "agent-2", ttl_seconds=30) is False


async def test_scan_expired_leases(store):
    await store.acquire_lease("conv-1", "agent-1", ttl_seconds=0)
    # ttl=0 立即过期
    expired = await store.scan_expired_leases()
    assert "conv-1" in expired


async def test_release_lease(store):
    await store.acquire_lease("conv-1", "agent-1", ttl_seconds=30)
    await store.release_lease("conv-1")
    assert await store.acquire_lease("conv-1", "agent-2", ttl_seconds=30) is True
