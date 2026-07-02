import os
import tempfile

import pytest

from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.usage_metric import aggregate_usage, emit_usage_metric
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _fake_emit_factory(store):
    """Build an emit callable that persists via EventStream."""
    stream = EventStream(store)
    seq = {"n": 0}

    async def emit(state, event_type, input_data=None, output_data=None):
        import time
        import uuid

        from derisk.agent.core.v2.step_event import StepEvent

        evt = StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=state,
            event_type=event_type,
            input=input_data or {},
            output=output_data or {},
            seq=seq["n"],
            timestamp=time.time(),
        )
        seq["n"] += 1
        return await stream.emit(evt)

    return emit


async def test_emit_usage_metric_persists_event(store):
    emit = await _fake_emit_factory(store)
    await emit_usage_metric(
        store=store,
        emit=emit,
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        llm_call_id="call-1",
        model="claude-sonnet-4-6",
        this_call={"prompt": 100, "completion": 20, "total": 120},
    )
    events = await store.get_events("conv-1")
    usage_events = [e for e in events if e.event_type == "usage_metric"]
    assert len(usage_events) == 1
    assert usage_events[0].output["this_call"]["total"] == 120
    assert usage_events[0].output["cumulative"]["total"] == 120
    assert usage_events[0].output["model"] == "claude-sonnet-4-6"


async def test_cumulative_aggregates_across_calls(store):
    emit = await _fake_emit_factory(store)
    await emit_usage_metric(
        store,
        emit,
        "step-1",
        "conv-1",
        "agent-1",
        "call-1",
        "m1",
        {"prompt": 100, "completion": 20, "total": 120},
    )
    await emit_usage_metric(
        store,
        emit,
        "step-1",
        "conv-1",
        "agent-1",
        "call-2",
        "m1",
        {"prompt": 200, "completion": 30, "total": 230},
    )
    events = await store.get_events("conv-1")
    usage_events = [e for e in events if e.event_type == "usage_metric"]
    assert len(usage_events) == 2
    assert usage_events[1].output["cumulative"]["total"] == 350


async def test_aggregate_usage_sums_all(store):
    emit = await _fake_emit_factory(store)
    await emit_usage_metric(
        store,
        emit,
        "step-1",
        "conv-1",
        "agent-1",
        "call-1",
        "m1",
        {"prompt": 100, "completion": 20, "total": 120},
    )
    await emit_usage_metric(
        store,
        emit,
        "step-1",
        "conv-1",
        "agent-1",
        "call-2",
        "m1",
        {"prompt": 200, "completion": 30, "total": 230},
    )
    agg = await aggregate_usage(store, "conv-1")
    assert agg["total"] == 350
    assert agg["prompt"] == 300
    assert agg["completion"] == 50


async def test_emit_usage_metric_with_acting_state(store):
    emit = await _fake_emit_factory(store)
    await emit_usage_metric(
        store=store,
        emit=emit,
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        llm_call_id="call-1",
        model="claude-sonnet-4-6",
        this_call={"prompt": 100, "completion": 20, "total": 120},
        current_state=StepState.ACTING,
    )
    events = await store.get_events("conv-1")
    usage_events = [e for e in events if e.event_type == "usage_metric"]
    assert len(usage_events) == 1
    assert usage_events[0].output["this_call"]["total"] == 120


async def test_context_window_and_ratio(store):
    emit = await _fake_emit_factory(store)
    await emit_usage_metric(
        store,
        emit,
        "step-1",
        "conv-1",
        "agent-1",
        "call-1",
        "claude-sonnet-4-6",
        {"prompt": 5000, "completion": 200, "total": 5200},
    )
    events = await store.get_events("conv-1")
    usage_events = [e for e in events if e.event_type == "usage_metric"]
    assert "context_window" in usage_events[0].output
    assert "ratio" in usage_events[0].output
