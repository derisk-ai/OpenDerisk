"""run_loop 多轮循环测试。"""
import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock
from derisk.agent.core.v2.run_loop import run_loop
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def _thinking_no_tools(input_):
    """thinking_fn 不 emit tool_calls → 单 step turn。"""
    yield {"token": "final answer"}


async def _acting_return_ok(tool_call, ctx):
    from derisk.agent.core.v2.tool_call_types import V2ToolResult
    return V2ToolResult.ok(output="tool result", tool_name="test_tool")


async def test_single_step_turn(store):
    """thinking 不 emit tool_calls → run_loop 跑一个 step 就结束。"""
    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=_thinking_no_tools,
        acting_fn=_acting_return_ok,
        max_steps=5,
    ):
        events.append(e)
    # 应有 INIT / THINKING / DONE
    states = [e.state for e in events]
    assert states[0] == StepState.INIT
    assert states[-1] == StepState.DONE


async def test_max_steps_caps_loop(store):
    """max_steps=1 时只跑 1 个 step。"""
    call_count = {"n": 0}
    async def thinking(input_):
        call_count["n"] += 1
        yield {"token": "x"}

    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=thinking,
        acting_fn=_acting_return_ok,
        max_steps=1,
    ):
        events.append(e)
    assert call_count["n"] == 1


async def test_turn_complete_hook_fires(store):
    """turn 结束时触发 HookManager.turn_complete。"""
    hook_manager = MagicMock()
    hook_manager.trigger = AsyncMock()
    async for _ in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=_thinking_no_tools,
        acting_fn=_acting_return_ok,
        hook_manager=hook_manager,
        max_steps=5,
    ):
        pass
    hook_manager.trigger.assert_called()
    # 至少一次 turn_complete
    calls = [c.args[0] for c in hook_manager.trigger.call_args_list]
    assert "turn_complete" in calls


async def test_awaiting_user_returns(store):
    """thinking_fn emit await_user=True → AWAITING_USER → run_loop 应 return。"""
    async def thinking(input_):
        yield {"await_user": True}

    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=thinking,
        acting_fn=_acting_return_ok,
        max_steps=5,
    ):
        events.append(e)

    # 应有 AWAITING_USER 事件
    states = [e.state for e in events]
    assert StepState.AWAITING_USER in states
    # 不应有 DONE 事件（step 被暂停）
    assert StepState.DONE not in states


async def test_multi_step_turn(store):
    """thinking emit tool_call → acting → thinking 再无 tool_call → turn 结束。"""
    state = {"call": 0}

    async def thinking(input_):
        state["call"] += 1
        if state["call"] == 1:
            yield {"token": "calling", "tool_calls": [{"tool": "read_file", "input": {}}]}
        else:
            yield {"token": "final"}

    from derisk.agent.core.v2.tool_call_types import V2ToolResult

    async def acting(tool_call, ctx):
        return V2ToolResult.ok(output="ok", tool_name="read_file")

    events = []
    async for e in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=thinking,
        acting_fn=acting,
        max_steps=5,
    ):
        events.append(e)

    # 应有 2 个 step（thinking 调了 2 次）
    assert state["call"] == 2
    # 应有 1 个 tool_call + 1 个 tool_result
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1


async def test_max_steps_no_double_turn_complete(store):
    """max_steps reached on no-tool step should fire turn_complete only once."""
    call_count = {"n": 0}
    async def thinking(input_):
        call_count["n"] += 1
        yield {"token": "x"}  # no tool_calls

    hook_manager = MagicMock()
    hook_manager.trigger = AsyncMock()
    async for _ in run_loop(
        agent_id="a1", conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1"},
        state_store=store,
        thinking_fn=thinking,
        acting_fn=_acting_return_ok,
        hook_manager=hook_manager,
        max_steps=1,
    ):
        pass
    turn_complete_calls = [c for c in hook_manager.trigger.call_args_list if c.args[0] == "turn_complete"]
    assert len(turn_complete_calls) == 1, f"Expected 1 turn_complete, got {len(turn_complete_calls)}"
