"""Tests for V2EventEmitter - V2 SSE event generation."""
import asyncio
import pytest

from derisk.agent.core.v2.v2_event_emitter import V2EventEmitter
from derisk.agent.core.v2.v2_event_types import STEP_START, LLM_TOKEN, VIS_UPDATE
from derisk.agent.core.v2.v2_vis_component import VisOperationType, VisComponentTag


@pytest.mark.asyncio
async def test_event_emitter_basic():
    """Test basic event emission with seq increment."""
    emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")

    event = await emitter.emit(STEP_START, {"state": "INIT"})
    assert event["event"] == "step_start"
    assert event["seq"] == 1
    assert event["payload"]["state"] == "INIT"

    event2 = await emitter.emit(LLM_TOKEN, {"token": "hello"})
    assert event2["seq"] == 2  # seq increments


@pytest.mark.asyncio
async def test_event_emitter_vis_update():
    """Test VIS update event format."""
    emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")

    event = await emitter.emit_vis_update(
        type=VisOperationType.INCR,
        uid="s1-thinking-0",
        tag=VisComponentTag.THINKING,
        content="analyzing",
    )
    assert event["event"] == "vis_update"
    assert event["payload"]["type"] == "incr"
    assert event["payload"]["uid"] == "s1-thinking-0"
    assert event["payload"]["tag"] == "thinking"
    assert event["payload"]["content"] == "analyzing"


@pytest.mark.asyncio
async def test_event_emitter_ts_increases():
    """Test that timestamps are monotonically non-decreasing."""
    emitter = V2EventEmitter(step_id="s1", agent_id="agent-1", conv_id="conv-1")

    event1 = await emitter.emit(STEP_START, {})
    await asyncio.sleep(0.01)  # 10ms
    event2 = await emitter.emit(LLM_TOKEN, {"token": "test"})

    assert event2["ts"] >= event1["ts"]
