"""ColdSummarizer 测试 —— 全量重整 / 缓存 / 恢复 / 降级。"""

import pytest

from derisk.agent.expand.react_master_agent.context_engine.engine import (
    InMemoryColdPersistence,
)
from derisk.agent.expand.react_master_agent.context_engine.summarizer import (
    ColdSummarizer,
    HandoffMessage,
)
from derisk.agent.expand.react_master_agent.context_engine.timeline import (
    ResultStatus,
    TimelineUnit,
    ToolCallBinding,
    UnitKind,
)

from .conftest import CountingSummarizer, RecordingEmitter


def _cold_unit(seq, text="hello", tokens=10):
    return TimelineUnit(
        kind=UnitKind.USER,
        conv_id="c1",
        message_id=f"m{seq}",
        rounds=1,
        created_at=float(seq),
        seq=seq,
        user_content=text,
        tokens=tokens,
    )


def _batches(n, batch=4):
    units = [_cold_unit(i) for i in range(n)]
    return [units[i : i + batch] for i in range(0, n, batch)]


@pytest.mark.asyncio
async def test_full_reintegration_single_handoff():
    summ = CountingSummarizer("SUMMARY")
    cs = ColdSummarizer(summ, InMemoryColdPersistence(), events=RecordingEmitter())
    handoff = await cs.summarize_cold(_batches(8), "c1", "s")
    assert isinstance(handoff, HandoffMessage)
    msg = handoff.to_message()
    assert msg["role"] == "human"
    assert "SUMMARY" in msg["content"]
    # 单条
    assert isinstance(msg["content"], str)


@pytest.mark.asyncio
async def test_content_hash_stable_cache_hit():
    summ = CountingSummarizer("S")
    cs = ColdSummarizer(summ, InMemoryColdPersistence())
    b = _batches(8)
    await cs.summarize_cold(b, "c1", "s")
    await cs.summarize_cold(b, "c1", "s")  # 同样 cold → 命中内存缓存
    assert summ.calls == 1


@pytest.mark.asyncio
async def test_resume_reads_from_persistence_no_model_call():
    persistence = InMemoryColdPersistence()
    summ1 = CountingSummarizer("S")
    cs1 = ColdSummarizer(summ1, persistence)
    b = _batches(8)
    await cs1.summarize_cold(b, "c1", "s")
    assert summ1.calls == 1

    # 模拟新进程：新 summarizer 实例，内存缓存为空，但持久化命中
    summ2 = CountingSummarizer("S")
    cs2 = ColdSummarizer(summ2, persistence)
    handoff = await cs2.summarize_cold(b, "c1", "s")
    assert summ2.calls == 0  # 不调模型
    assert "S" in handoff.content


@pytest.mark.asyncio
async def test_degrade_on_llm_failure():
    summ = CountingSummarizer(raises=True)
    emitter = RecordingEmitter()
    cs = ColdSummarizer(summ, InMemoryColdPersistence(), events=emitter)
    handoff = await cs.summarize_cold(_batches(8), "c1", "s")
    assert handoff.degraded
    assert "COMPRESSION_LLM_FAILED" in emitter.types()


@pytest.mark.asyncio
async def test_degraded_not_persisted():
    persistence = InMemoryColdPersistence()
    summ = CountingSummarizer(raises=True)
    cs = ColdSummarizer(summ, persistence)
    b = _batches(8)
    await cs.summarize_cold(b, "c1", "s")
    # 降级不持久化：新实例（healthy）应重新调用模型
    summ2 = CountingSummarizer("OK")
    cs2 = ColdSummarizer(summ2, persistence)
    await cs2.summarize_cold(b, "c1", "s")
    assert summ2.calls == 1


@pytest.mark.asyncio
async def test_summarize_fn_none_truncates():
    cs = ColdSummarizer(None, InMemoryColdPersistence())
    handoff = await cs.summarize_cold(_batches(4), "c1", "s")
    assert handoff.degraded  # 无 LLM → 截断兜底


@pytest.mark.asyncio
async def test_empty_cold_returns_none():
    cs = ColdSummarizer(CountingSummarizer(), InMemoryColdPersistence())
    assert await cs.summarize_cold([], "c1", "s") is None


@pytest.mark.asyncio
async def test_new_cold_unit_changes_hash():
    summ = CountingSummarizer("S")
    cs = ColdSummarizer(summ, InMemoryColdPersistence())
    await cs.summarize_cold(_batches(8), "c1", "s")
    # 增加一个单元 → hash 变 → 重算
    await cs.summarize_cold(_batches(12), "c1", "s")
    assert summ.calls == 2


@pytest.mark.asyncio
async def test_compression_events_emitted():
    emitter = RecordingEmitter()
    cs = ColdSummarizer(CountingSummarizer("S"), InMemoryColdPersistence(), events=emitter)
    await cs.summarize_cold(_batches(8), "c1", "s")
    assert "COMPRESSION_START" in emitter.types()
    assert "COMPRESSION_COMPLETE" in emitter.types()
