from derisk.agent.core.v2.stream_event import StreamEvent, EVENT_TYPES
from derisk.agent.core.v2.step_state import StepState, VALID_TRANSITIONS, validate_transition


def test_stream_event_fields():
    e = StreamEvent(type="llm_token", payload={"token": "hi"}, seq=1, timestamp=0.0)
    assert e.type == "llm_token"
    assert e.payload == {"token": "hi"}
    assert e.seq == 1


def test_event_types_contains_legacy_and_new():
    # Legacy SSE compat types
    assert "metadata" in EVENT_TYPES
    assert "interrupt" in EVENT_TYPES
    assert "error" in EVENT_TYPES
    assert "workspace" in EVENT_TYPES
    assert "content" in EVENT_TYPES
    assert "done" in EVENT_TYPES
    # New fine-grained types
    assert "step_start" in EVENT_TYPES
    assert "step_end" in EVENT_TYPES
    assert "llm_token" in EVENT_TYPES
    assert "tool_call" in EVENT_TYPES
    assert "tool_result" in EVENT_TYPES
    assert "interaction_request" in EVENT_TYPES
    assert "sub_agent_start" in EVENT_TYPES
    assert "sub_agent_result" in EVENT_TYPES
    # P3 §10.7 addition
    assert "usage_metric" in EVENT_TYPES


def test_observing_can_transition_to_acting():
    """P1 pre-existing gap: multi-tool sequences need OBSERVING → ACTING."""
    assert validate_transition(StepState.OBSERVING, StepState.ACTING)
