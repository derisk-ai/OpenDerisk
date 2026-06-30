import pytest
import tempfile
import os
import asyncio
from derisk.agent.core.v2.event_stream import EventStream
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


async def test_emit_persists_and_returns_event(store):
    stream = EventStream(store)
    event = StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.INIT,
        event_type="step_init",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    )
    returned = await stream.emit(event)
    assert returned is event
    persisted = await store.get_events("conv-1")
    assert len(persisted) == 1
    assert persisted[0].event_id == "evt-1"


async def test_replay_yields_historical_events_in_order(store):
    stream = EventStream(store)
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

    # 模拟进程重启后重放
    new_stream = EventStream(store)
    events = []
    async for e in new_stream.replay("conv-1"):
        events.append(e)
    assert [e.seq for e in events] == [0, 1, 2]
    assert [e.output["i"] for e in events] == [0, 1, 2]


async def test_replay_since_seq(store):
    stream = EventStream(store)
    for i in range(5):
        await stream.emit(StepEvent(
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
        ))
    new_stream = EventStream(store)
    events = []
    async for e in new_stream.replay("conv-1", since_seq=3):
        events.append(e)
    assert [e.seq for e in events] == [3, 4]
