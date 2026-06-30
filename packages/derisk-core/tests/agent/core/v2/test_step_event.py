import pytest
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


def test_step_event_fields():
    event = StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.THINKING,
        event_type="llm_token",
        input={"prompt": "hi"},
        output={"token": "hello"},
        seq=0,
        timestamp=1000.0,
    )
    assert event.event_id == "evt-1"
    assert event.state == StepState.THINKING
    assert event.seq == 0


def test_step_event_storage_roundtrip():
    event = StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id="step-0",
        state=StepState.ACTING,
        event_type="tool_call",
        input={"tool": "read_file"},
        output={},
        seq=5,
        timestamp=1000.0,
    )
    d = event.to_storage_dict()
    assert d["state"] == "acting"  # 枚举序列化为字符串
    restored = StepEvent.from_storage_dict(d)
    assert restored == event
    assert restored.state == StepState.ACTING


def test_step_event_parent_step_id_optional():
    event = StepEvent(
        event_id="evt-2",
        step_id="step-2",
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
    assert event.parent_step_id is None
