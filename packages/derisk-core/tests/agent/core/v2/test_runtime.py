# packages/derisk-core/tests/agent/core/v2/test_runtime.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step, resume_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.recovery import RecoveryCoordinatorV2
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def thinking_fn(input_):
    """测试用思考函数：yield 两个 token。"""
    yield {"token": "hello"}
    yield {"token": "world"}


async def acting_fn(tool_call: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
    return V2ToolResult.ok(output=f"executed:{tool_call.name}", tool_name=tool_call.name)


async def test_run_step_produces_init_thinking_done(store):
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store, thinking_fn):
        events.append(e)

    states = [e.state for e in events]
    assert states[0] == StepState.INIT
    assert StepState.THINKING in states
    assert states[-1] == StepState.DONE
    # 至少有 2 个 llm_token
    tokens = [e for e in events if e.event_type == "llm_token"]
    assert len(tokens) == 2


async def test_run_step_with_acting(store):
    async def thinking_with_tool(input_):
        yield {"token": "calling tool"}
        # 在 token 流里附带 tool_calls（约定：thinking_fn 的最后一个 yield 可以含 tool_calls）
        yield {"token": "", "tool_calls": [{"tool": "read_file"}]}

    events = []
    async for e in run_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store, thinking_with_tool, acting_fn
    ):
        events.append(e)

    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert tool_results[0].output["content"] == "executed:read_file"
    assert tool_results[0].output["is_exe_success"] is True


async def test_crash_recovery_resumes_awaiting(store):
    """模拟跑到 AWAITING_USER 后崩溃，resume 后状态恢复。"""
    # 先跑一步，停在 awaiting（用特殊 thinking_fn 模拟）
    async def thinking_awaiting(input_):
        yield {"token": "need user input", "await_user": True}

    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store, thinking_awaiting):
        events.append(e)

    # 确认停在 AWAITING_USER
    rc = RecoveryCoordinatorV2(store)
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "resume_awaiting"
    assert decision["state"] == StepState.AWAITING_USER

    # 重放事件
    replayed = await rc.replay_events("conv-1")
    assert len(replayed) == len(events)


async def test_resume_step_redoes_incomplete(store):
    """step 停在 THINKING（崩溃），resume 后重做该 step。"""
    # 手动塞一个 THINKING 事件模拟崩溃
    from derisk.agent.core.v2.event_stream import EventStream
    from derisk.agent.core.v2.step_event import StepEvent
    stream = EventStream(store)
    await stream.emit(StepEvent(
        event_id="evt-pre",
        step_id="step-pre",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.THINKING,
        event_type="llm_token",
        input={"prompt": "hi"},
        output={"token": "partial"},
        seq=0,
        timestamp=0.0,
    ))

    rc = RecoveryCoordinatorV2(store)
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "redo_step"
    assert decision["step_id"] == "step-pre"

    # resume_step 应该重做该 step
    events = []
    async for e in resume_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store, thinking_fn,
        step_id="step-pre"
    ):
        events.append(e)
    # 重做后应该到 DONE
    assert events[-1].state == StepState.DONE
