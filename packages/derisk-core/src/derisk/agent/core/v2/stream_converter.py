"""step_event_to_stream_event — maps internal StepEvent to external StreamEvent.

Spec §10.1-§10.2. The internal StepEvent carries (state, event_type, input, output);
the external StreamEvent flattens this to (type, payload). The SSE adapter
dispatches on StreamEvent.type to produce the frontend SSE format.
"""
from __future__ import annotations

from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.stream_event import StreamEvent


def step_event_to_stream_event(step_event: StepEvent) -> StreamEvent:
    state = step_event.state
    event_type = step_event.event_type
    payload = {
        **step_event.input,
        **step_event.output,
        "step_id": step_event.step_id,
        "conv_id": step_event.conv_id,
        "agent_id": step_event.agent_id,
        "parent_step_id": step_event.parent_step_id,
    }

    if event_type == "step_init" and state is StepState.INIT:
        stream_type = "step_start"
    elif event_type == "step_done" and state is StepState.DONE:
        stream_type = "step_end"
    elif event_type == "llm_token":
        stream_type = "llm_token"
    elif event_type == "tool_call" and state is StepState.ACTING:
        stream_type = "tool_call"
    elif event_type == "tool_result" and state is StepState.OBSERVING:
        stream_type = "tool_result"
    elif event_type == "interaction_request" and state in (
        StepState.AWAITING_USER,
        StepState.AWAITING_TOOL_PERMISSION,
    ):
        stream_type = "interaction_request"
    elif event_type == "subagent_spawn" and state is StepState.AWAITING_SUB_AGENT:
        stream_type = "sub_agent_start"
    elif event_type == "usage_metric":
        stream_type = "usage_metric"
    else:
        stream_type = "workspace"
        payload = {"event_type": event_type, **payload}

    return StreamEvent(
        type=stream_type,
        payload=payload,
        seq=step_event.seq,
        timestamp=step_event.timestamp,
    )
