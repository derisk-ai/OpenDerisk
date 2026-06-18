"""InvariantGuard 测试 —— I1–I6 + repair 幂等。"""

from derisk.agent.expand.react_master_agent.context_engine.invariants import (
    InvariantGuard,
)


def _ai_with_calls(*ids):
    return {
        "role": "ai",
        "content": "",
        "tool_calls": [
            {"id": i, "type": "function", "function": {"name": "f", "arguments": "{}"}}
            for i in ids
        ],
    }


def _tool(tcid, content="r"):
    return {"role": "tool", "tool_call_id": tcid, "content": content}


def test_I1_orphan_tool_dropped():
    msgs = [
        {"role": "human", "content": "q"},
        _tool("orphan", "stray"),  # 无前序声明
    ]
    repaired, report = InvariantGuard().repair(msgs)
    assert not any(m["role"] == "tool" for m in repaired)
    assert any("I1" in v for v in report.violations)


def test_I2_unanswered_toolcall_stripped():
    # 声明 tc1 + tc2，但只有 tc1 有结果 → tc2 被剥离，绝不造 result-not-available
    msgs = [
        {"role": "human", "content": "q"},
        _ai_with_calls("tc1", "tc2"),
        _tool("tc1", "A"),
    ]
    repaired, report = InvariantGuard().repair(msgs)
    ai = [m for m in repaired if m["role"] == "ai"][0]
    ids = [t["id"] for t in ai.get("tool_calls", [])]
    assert ids == ["tc1"]
    assert "tc2" not in str(repaired)
    assert not any("result not available" in str(m.get("content", "")).lower() for m in repaired)


def test_I2_all_unanswered_drops_empty_assistant():
    msgs = [
        {"role": "human", "content": "q"},
        _ai_with_calls("tcX"),  # 无结果，content 空 → 整条丢弃
    ]
    repaired, _ = InvariantGuard().repair(msgs)
    assert not any(m["role"] == "ai" for m in repaired)


def test_valid_sequence_passes():
    msgs = [
        {"role": "human", "content": "q"},
        _ai_with_calls("tc1"),
        _tool("tc1", "A"),
        {"role": "ai", "content": "done"},
    ]
    report = InvariantGuard().check(msgs)
    # I1/I2 无违规
    assert not [v for v in report.violations if v.startswith(("I1", "I2"))]


def test_I5_dedup_adjacent_human():
    msgs = [
        {"role": "human", "content": "same"},
        {"role": "human", "content": "same"},
    ]
    repaired, report = InvariantGuard().repair(msgs)
    humans = [m for m in repaired if m["role"] == "human"]
    assert len(humans) == 1
    assert any("I5" in v for v in report.violations)


def test_I6_dedup_adjacent_tool():
    msgs = [
        {"role": "human", "content": "q"},
        _ai_with_calls("tc1"),
        _tool("tc1", "A"),
        _tool("tc1", "A"),  # 相邻重复
    ]
    repaired, report = InvariantGuard().repair(msgs)
    tools = [m for m in repaired if m["role"] == "tool"]
    assert len(tools) == 1


def test_repair_idempotent():
    msgs = [
        {"role": "human", "content": "q"},
        _ai_with_calls("tc1", "tc2"),
        _tool("tc1", "A"),
        _tool("orphan"),
    ]
    once, _ = InvariantGuard().repair(msgs)
    twice, report2 = InvariantGuard().repair(once)
    assert once == twice  # 幂等
    # 第二次无需修复
    assert not report2.repairs
