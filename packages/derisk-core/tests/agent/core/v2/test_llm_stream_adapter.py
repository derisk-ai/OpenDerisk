"""derisk_llm stream 适配器测试。"""
import pytest
from unittest.mock import MagicMock
from derisk.agent.core.v2.llm_stream_adapter import make_derisk_llm_stream, make_derisk_llm_stream_fn


async def _fake_derisk_stream(model, messages):
    """模拟 derisk_llm 的 stream 输出（delta 格式）。"""
    yield {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}
    yield {"choices": [{"delta": {"content": " world"}, "finish_reason": None}]}
    yield {
        "choices": [{"delta": {}, "finish_reason": "tool_calls",
                     "message": {"tool_calls": [{"function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'}}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


async def test_adapter_yields_tokens():
    stream = make_derisk_llm_stream(_fake_derisk_stream)
    chunks = []
    async for c in stream([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)
    tokens = [c for c in chunks if c.get("token")]
    assert "".join(c["token"] for c in tokens) == "hello world"


async def test_adapter_yields_tool_calls():
    stream = make_derisk_llm_stream(_fake_derisk_stream)
    chunks = []
    async for c in stream([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)
    tool_call_chunks = [c for c in chunks if c.get("tool_calls")]
    assert len(tool_call_chunks) == 1
    assert tool_call_chunks[0]["tool_calls"][0]["tool"] == "read_file"
    assert tool_call_chunks[0]["tool_calls"][0]["input"] == {"path": "/tmp/x"}


async def test_adapter_yields_usage():
    stream = make_derisk_llm_stream(_fake_derisk_stream)
    chunks = []
    async for c in stream([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)
    usage_chunks = [c for c in chunks if c.get("usage")]
    assert len(usage_chunks) >= 1
    assert usage_chunks[-1]["usage"]["total_tokens"] == 15


# --- make_derisk_llm_stream_fn tests ---


async def test_stream_fn_yields_tokens():
    """make_derisk_llm_stream_fn wraps LLMClient.generate_stream → token chunks."""
    from derisk.core.interface.llm import ModelOutput

    llm_client = MagicMock()

    async def _fake_stream(request):
        yield ModelOutput(error_code=0, text="Hello")
        yield ModelOutput(error_code=0, text=" world")
        yield ModelOutput(
            error_code=0,
            text="",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        )

    llm_client.generate_stream = _fake_stream

    stream_fn = make_derisk_llm_stream_fn(llm_client, model_alias="test-model")
    chunks = []
    async for c in stream_fn([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)

    tokens = [c for c in chunks if c.get("token")]
    assert "".join(c["token"] for c in tokens) == "Hello world"


async def test_stream_fn_yields_tool_calls():
    """make_derisk_llm_stream_fn normalizes tool_calls from ModelOutput."""
    from derisk.core.interface.llm import ModelOutput

    llm_client = MagicMock()

    async def _fake_stream(request):
        yield ModelOutput(
            error_code=0,
            text="Let me check.",
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "/tmp/x"}',
                    },
                }
            ],
        )
        yield ModelOutput(
            error_code=0,
            text="",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    llm_client.generate_stream = _fake_stream

    stream_fn = make_derisk_llm_stream_fn(llm_client, model_alias="test-model")
    chunks = []
    async for c in stream_fn([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)

    tool_call_chunks = [c for c in chunks if c.get("tool_calls")]
    assert len(tool_call_chunks) == 1
    assert tool_call_chunks[0]["tool_calls"][0]["tool"] == "read_file"
    assert tool_call_chunks[0]["tool_calls"][0]["input"] == {"path": "/tmp/x"}


async def test_stream_fn_handles_string_tool_calls():
    """make_derisk_llm_stream_fn handles tool_calls as JSON string."""
    from derisk.core.interface.llm import ModelOutput
    import json

    llm_client = MagicMock()

    async def _fake_stream(request):
        yield ModelOutput(
            error_code=0,
            text="ok",
            tool_calls=json.dumps([
                {
                    "id": "call_1",
                    "function": {
                        "name": "search",
                        "arguments": '{"query": "test"}',
                    },
                }
            ]),
        )

    llm_client.generate_stream = _fake_stream

    stream_fn = make_derisk_llm_stream_fn(llm_client, model_alias="test-model")
    chunks = []
    async for c in stream_fn([{"role": "user", "content": "hi"}], "test-model"):
        chunks.append(c)

    tool_call_chunks = [c for c in chunks if c.get("tool_calls")]
    assert len(tool_call_chunks) == 1
    assert tool_call_chunks[0]["tool_calls"][0]["tool"] == "search"
