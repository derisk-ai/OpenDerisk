"""default_thinking_fn + run_loop 端到端集成测试。"""
import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock

from derisk.agent.core.v2.run_loop import run_loop
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.default_thinking import make_default_thinking_fn
from derisk.agent.core.v2.default_acting import make_default_acting_fn
from derisk.agent.core.v2.tool_resolver import ToolResolver
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.thinking_chunk import AwaitUserChunk


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def test_default_thinking_fn_with_run_loop_end_to_end(store):
    """验证 make_default_thinking_fn 产生的 ThinkingChunk 能被 runtime 正确消费。"""
    async def mock_llm_stream(messages, model):
        yield {"token": "Hello"}
        yield {"token": " world"}
        yield {"tool_calls": [{"tool": "echo", "input": {"text": "hi"}}]}
        yield {"token": "Final answer"}

    context_engine = MagicMock()
    build_out = MagicMock()
    build_out.messages = [{"role": "user", "content": "hi"}]
    context_engine.build_messages = AsyncMock(return_value=build_out)

    class FakeEchoTool:
        name = "echo"
        async def execute(self, args, context=None):
            from derisk.agent.core.v2.tool_call_types import V2ToolResult
            return V2ToolResult.ok(output=f"echo: {args.get('text', '')}", tool_name="echo")

    resolver = ToolResolver(system_tools={"echo": FakeEchoTool()})
    acting_fn = make_default_acting_fn(
        tool_resolver=resolver,
        doom_loop_detector=MagicMock(check=AsyncMock(return_value=True)),
        failure_tracker=ToolFailureTracker(max_failures=3),
        truncator=MagicMock(truncate=AsyncMock(return_value=MagicMock(truncated=False, truncated_content=""))),
        tool_context_factory=ToolContextFactory(agent_id="a1", conv_id="c1"),
    )

    thinking_fn = make_default_thinking_fn(
        llm_stream_fn=mock_llm_stream,
        model_alias="test-model",
        context_engine=context_engine,
        memory_bundle=None,
        get_session_messages=lambda sid: [],
        get_work_log=lambda cid: [],
        get_context_window=lambda m: 4096,
        system_prompt="You are a test agent.",
    )

    events = []
    async for e in run_loop(
        agent_id="a1",
        conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1", "conv_id": "c1"},
        state_store=store,
        thinking_fn=thinking_fn,
        acting_fn=acting_fn,
        max_steps=10,
    ):
        events.append(e)

    states = [e.state for e in events]
    assert StepState.THINKING in states
    assert StepState.DONE in states


async def test_await_user_chunk_emits_awaiting_user_state(store):
    """I2: AwaitUserChunk 触发 AWAITING_USER 状态。"""
    async def thinking_fn(input_):
        yield AwaitUserChunk(reason="need user confirmation")

    events = []
    async for e in run_loop(
        agent_id="a1",
        conv_id="c1",
        input_={"prompt": "hi", "session_id": "s1", "conv_id": "c1"},
        state_store=store,
        thinking_fn=thinking_fn,
        acting_fn=None,
        max_steps=10,
    ):
        events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_USER in states
    assert any(
        e.event_type == "interaction_request"
        and e.input.get("reason") == "need user confirmation"
        for e in events
    )