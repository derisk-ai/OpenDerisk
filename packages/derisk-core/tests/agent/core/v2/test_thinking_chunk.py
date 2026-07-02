"""ThinkingChunk typed union 测试。"""
from derisk.agent.core.v2.thinking_chunk import (
    ThinkingChunk, TokenChunk, ToolCallChunk, UsageChunk,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult


def test_token_chunk():
    chunk = TokenChunk(token="hello", usage=None)
    assert chunk.token == "hello"
    assert chunk.usage is None


def test_token_chunk_with_usage():
    chunk = TokenChunk(token="hi", usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
    assert chunk.usage["total_tokens"] == 12


def test_tool_call_chunk():
    tc = V2ToolCall(name="read_file", args={"path": "/tmp/x"})
    chunk = ToolCallChunk(tool_calls=[tc])
    assert len(chunk.tool_calls) == 1
    assert chunk.tool_calls[0].name == "read_file"


def test_usage_chunk():
    chunk = UsageChunk(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
    assert chunk.usage["total_tokens"] == 12


def test_thinking_chunk_union():
    t: ThinkingChunk = TokenChunk(token="x")
    assert isinstance(t, TokenChunk)