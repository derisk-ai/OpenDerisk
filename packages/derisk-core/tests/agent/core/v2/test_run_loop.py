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


@pytest.mark.skip(reason="Task 16")
async def test_awaiting_user_returns(store):
    """AWAITING_USER 状态时 run_loop 应 return（暂停）。"""
    pass  # TODO: 这个测试在 Task 16 完善
