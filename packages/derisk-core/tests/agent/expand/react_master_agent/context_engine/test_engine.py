"""ContextEngine 端到端测试（8 模块集成，无真实 LLM）。"""

import pytest

from derisk.agent.expand.react_master_agent.context_engine.engine import (
    ContextEngine,
    EngineConfig,
    InMemoryColdPersistence,
)
from derisk.agent.expand.react_master_agent.context_engine.layering import (
    LayerBudgetConfig,
)

from .conftest import CountingSummarizer, FakeMsg, FakeWE, RecordingEmitter, ai_tool_call


def _engine(summarize=None, cfg=None, emitter=None, persistence=None):
    return ContextEngine(
        config=cfg or EngineConfig(),
        cold_persistence=persistence or InMemoryColdPersistence(),
        summarize_fn=summarize,
        events=emitter or RecordingEmitter(),
    )


@pytest.mark.asyncio
async def test_build_messages_end_to_end_no_orphans():
    msgs = [
        FakeMsg("c1", "human", "m1", content="查天气", rounds=1, created_at=1.0),
        FakeMsg("c1", "ai", "m2", content="查", tool_calls=[ai_tool_call("tc1", "wx")], rounds=1, created_at=2.0),
        FakeMsg("c1", "ai", "m3", content="晴", rounds=1, created_at=4.0),
    ]
    wls = {"c1": [FakeWE("wx", "tc1", result="晴25度", message_id="m2")]}
    out = await _engine().build_messages(msgs, wls, "c1", "s", 100000)
    roles = [m["role"] for m in out.messages]
    assert roles == ["human", "ai", "tool", "ai"]
    assert out.guard_report.ok or not [
        v for v in out.guard_report.violations if v.startswith(("I1", "I2"))
    ]


@pytest.mark.asyncio
async def test_missing_results_never_loop():
    # 核心回归：缺失 WorkEntry 的 tool_call 既不渲染成 tool 消息，也不出现在 tool_calls
    msgs = [
        FakeMsg("c1", "human", "m1", content="两件事", rounds=1, created_at=1.0),
        FakeMsg(
            "c1",
            "ai",
            "m2",
            content="",
            tool_calls=[ai_tool_call("tc_ok", "fa"), ai_tool_call("tc_missing", "fb")],
            rounds=1,
            created_at=2.0,
        ),
    ]
    wls = {"c1": [FakeWE("fa", "tc_ok", result="A", message_id="m2")]}
    out = await _engine().build_messages(msgs, wls, "c1", "s", 100000)
    # 无 result-not-available
    assert not any(
        "result not available" in str(m.get("content", "")).lower() for m in out.messages
    )
    # tc_missing 不作为 tool 消息
    assert not any(m.get("tool_call_id") == "tc_missing" for m in out.messages)
    # tc_missing 不在任何 assistant tool_calls
    for m in out.messages:
        for t in m.get("tool_calls", []) or []:
            assert t["id"] != "tc_missing"


@pytest.mark.asyncio
async def test_returns_layer_tokens_and_cleanup_hints():
    msgs = [FakeMsg("c1", "human", "m1", content="hi", rounds=1, created_at=1.0)]
    out = await _engine().build_messages(msgs, {"c1": []}, "c1", "s", 100000)
    assert set(out.layer_tokens.keys()) == {"hot", "warm", "cold"}
    assert "can_evict_message_ids" in out.cleanup_hints


@pytest.mark.asyncio
async def test_cold_handoff_prepended_when_overflow():
    # 制造很多历史轮 → cold → 单条 handoff 置于最前
    msgs = []
    t = 0.0
    for r in range(1, 15):
        t += 1
        msgs.append(FakeMsg(f"c{r}", "human", f"u{r}", content="x" * 400, rounds=r, created_at=t))
        t += 1
        msgs.append(FakeMsg(f"c{r}", "ai", f"a{r}", content="y" * 400, rounds=r, created_at=t))
    # current 是最后一轮
    current = "c14"
    cfg = EngineConfig(
        layer=LayerBudgetConfig(hot_ratio=0.1, warm_ratio=0.1, cold_ratio=0.5, cold_batch_units=4),
        history_budget_ratio=1.0,
    )
    summ = CountingSummarizer("HISTORY_SUMMARY")
    out = await _engine(summarize=summ, cfg=cfg).build_messages(
        msgs, {f"c{r}": [] for r in range(1, 15)}, current, "s", 2000
    )
    assert out.handoff is not None
    # 第一条是 handoff（human）
    assert out.messages[0]["role"] == "human"
    assert "HISTORY_SUMMARY" in out.messages[0]["content"]


@pytest.mark.asyncio
async def test_no_messages_returns_empty():
    out = await _engine().build_messages([], {}, "c1", "s", 100000)
    assert out.messages == []


@pytest.mark.asyncio
async def test_pure_engine_no_storage_dependency():
    # 仅用内存假对象即可构建（证明引擎纯净，不碰 GptsMemory）
    msgs = [
        FakeMsg("c1", "human", "m1", content="q", rounds=1, created_at=1.0),
        FakeMsg("c1", "ai", "m2", content="a", rounds=1, created_at=2.0),
    ]
    out = await _engine().build_messages(msgs, {"c1": []}, "c1", "s", 100000)
    assert len(out.messages) == 2


@pytest.mark.asyncio
async def test_warm_tool_result_truncated():
    # 大量历史使旧工具结果进 warm 并被截断
    long_result = "Z" * 5000
    msgs = [
        FakeMsg("c1", "human", "m1", content="q", rounds=1, created_at=1.0),
        FakeMsg("c1", "ai", "m2", content="", tool_calls=[ai_tool_call("tc1", "fa")], rounds=1, created_at=2.0),
        FakeMsg("c1", "human", "m3", content="q2", rounds=2, created_at=3.0),
    ]
    wls = {"c1": [FakeWE("fa", "tc1", result=long_result, message_id="m2", tokens=1250)]}
    cfg = EngineConfig(
        layer=LayerBudgetConfig(hot_ratio=0.05, warm_ratio=0.5, cold_ratio=0.1, warm_tool_result_max_length=400),
        history_budget_ratio=1.0,
    )
    out = await _engine(cfg=cfg).build_messages(msgs, wls, "c1", "s", 1000)
    tool_msgs = [m for m in out.messages if m["role"] == "tool"]
    if tool_msgs:
        # warm 层结果应被截断（远小于 5000）
        assert len(str(tool_msgs[0]["content"])) < 5000
