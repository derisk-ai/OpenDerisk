"""default_thinking_fn 测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from derisk.agent.core.v2.default_thinking import make_default_thinking_fn
from derisk.agent.core.v2.thinking_chunk import TokenChunk, ToolCallChunk


async def _fake_llm_stream(messages, model):
    yield {"token": "hello", "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}}
    yield {"token": " world"}


async def test_yields_token_chunks():
    context_engine = MagicMock()
    build_out = MagicMock()
    build_out.messages = [{"role": "user", "content": "hi"}]
    context_engine.build_messages = AsyncMock(return_value=build_out)

    thinking_fn = make_default_thinking_fn(
        llm_stream_fn=lambda messages, model: _fake_llm_stream(messages, model),
        model_alias="test-model",
        context_engine=context_engine,
        memory_bundle=None,
        get_session_messages=lambda sid: [],
        get_work_log=lambda cid: [],
        get_context_window=lambda model: 128000,
    )
    chunks = []
    async for c in thinking_fn({"prompt": "hi", "conv_id": "c1", "session_id": "s1"}):
        chunks.append(c)
    # 至少 2 个 token chunk
    tokens = [c for c in chunks if isinstance(c, TokenChunk)]
    assert len(tokens) >= 2
    assert tokens[0].token == "hello"


async def test_scrubs_token_through_memory_pipeline():
    """memory_bundle.pipeline.scrub_stream_delta 应被调用清洗 token。"""
    context_engine = MagicMock()
    build_out = MagicMock()
    build_out.messages = [{"role": "user", "content": "hi"}]
    context_engine.build_messages = AsyncMock(return_value=build_out)

    pipeline = MagicMock()
    pipeline.scrub_stream_delta = MagicMock(side_effect=lambda t: t.replace("<memory-context>", ""))
    pipeline.consume_prefetch = AsyncMock(return_value=None)
    bundle = MagicMock()
    bundle.pipeline = pipeline
    bundle.manager = MagicMock()
    bundle.manager.retrieve_relevant_memories = AsyncMock(return_value="")

    thinking_fn = make_default_thinking_fn(
        llm_stream_fn=lambda m, mo: _fake_llm_stream(m, mo),
        model_alias="test",
        context_engine=context_engine,
        memory_bundle=bundle,
        get_session_messages=lambda sid: [],
        get_work_log=lambda cid: [],
        get_context_window=lambda model: 128000,
    )
    chunks = []
    async for c in thinking_fn({"prompt": "hi", "conv_id": "c1", "session_id": "s1"}):
        chunks.append(c)
    # scrubber 至少被调用过
    assert pipeline.scrub_stream_delta.called
