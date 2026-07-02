import pytest
import tempfile
import os
import asyncio
from derisk.agent.core.v2.subagent_runtime import (
    SubAgentRuntime, SubAgentSpawnSpec,
)
from derisk.agent.core.v2.subagent_handle import SubAgentMode, SubAgentStatus
from derisk.agent.core.v2.state_store import DbStateStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _subagent_thinking(input_):
    yield {"token": "sub"}
    yield {"token": "", "tool_calls": []}


async def _subagent_acting(tc):
    return {"result": f"sub:{tc.get('tool', '')}"}


def _make_spec(parent_step_id="step-p", parent_conv_id="conv-p", run_in_background=False, depth=0):
    return SubAgentSpawnSpec(
        agent_name="BAIZE",
        task="do something",
        run_in_background=run_in_background,
        context={},
        parent_step_id=parent_step_id,
        parent_conv_id=parent_conv_id,
        parent_agent_id="agent-p",
        depth=depth,
        thinking_fn=_subagent_thinking,
        acting_fn=_subagent_acting,
    )


async def test_spawn_sync_returns_handle_with_done_result(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec(run_in_background=False))
    assert handle.mode is SubAgentMode.SYNC
    assert handle.status is SubAgentStatus.DONE
    assert handle.result is not None
    assert handle.parent_conv_id == "conv-p"
    assert handle.sub_conv_id != "conv-p"  # independent conv


async def test_spawn_async_returns_running_handle(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec(run_in_background=True))
    assert handle.mode is SubAgentMode.ASYNC
    assert handle.status in (SubAgentStatus.RUNNING, SubAgentStatus.DONE)  # may finish fast
    assert handle.transcript_id is not None


async def test_spawn_exceeds_depth_limit_rejected(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=3)
    with pytest.raises(ValueError, match="depth"):
        await runtime.spawn(_make_spec(depth=3))  # depth+1 = 4 > 3


async def test_spawn_at_depth_limit_boundary_ok(store):
    """depth=2, max_depth=3 -> depth+1=3 == max_depth, allowed."""
    runtime = SubAgentRuntime(state_store=store, max_depth=3)
    handle = await runtime.spawn(_make_spec(depth=2))
    assert handle.status is SubAgentStatus.DONE


async def test_get_status_returns_handle(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec())
    fetched = await runtime.get_status(handle.task_id)
    assert fetched is not None
    assert fetched.task_id == handle.task_id


async def test_get_status_returns_none_for_unknown(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    assert await runtime.get_status("never-existed") is None


async def test_cancel_async_task(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    # Spawn an async task that takes a bit
    async def slow_thinking(input_):
        await asyncio.sleep(0.1)
        yield {"token": "sub", "tool_calls": []}

    spec = _make_spec(run_in_background=True)
    spec.thinking_fn = slow_thinking
    handle = await runtime.spawn(spec)
    ok = await runtime.cancel(handle.task_id)
    assert ok is True
    # After cancel, status is CANCELLED or DONE (if it finished first)
    fetched = await runtime.get_status(handle.task_id)
    assert fetched.status in (SubAgentStatus.CANCELLED, SubAgentStatus.DONE)


async def test_resume_async_task(store):
    """resume() on an async task returns the current handle (may be running or done)."""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec(run_in_background=True))
    resumed = await runtime.resume(handle.task_id)
    assert resumed.task_id == handle.task_id


async def test_sync_spawn_writes_subagent_events_to_same_store(store):
    """Sub-agent's StepEvents go into the same step_event table with sub_conv_id."""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec())
    events = await store.get_events(handle.sub_conv_id)
    assert len(events) > 0
    # Sub-agent should have at least INIT, THINKING, DONE
    states = [e.state.value for e in events]
    assert "init" in states
    assert "done" in states


async def test_sync_subagent_delegates_asks_to_parent_gateway(store):
    """P2 follow-up: sync sub-agent's ask_user bubbles to parent's gateway."""
    from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec
    from derisk.agent.interaction.interaction_protocol import InteractionResponse
    from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction

    parent_received = []

    class FakeParentGateway:
        async def send_and_wait(self, request):
            parent_received.append(request)
            return InteractionResponse(request_id=request.request_id, choice="allow_once")

    # Sub-agent's thinking_fn triggers an ask via acting_fn (which is gated)
    async def sub_thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "ask_user_tool", "input": {"q": "name?"}}]}

    async def sub_acting(tc):
        return {"result": "ok"}

    # Force the gate to ASK for ask_user_tool so we can prove delegation to parent.
    ruleset = PermissionRuleset(rules={
        "ask_user_tool": PermissionRule(tool_pattern="ask_user_tool", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="BAIZE",
        task="ask parent",
        run_in_background=False,
        parent_step_id="step-p", parent_conv_id="conv-p", parent_agent_id="agent-p",
        depth=0,
        thinking_fn=sub_thinking,
        acting_fn=sub_acting,
        interaction_gateway=FakeParentGateway(),
        ruleset=ruleset,
    )
    handle = await runtime.spawn(spec)
    assert handle.status.value == "done"
    # Parent gateway should have received the authorization request.
    assert len(parent_received) >= 1
    assert parent_received[0].tool_name == "ask_user_tool"


async def test_async_subagent_auto_denies_asks(store):
    """P2 follow-up: async sub-agent's asks auto-deny (no parent interruption)."""
    from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec

    class TrackingParentGateway:
        def __init__(self):
            self.received = []
        async def send_and_wait(self, request):
            self.received.append(request)
            raise AssertionError("async sub-agent should NOT call parent gateway")

    async def sub_thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "ask_user_tool", "input": {"q": "name?"}}]}

    async def sub_acting(tc):
        return {"result": "auto-denied path"}

    parent_gw = TrackingParentGateway()
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="BAIZE",
        task="bg task",
        run_in_background=True,
        parent_step_id="step-p", parent_conv_id="conv-p", parent_agent_id="agent-p",
        depth=0,
        thinking_fn=sub_thinking,
        acting_fn=sub_acting,
        interaction_gateway=parent_gw,
    )
    handle = await runtime.spawn(spec)
    # Wait for async task to finish
    await runtime.wait(handle, timeout=2.0)
    # Parent gateway was NOT called (auto-deny path)
    assert parent_gw.received == []
