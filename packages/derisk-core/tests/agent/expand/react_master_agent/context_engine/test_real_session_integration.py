"""真实数据路径全链路集成测试。

使用真实的 GptsMemory（消息经 pandas 序列化往返 + WorkEntry 真实缓存），
按 react_master_agent._compute_context_engine_messages 的同样方式驱动 ContextEngine，
验证生产数据通路（不依赖真实 LLM 服务）：
  - 多轮工具调用会话装配正确、顺序正确
  - 无 orphan tool_call / 无 [result not available] 死循环
  - 多轮上下文不丢
  - 缺失结果被结构性消除
"""

import uuid

import pytest

from derisk.agent.core.memory.gpts.base import GptsMessage
from derisk.agent.core.memory.gpts.file_base import WorkEntry
from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
from derisk.agent.core.memory.agent_memory import AgentMemory
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.expand.react_master_agent.context_engine import (
    ContextEngine,
    EngineConfig,
    InMemoryColdPersistence,
)
from derisk.agent.expand.react_master_agent.context_engine.layering import (
    LayerBudgetConfig,
)

from .conftest import CountingSummarizer, RecordingEmitter


def _msg(conv_id, session_id, role, content, rounds, tool_calls=None):
    mid = uuid.uuid4().hex
    return GptsMessage(
        conv_id=conv_id,
        conv_session_id=session_id,
        sender=role,
        sender_name=role,
        message_id=mid,
        role=role,
        content=content,
        rounds=rounds,
        tool_calls=tool_calls,
        data_version="v2",
    )


def _add_message(memory, msg):
    """直接写入 message_memory（真实 pandas 序列化往返），等价生产持久化结果。"""
    memory._message_memory.append(msg)


async def _load_and_build(
    memory, session_id, current_conv, summarizer=None, cfg=None, context_window=100000
):
    """复刻 react_master_agent._compute_context_engine_messages 的加载逻辑。"""
    messages = await memory.get_session_messages(session_id)
    conv_ids = {m.conv_id for m in messages}
    conv_ids.add(current_conv)
    work_logs_by_conv = {}
    for cid in conv_ids:
        work_logs_by_conv[cid] = await memory.get_work_log(cid)

    engine = ContextEngine(
        config=cfg or EngineConfig(),
        cold_persistence=InMemoryColdPersistence(),
        summarize_fn=summarizer,
        events=RecordingEmitter(),
    )
    return await engine.build_messages(
        messages=messages,
        work_logs_by_conv=work_logs_by_conv,
        current_conv_id=current_conv,
        session_id=session_id,
        context_window=context_window,
    )


@pytest.mark.asyncio
async def test_real_memory_single_turn_tool_call():
    memory = GptsMemory()
    session = "sess_real_1"
    conv = f"{session}_1"

    # 用户输入
    um = _msg(conv, session, "human", "查询北京天气", rounds=1)
    _add_message(memory, um)
    # AI 发起 tool_call
    tc_id = "call_abc"
    am = _msg(
        conv,
        session,
        "assistant",
        "我来查询",
        rounds=1,
        tool_calls=[
            {"id": tc_id, "type": "function", "function": {"name": "get_weather", "arguments": '{"city":"北京"}'}}
        ],
    )
    _add_message(memory, am)
    # 工具结果写入 work_log
    await memory.append_work_entry(
        conv,
        WorkEntry(
            timestamp=1.0,
            tool="get_weather",
            tool_call_id=tc_id,
            result="北京 晴 25℃",
            message_id=am.message_id,
            success=True,
        ),
        save_db=False,
    )

    out = await _load_and_build(memory, session, conv)
    roles = [m["role"] for m in out.messages]
    # human -> ai(with tool_call) -> tool
    assert "human" in roles and "ai" in roles and "tool" in roles
    tool_msg = [m for m in out.messages if m["role"] == "tool"][0]
    assert "北京" in str(tool_msg["content"])
    assert out.guard_report.ok or not [
        v for v in out.guard_report.violations if v.startswith(("I1", "I2"))
    ]


@pytest.mark.asyncio
async def test_real_memory_missing_result_no_loop():
    """核心回归：work_log 缺一条结果，不得产生 orphan / 死循环。"""
    memory = GptsMemory()
    session = "sess_real_2"
    conv = f"{session}_1"

    _add_message(memory, _msg(conv, session, "human", "做两件事", rounds=1))
    am = _msg(
        conv,
        session,
        "assistant",
        "",
        rounds=1,
        tool_calls=[
            {"id": "ok1", "type": "function", "function": {"name": "fa", "arguments": "{}"}},
            {"id": "missing1", "type": "function", "function": {"name": "fb", "arguments": "{}"}},
        ],
    )
    _add_message(memory, am)
    # 只写 ok1 的结果，missing1 缺失
    await memory.append_work_entry(
        conv,
        WorkEntry(timestamp=1.0, tool="fa", tool_call_id="ok1", result="A", message_id=am.message_id),
        save_db=False,
    )

    out = await _load_and_build(memory, session, conv)
    # 无 result-not-available
    assert not any(
        "result not available" in str(m.get("content", "")).lower() for m in out.messages
    )
    # missing1 不作为 tool 消息、不在 tool_calls
    assert not any(m.get("tool_call_id") == "missing1" for m in out.messages)
    for m in out.messages:
        for t in m.get("tool_calls", []) or []:
            assert t["id"] != "missing1"


