import pytest
import tempfile
import os
from types import SimpleNamespace
from derisk.agent.core.v2.spawn_subagent_tool import SpawnSubagentTool
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime
from derisk.agent.core.v2.state_store import DbStateStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _subagent_thinking(input_):
    yield {"token": "sub", "tool_calls": []}


async def _subagent_acting(tc):
    return {"result": "ok"}


def _make_tool(store, max_depth=5):
    runtime = SubAgentRuntime(state_store=store, max_depth=max_depth)
    return SpawnSubagentTool(runtime=runtime), runtime


def _make_context(parent_step_id="step-p", parent_conv_id="conv-p", parent_agent_id="agent-p"):
    # ToolContext does not expose parent_step_id/parent_conv_id/depth/thinking_fn/acting_fn,
    # so use a generic namespace object. The implementation reads these via getattr().
    return SimpleNamespace(
        parent_step_id=parent_step_id,
        parent_conv_id=parent_conv_id,
        agent_id=parent_agent_id,
        depth=0,
        thinking_fn=_subagent_thinking,
        acting_fn=_subagent_acting,
    )


async def test_tool_execute_sync_returns_result(store):
    tool, runtime = _make_tool(store)
    ctx = _make_context()
    result = await tool.execute(
        args={
            "agent_name": "BAIZE",
            "task": "do thing",
            "run_in_background": False,
            "context": {},
        },
        context=ctx,
    )
    assert result.success is True
    assert "task_id" in result.output
    assert result.output["mode"] == "sync"
    assert result.output["status"] == "done"


async def test_tool_execute_async_returns_handle(store):
    tool, runtime = _make_tool(store)
    ctx = _make_context()
    result = await tool.execute(
        args={
            "agent_name": "BAIZE",
            "task": "do thing async",
            "run_in_background": True,
            "context": {},
        },
        context=ctx,
    )
    assert result.success is True
    assert result.output["mode"] == "async"
    assert "task_id" in result.output


async def test_tool_validates_required_args(store):
    tool, runtime = _make_tool(store)
    ctx = _make_context()
    result = await tool.execute(
        args={"agent_name": "BAIZE"},  # missing task
        context=ctx,
    )
    assert result.success is False
    assert "task" in (result.error or "").lower()
