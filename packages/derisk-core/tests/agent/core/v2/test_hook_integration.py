"""hook_integration context 构造测试。"""
from derisk.agent.core.v2.hook_integration import (
    build_pre_tool_use_context,
    build_post_tool_use_context,
    build_turn_complete_context,
    build_conversation_complete_context,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall
from derisk.agent.tools.context import ToolContext


def test_pre_tool_use_context():
    tc = V2ToolCall(name="bash", args={"cmd": "ls"})
    ctx = ToolContext(agent_id="a1", conversation_id="c1")
    result = build_pre_tool_use_context(tc, ctx)
    assert result["tool_name"] == "bash"
    assert result["args"] == {"cmd": "ls"}
    assert result["context"] is ctx
    assert result["conv_id"] == "c1"
    assert result["agent_id"] == "a1"


def test_post_tool_use_context_with_result():
    from derisk.agent.core.v2.tool_call_types import V2ToolResult
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext(agent_id="a1", conversation_id="c1")
    result = V2ToolResult.ok(output="done", tool_name="bash")
    out = build_post_tool_use_context(tc, ctx, result)
    assert out["tool_name"] == "bash"
    assert out["result"] is result
    assert out["error"] is None


def test_post_tool_use_context_with_error():
    tc = V2ToolCall(name="bash", args={})
    ctx = ToolContext(agent_id="a1", conversation_id="c1")
    out = build_post_tool_use_context(tc, ctx, None, error="boom")
    assert out["error"] == "boom"
    assert out["result"] is None


def test_turn_complete_context():
    out = build_turn_complete_context(
        round=3, interrupted=False, user_prompt="hi",
        final_answer="hello", user_id="u1", conv_id="c1", agent_id="a1", step_count=5,
    )
    assert out["round"] == 3
    assert out["interrupted"] is False
    assert out["user_prompt"] == "hi"
    assert out["final_answer"] == "hello"
    assert out["user_id"] == "u1"
    assert out["conv_id"] == "c1"
    assert out["agent_id"] == "a1"
    assert out["step_count"] == 5


def test_conversation_complete_context():
    out = build_conversation_complete_context(
        conv_id="c1", agent_id="a1", user_id="u1", total_rounds=10,
    )
    assert out["conv_id"] == "c1"
    assert out["total_rounds"] == 10