@pytest.mark.asyncio
async def test_real_memory_multiturn_context_preserved():
    """多轮（多 conv_id）上下文不丢。"""
    memory = GptsMemory()
    session = "sess_real_3"

    for i in range(1, 4):
        conv = f"{session}_{i}"
        _add_message(memory, _msg(conv, session, "human", f"问题{i}", rounds=i))
        _add_message(memory, _msg(conv, session, "assistant", f"回答{i}", rounds=i))

    current = f"{session}_3"
    out = await _load_and_build(memory, session, current)
    all_text = " ".join(str(m.get("content", "")) for m in out.messages)
    # 三轮问答都在
    for i in range(1, 4):
        assert f"问题{i}" in all_text
        assert f"回答{i}" in all_text


@pytest.mark.asyncio
async def test_real_memory_long_session_triggers_cold_handoff():
    """长会话触发 cold 压缩，产出单条 handoff，且不丢当前轮。"""
    memory = GptsMemory()
    session = "sess_real_4"

    for i in range(1, 13):
        conv = f"{session}_{i}"
        _add_message(memory, _msg(conv, session, "human", "X" * 500, rounds=i))
        _add_message(memory, _msg(conv, session, "assistant", "Y" * 500, rounds=i))

    current = f"{session}_12"
    summ = CountingSummarizer("COMPRESSED_HISTORY")
    cfg = EngineConfig(
        layer=LayerBudgetConfig(
            hot_ratio=0.1, warm_ratio=0.1, cold_ratio=0.5, cold_batch_units=4
        ),
        history_budget_ratio=1.0,
    )
    # 24 条 × ~125 token ≈ 3000 token；给 800 的 window 逼出 cold
    out = await _load_and_build(
        memory, session, current, summarizer=summ, cfg=cfg, context_window=800
    )
    # 触发了压缩
    assert summ.calls >= 1
    assert out.handoff is not None
    # handoff 在最前
    assert out.messages[0]["role"] == "human"
    assert "COMPRESSED_HISTORY" in out.messages[0]["content"]
    # 守恒：guard 通过
    assert not [
        v for v in out.guard_report.violations if v.startswith(("I1", "I2", "I3"))
    ]


@pytest.mark.asyncio
async def test_real_agent_compute_context_engine_messages():
    """直接驱动真实 ReActMasterAgent 的生产方法 _compute_context_engine_messages。

    验证整条接入链路：agent → GptsMemory 加载 → ContextEngine 构建 →
    多 tool_call 原子渲染、缺失结果结构性消除、guard 通过。
    """
    gm = GptsMemory()
    session = "agent_chain"
    conv = f"{session}_1"
    _add_message(gm, _msg(conv, session, "human", "查天气并读config", rounds=1))
    am = _msg(
        conv,
        session,
        "assistant",
        "执行",
        rounds=1,
        tool_calls=[
            {"id": "t1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
            {"id": "t2", "type": "function", "function": {"name": "read", "arguments": '{"path":"config.yaml"}'}},
            {"id": "t_missing", "type": "function", "function": {"name": "broken", "arguments": "{}"}},
        ],
    )
    _add_message(gm, am)
    await gm.append_work_entry(
        conv,
        WorkEntry(timestamp=1.0, tool="get_weather", tool_call_id="t1", result="晴 25℃", message_id=am.message_id),
        save_db=False,
    )
    await gm.append_work_entry(
        conv,
        WorkEntry(timestamp=2.0, tool="read", tool_call_id="t2", result="key: val", message_id=am.message_id),
        save_db=False,
    )
    # t_missing 故意不写结果

    agent = ReActMasterAgent()
    agent.memory = AgentMemory(gpts_memory=gm)

    out = await agent._compute_context_engine_messages(conv, session, 100000)
    assert out is not None
    roles = [m["role"] for m in out.messages]
    # human → ai(2 个有效 tool_call) → tool ×2
    assert roles == ["human", "ai", "tool", "tool"]
    ai = [m for m in out.messages if m["role"] == "ai"][0]
    tc_ids = [t["id"] for t in ai["tool_calls"]]
    assert tc_ids == ["t1", "t2"]  # t_missing 被消除
    # 无死循环标记
    assert not any(
        "result not available" in str(m.get("content", "")).lower() for m in out.messages
    )
    assert not any(m.get("tool_call_id") == "t_missing" for m in out.messages)
    assert out.guard_report.ok or not [
        v for v in out.guard_report.violations if v.startswith(("I1", "I2"))
    ]

