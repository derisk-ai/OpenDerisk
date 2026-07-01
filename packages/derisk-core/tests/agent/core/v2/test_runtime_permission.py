# packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step, resume_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.permission_gate import PermissionGate, PermissionDecision
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache
from derisk.agent.core.v2.step_state import StepState, IllegalTransitionError
from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def thinking_fn(input_):
    yield {"token": "calling tool"}
    yield {"token": "", "tool_calls": [{"tool": "read_file", "input": {"path": "/x"}}]}


async def acting_fn(tool_call):
    return {"result": f"executed:{tool_call['tool']}"}


def _make_gate(store, mode=PermissionMode.DEFAULT, ruleset=None, adapter=None):
    stream = EventStream(store)
    return PermissionGate(
        state_store=store, event_stream=stream,
        interaction_adapter=adapter,
        session_cache=SessionPermissionCache(),
        ruleset=ruleset, mode=mode,
        step_id="step-test", conv_id="conv-1", agent_id="agent-1",
    )


async def test_run_step_with_permission_allow_executes_tool(store):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _make_gate(store, ruleset=ruleset)
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert tool_results[0].output == {"result": "executed:read_file"}
    assert events[-1].state is StepState.DONE


async def test_run_step_with_permission_deny_skips_tool(store):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.DENY)
    }, default_action=PermissionAction.ALLOW)
    gate = _make_gate(store, ruleset=ruleset)
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    # ACTING tool_call event IS emitted (we attempted the call), but no tool_result
    assert len(tool_calls) == 1
    assert len(tool_results) == 0
    # The tool_call event's output should indicate denial
    assert tool_calls[0].output.get("denied") is True
    assert events[-1].state is StepState.DONE


async def test_run_step_with_permission_ask_emits_awaiting(store):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class R: choice = "allow_once"
            return R()
    gate = _make_gate(store, ruleset=ruleset, adapter=FakeAdapter())
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    awaiting = [e for e in events if e.state is StepState.AWAITING_TOOL_PERMISSION]
    assert len(awaiting) == 1
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_results) == 1  # tool executed after user allowed
    assert events[-1].state is StepState.DONE


async def test_resume_step_redoes_acting_phase_with_permission(store):
    """P0 Important #1 fix: resume_step must run acting_fn on redo path."""
    from derisk.agent.core.v2.step_event import StepEvent
    stream = EventStream(store)
    # Simulate a crash mid-ACTING: step-pre got a tool_call event but no tool_result
    await stream.emit(StepEvent(
        event_id="evt-pre-1", step_id="step-pre", conv_id="conv-1", agent_id="agent-1",
        parent_step_id=None, state=StepState.THINKING, event_type="llm_token",
        input={"prompt": "hi"}, output={"token": "partial"}, seq=0, timestamp=0.0,
    ))
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = PermissionGate(
        state_store=store, event_stream=stream, interaction_adapter=None,
        session_cache=SessionPermissionCache(), ruleset=ruleset,
        mode=PermissionMode.DEFAULT, step_id="step-pre", conv_id="conv-1", agent_id="agent-1",
    )
    events = []
    async for e in resume_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                                 thinking_fn, acting_fn, step_id="step-pre",
                                 permission_gate=gate):
        events.append(e)
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    # P0 Important #1 fix: acting_fn IS called on redo path
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert events[-1].state is StepState.DONE


async def test_run_step_enforces_invalid_transition(store):
    """P0 Important #2 fix: validate_transition is wired into _make_emit."""
    # We can't easily trigger an invalid transition from outside run_step's normal flow,
    # but we can test _validate_and_track_transition directly
    from derisk.agent.core.v2.runtime import _validate_and_track_transition
    # Valid: INIT -> THINKING
    _validate_and_track_transition("step-1", None, StepState.INIT)
    _validate_and_track_transition("step-1", StepState.INIT, StepState.THINKING)
    # Invalid: INIT -> DONE (skips THINKING)
    with pytest.raises(IllegalTransitionError):
        _validate_and_track_transition("step-2", StepState.INIT, StepState.DONE)
