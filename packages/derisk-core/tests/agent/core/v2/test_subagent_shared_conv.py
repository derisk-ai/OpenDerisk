"""SubAgentRuntime shared_conv 模式测试。"""
import pytest
import tempfile
import os
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext


async def _sub_thinking(input_):
    yield {"token": "子 agent 思考"}
    yield {"token": "", "tool_calls": []}


async def _sub_acting(tc: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
    return V2ToolResult.ok(output="子 agent 完成", tool_name="sub_tool")


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def test_shared_conv_writes_events_to_parent_conv(store):
    """shared_conv=True 时，子 agent 事件写父 conv_id。"""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="sub",
        task="子任务",
        run_in_background=False,
        parent_step_id="step-parent",
        parent_conv_id="conv-parent",
        parent_agent_id="agent-parent",
        depth=0,
        thinking_fn=_sub_thinking,
        acting_fn=_sub_acting,
        shared_conv=True,  # v2 新增
    )
    handle = await runtime.spawn(spec)
    assert handle.status.value == "done"

    # 父 conv 的事件里应有子 agent 的事件
    events = await store.get_events("conv-parent")
    assert len(events) > 0
    # 子事件应有 parent_step_id 标记
    sub_events = [e for e in events if e.parent_step_id == "step-parent"]
    assert len(sub_events) > 0


async def test_independent_conv_creates_new_conv(store):
    """shared_conv=False（默认）时，子 agent 用新 sub_conv_id。"""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="sub",
        task="子任务",
        run_in_background=False,
        parent_step_id="step-parent",
        parent_conv_id="conv-parent",
        parent_agent_id="agent-parent",
        depth=0,
        thinking_fn=_sub_thinking,
        acting_fn=_sub_acting,
    )
    handle = await runtime.spawn(spec)
    assert handle.status.value == "done"
    assert handle.sub_conv_id != "conv-parent"  # 独立 conv

    # 父 conv 不应有子 agent 的事件
    parent_events = await store.get_events("conv-parent")
    assert len(parent_events) == 0
