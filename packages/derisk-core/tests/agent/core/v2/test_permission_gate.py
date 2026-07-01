# packages/derisk-core/tests/agent/core/v2/test_permission_gate.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache
from derisk.agent.core.v2.permission_gate import PermissionGate, PermissionDecision
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.step_state import StepState
from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


@pytest.fixture
def stream(store):
    return EventStream(store)


def _gate(store, stream, mode=PermissionMode.DEFAULT, ruleset=None, session_cache=None,
          interaction_adapter=None, step_id="step-1", conv_id="conv-1", agent_id="agent-1"):
    return PermissionGate(
        state_store=store, event_stream=stream,
        interaction_adapter=interaction_adapter,
        session_cache=session_cache or SessionPermissionCache(),
        ruleset=ruleset, mode=mode,
        step_id=step_id, conv_id=conv_id, agent_id=agent_id,
    )


async def test_bypass_mode_allows(store, stream):
    gate = _gate(store, stream, mode=PermissionMode.BYPASS)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []  # no event emitted
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_auto_mode_allows(store, stream):
    gate = _gate(store, stream, mode=PermissionMode.AUTO)
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_plan_mode_denies_side_effect_tool_when_ruleset_says_allow(store, stream):
    # ruleset allows rm, but plan mode overrides → deny
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, mode=PermissionMode.PLAN, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    assert gate.last_result.decision is PermissionDecision.DENY
    assert "plan mode" in gate.last_result.reason.lower()


async def test_plan_mode_allows_readonly_tool(store, stream):
    ruleset = PermissionRuleset(default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, mode=PermissionMode.PLAN, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_session_cache_skips_ruleset(store, stream):
    cache = SessionPermissionCache()
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ASK)
    # Pre-populate session cache
    from derisk.agent.core.v2.session_cache import hash_tool_input
    cache.allow_session("read_file", hash_tool_input({}))
    gate = _gate(store, stream, ruleset=ruleset, session_cache=cache)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ruleset_allow_short_circuits(store, stream):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ruleset_deny_short_circuits(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.DENY)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_ask_emits_awaiting_event_and_persists_checkpoint(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    # Fake interaction adapter: responds "allow_once" immediately
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class FakeResponse:
                choice = "allow_once"
                status = None
            return FakeResponse()
    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    # Should emit exactly one AWAITING_TOOL_PERMISSION event
    assert len(events) == 1
    assert events[0].state is StepState.AWAITING_TOOL_PERMISSION
    assert events[0].event_type == "interaction_request"
    assert events[0].input["tool_name"] == "rm"
    # Checkpoint persisted
    request_id = events[0].input["request_id"]
    cp = await store.get_interaction_checkpoint(request_id)
    assert cp is not None
    assert cp["step_id"] == "step-1"
    # Decision is ALLOW after user responds; checkpoint deletion is deferred
    # to the runtime (P2 refinement — see TODO in runtime.py:_run_acting_phase)
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ask_deny_response_persists_deny(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class FakeResponse:
                action = "deny"
                status = None
            return FakeResponse()
    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_ask_allow_session_caches_for_session(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class FakeResponse:
                choice = "allow_session"
                status = None
            return FakeResponse()
    cache = SessionPermissionCache()
    gate = _gate(store, stream, ruleset=ruleset, session_cache=cache,
                 interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW
    # Second call with same input should skip the ask (no event, cache hit)
    from derisk.agent.core.v2.session_cache import hash_tool_input
    assert cache.is_allowed("rm", hash_tool_input({"path": "/x"}))


async def test_no_ruleset_no_adapter_defaults_to_allow(store, stream):
    # No ruleset, no adapter — default_action when no ruleset is ALLOW (safe default for P1 tests)
    gate = _gate(store, stream, ruleset=None, interaction_adapter=None)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_no_ruleset_but_ask_action_without_adapter_raises(store, stream):
    # If somehow no ruleset but mode says ask... can't happen in practice,
    # but guard: if decision would be ASK and no adapter, raise clear error
    from derisk.agent.core.v2.permission_gate import NoInteractionAdapterError
    # Build a gate with no ruleset AND no adapter; force the ASK path by using
    # a ruleset that returns ASK
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=None)
    with pytest.raises(NoInteractionAdapterError):
        async for _ in gate.check({"tool": "rm", "input": {}}):
            pass


async def test_ask_reads_response_choice_not_action(store, stream):
    """P1 I-1 fix: gate reads response.choice, not response.action."""
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            # Real InteractionResponse has .choice, NOT .action
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(
                request_id="req-x",
                choice="allow_once",
            )

    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ask_deny_when_response_choice_is_none(store, stream):
    """If response.choice is None (e.g. user dismissed), default to deny."""
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice=None)

    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_check_accepts_emit_callable_for_correct_seq(store, stream):
    """P1 I-2 fix: when emit callable is passed, gate uses it (correct seq)."""
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice="allow_once")

    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())

    # Fake emit: increments seq, persists, returns the event
    seq = {"n": 100}
    captured = {}
    async def fake_emit(state, event_type, input_data=None, output_data=None):
        from derisk.agent.core.v2.step_event import StepEvent
        import time
        evt = StepEvent(
            event_id=f"evt-{seq['n']}", step_id=gate._step_id, conv_id=gate._conv_id,
            agent_id=gate._agent_id, parent_step_id=None, state=state,
            event_type=event_type, input=input_data or {}, output=output_data or {},
            seq=seq["n"], timestamp=time.time(),
        )
        seq["n"] += 1
        captured["event"] = evt
        return evt

    events = [e async for e in gate.check({"tool": "rm", "input": {}}, emit=fake_emit)]
    # The emitted event should have seq=100, not seq=0
    assert events[0].seq == 100
