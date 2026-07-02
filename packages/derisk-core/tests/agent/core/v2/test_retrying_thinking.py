"""retrying_thinking 装饰器测试。"""
import pytest
from derisk.agent.core.v2.retrying_thinking import retrying_thinking
from derisk.agent.core.v2.thinking_chunk import TokenChunk


async def _stream_ok():
    yield TokenChunk(token="a")
    yield TokenChunk(token="b")


async def _stream_fail_once_then_succeed():
    """第一次抛异常，第二次成功。"""
    if not hasattr(_stream_fail_once_then_succeed, "_called"):
        _stream_fail_once_then_succeed._called = True
        raise RuntimeError("LLM error")
    yield TokenChunk(token="recovered")


async def _stream_always_fail():
    yield TokenChunk(token="x")
    raise RuntimeError("always fails")


async def test_no_retry_on_success():
    chunks = []
    async for c in retrying_thinking(_stream_ok, max_attempts=3):
        chunks.append(c)
    assert len(chunks) == 2
    assert chunks[0].token == "a"


async def test_retry_on_failure_then_success():
    chunks = []
    async for c in retrying_thinking(_stream_fail_once_then_succeed, max_attempts=3):
        chunks.append(c)
    assert len(chunks) == 1
    assert chunks[0].token == "recovered"


async def test_retry_exhausted_raises():
    with pytest.raises(RuntimeError, match="always fails"):
        async for _ in retrying_thinking(_stream_always_fail, max_attempts=3):
            pass


async def test_model_fallback_called():
    """model_fallback 在重试时被调用，传入上次失败的 model。"""
    fallback_calls = []
    def fallback(last_model):
        fallback_calls.append(last_model)
        return "fallback-model"

    # _stream_fail_once_then_succeed 已在前面测试中 _called=True，需要重置
    if hasattr(_stream_fail_once_then_succeed, "_called"):
        del _stream_fail_once_then_succeed._called

    async for _ in retrying_thinking(
        _stream_fail_once_then_succeed, max_attempts=3,
        model_fallback=fallback, initial_model="primary"
    ):
        pass
    assert len(fallback_calls) == 1
    assert fallback_calls[0] == "primary"
