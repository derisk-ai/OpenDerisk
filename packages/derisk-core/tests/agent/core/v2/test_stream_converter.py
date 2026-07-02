import time
from derisk.agent.core.v2.stream_converter import step_event_to_stream_event
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


def _make(state, event_type, output=None, input_=None, seq=0):
    return StepEvent(
        event_id=f"evt-{seq}", step_id="step-1", conv_id="conv-1", agent_id="agent-1",
        parent_step_id=None, state=state, event_type=event_type,
        input=input_ or {}, output=output or {}, seq=seq, timestamp=time.time(),
    )


def test_step_init_to_step_start():
    se = step_event_to_stream_event(_make(StepState.INIT, "step_init", input_={"prompt": "hi"}))
    assert se.type == "step_start"
    assert se.payload["step_id"] == "step-1"


def test_step_done_to_step_end():
    se = step_event_to_stream_event(_make(StepState.DONE, "step_done"))
    assert se.type == "step_end"


def test_llm_token_passes_through():
    se = step_event_to_stream_event(_make(StepState.THINKING, "llm_token", output={"token": "hi"}))
    assert se.type == "llm_token"
    assert se.payload["token"] == "hi"


def test_tool_call_to_tool_call():
    se = step_event_to_stream_event(_make(StepState.ACTING, "tool_call", input_={"tool": "rm"}))
    assert se.type == "tool_call"
    assert se.payload["tool"] == "rm"


def test_tool_result_to_tool_result():
    se = step_event_to_stream_event(_make(StepState.OBSERVING, "tool_result", output={"r": "ok"}))
    assert se.type == "tool_result"


def test_interaction_request_awaiting_user():
    se = step_event_to_stream_event(_make(StepState.AWAITING_USER, "interaction_request"))
    assert se.type == "interaction_request"


def test_interaction_request_awaiting_tool_permission():
    se = step_event_to_stream_event(_make(StepState.AWAITING_TOOL_PERMISSION, "interaction_request"))
    assert se.type == "interaction_request"


def test_subagent_spawn_to_sub_agent_start():
    se = step_event_to_stream_event(_make(StepState.AWAITING_SUB_AGENT, "subagent_spawn"))
    assert se.type == "sub_agent_start"


def test_usage_metric_passes_through():
    se = step_event_to_stream_event(_make(StepState.THINKING, "usage_metric", output={"total": 100}))
    assert se.type == "usage_metric"
    assert se.payload["total"] == 100


def test_unknown_event_falls_back_to_workspace():
    se = step_event_to_stream_event(_make(StepState.THINKING, "some_custom_event"))
    assert se.type == "workspace"


def test_seq_and_timestamp_preserved():
    step_event = _make(StepState.INIT, "step_init", seq=42)
    se = step_event_to_stream_event(step_event)
    assert se.seq == 42
    assert se.timestamp == step_event.timestamp
