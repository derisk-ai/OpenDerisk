# packages/derisk-core/tests/agent/core/v2/test_recovery.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.recovery import RecoveryCoordinatorV2
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def recovery():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = DbStateStore(path)
    yield RecoveryCoordinatorV2(store, lease_ttl_seconds=30), store, EventStream(store)
    os.unlink(path)


async def test_acquire_and_renew_lease(recovery):
    rc, store, stream = recovery
    assert await rc.acquire_lease("conv-1", "agent-1") is True
    assert await rc.renew_lease("conv-1", "agent-1") is True


async def test_scan_expired(recovery):
    rc, store, stream = recovery
    # 用 ttl=0 立即过期
    assert await store.acquire_lease("conv-1", "agent-1", ttl_seconds=0) is True
    expired = await rc.scan_expired()
    assert "conv-1" in expired


async def test_get_last_step_state_returns_none_when_empty(recovery):
    rc, store, stream = recovery
    assert await rc.get_last_step_state("conv-1") is None


async def test_get_last_step_state_returns_latest(recovery):
    rc, store, stream = recovery
    # 两个 step，最后一个是 AWAITING_USER
    for step_id, state, seq in [
        ("step-1", StepState.DONE, 0),
        ("step-2", StepState.AWAITING_USER, 1),
    ]:
        await stream.emit(StepEvent(
            event_id=f"evt-{step_id}",
            step_id=step_id,
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=state,
            event_type="step_init" if state == StepState.DONE else "interaction_request",
            input={"prompt": "hi"} if state == StepState.AWAITING_USER else {},
            output={},
            seq=seq,
            timestamp=float(seq),
        ))
    result = await rc.get_last_step_state("conv-1")
    assert result is not None
    step_id, state, snapshot = result
    assert step_id == "step-2"
    assert state == StepState.AWAITING_USER
    assert snapshot == {"prompt": "hi"}


async def test_decide_resume_action_awaiting(recovery):
    rc, store, stream = recovery
    await stream.emit(StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.AWAITING_USER,
        event_type="interaction_request",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    ))
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "resume_awaiting"
    assert decision["step_id"] == "step-1"
    assert decision["state"] == StepState.AWAITING_USER


async def test_decide_resume_action_redo_for_incomplete_step(recovery):
    rc, store, stream = recovery
    # step 停在 THINKING（未完成）→ 应重做
    await stream.emit(StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.THINKING,
        event_type="llm_token",
        input={"prompt": "hi"},
        output={"token": "partial"},
        seq=0,
        timestamp=0.0,
    ))
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "redo_step"
    assert decision["step_id"] == "step-1"


async def test_decide_resume_action_continue_when_done(recovery):
    rc, store, stream = recovery
    await stream.emit(StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.DONE,
        event_type="step_done",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    ))
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "continue_next"


async def test_replay_events(recovery):
    rc, store, stream = recovery
    for i in range(3):
        await stream.emit(StepEvent(
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
        ))
    events = await rc.replay_events("conv-1")
    assert [e.seq for e in events] == [0, 1, 2]
