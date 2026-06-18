"""BudgetLayerer 测试 —— Pass-1..4 无状态分层 + 剪枝 + 量化。"""

from derisk.agent.expand.react_master_agent.context_engine.layering import (
    BudgetLayerer,
    LayerBudgetConfig,
)
from derisk.agent.expand.react_master_agent.context_engine.timeline import (
    ResultStatus,
    Segment,
    TimelineUnit,
    ToolCallBinding,
    UnitKind,
)


def _user(seq, conv="c1", tokens=10, rounds=1):
    return TimelineUnit(
        kind=UnitKind.USER,
        conv_id=conv,
        message_id=f"u{seq}",
        rounds=rounds,
        created_at=float(seq),
        seq=seq,
        user_content=f"user{seq}",
        tokens=tokens,
    )


def _call(seq, tool, args=None, result="r", conv="c1", tokens=10, rounds=1, status=ResultStatus.OK):
    b = ToolCallBinding(
        tool_call_id=f"tc{seq}",
        tool_name=tool,
        args=args or {},
        result_status=status,
        result_text=result,
        tokens=tokens,
    )
    return TimelineUnit(
        kind=UnitKind.CALL,
        conv_id=conv,
        message_id=f"m{seq}",
        rounds=rounds,
        created_at=float(seq),
        seq=seq,
        ai_text="",
        calls=[b],
        tokens=tokens,
    )


def _seg(units, conv="c1"):
    return [Segment(conv_id=conv, units=units, first_rounds=units[0].rounds, first_created_at=units[0].created_at)]


def test_pass1_newest_to_oldest_budget():
    # window 大，全部进 hot
    units = [_user(0), _call(1, "fa"), _call(2, "fb")]
    plan = BudgetLayerer(LayerBudgetConfig()).layer(_seg(units), 100000, "c1")
    assert len(plan.hot) == 3
    assert not plan.warm
    assert not plan.cold


def test_oldest_goes_cold_when_budget_small():
    # 10 个单元各 100 token；window 小，最旧的沉 cold
    units = [_call(i, f"f{i}", tokens=100) for i in range(20)]
    cfg = LayerBudgetConfig(hot_ratio=0.2, warm_ratio=0.1, cold_ratio=0.5, cold_batch_units=4)
    # history window 已是传入值（engine 才乘 0.85），这里直接给 1000
    plan = BudgetLayerer(cfg).layer(_seg(units), 1000, "c1")
    assert plan.cold  # 有 cold 批次
    # 最新的在 hot
    assert plan.hot[-1].seq == 19


def test_preserve_tools_never_cold():
    cfg = LayerBudgetConfig(
        hot_ratio=0.05,
        warm_ratio=0.05,
        cold_ratio=0.5,
        preserve_tools_patterns={"view": ["skill.md"]},
        cold_batch_units=4,
    )
    # 一堆填充 + 一个很旧的 view skill.md
    preserved = _call(0, "view", args={"path": "x/skill.md"}, tokens=100)
    fillers = [_call(i, f"f{i}", tokens=100) for i in range(1, 20)]
    units = [preserved] + fillers
    plan = BudgetLayerer(cfg).layer(_seg(units), 800, "c1")
    cold_ids = {u.message_id for b in plan.cold for u in b}
    assert preserved.message_id not in cold_ids  # 强制不沉 cold


def test_anchor_user_never_cold():
    cfg = LayerBudgetConfig(hot_ratio=0.05, warm_ratio=0.05, cold_ratio=0.5, cold_batch_units=4)
    anchor = _user(0, conv="c1", tokens=100)
    fillers = [_call(i, f"f{i}", tokens=100) for i in range(1, 20)]
    units = [anchor] + fillers
    plan = BudgetLayerer(cfg).layer(_seg(units), 800, "c1")
    cold_ids = {u.message_id for b in plan.cold for u in b}
    assert anchor.message_id not in cold_ids


def test_pass2_dedup_duplicate_tools():
    # 两次相同 (tool, args)，旧的被剪。加 padding 使目标单元落在 warm（非 hot）。
    pad = _call(9, "pad", tokens=100)  # 最新，占满 hot
    u1 = _call(0, "fa", args={"q": "x"}, tokens=10)
    u2 = _call(1, "fa", args={"q": "x"}, tokens=10)
    cfg = LayerBudgetConfig(hot_ratio=0.1, warm_ratio=0.8, cold_ratio=0.05)
    # window 1000 → hot=100（容纳 pad），warm=800（容纳 u1/u2）
    plan = BudgetLayerer(cfg).layer(_seg([u1, u2, pad]), 1000, "c1")
    all_warm_bindings = [b for u in plan.warm for b in (u.calls or [])]
    pruned = [b for b in all_warm_bindings if b.pruned]
    assert any(b.tool_call_id == "tc0" for b in pruned)


def test_pass2_empty_result_pruned():
    pad = _call(9, "pad", tokens=100)
    u1 = _call(0, "fa", result="ok", tokens=10)
    cfg = LayerBudgetConfig(hot_ratio=0.1, warm_ratio=0.8, cold_ratio=0.05)
    plan = BudgetLayerer(cfg).layer(_seg([u1, pad]), 1000, "c1")
    bindings = [b for u in plan.warm for b in (u.calls or []) if b.tool_name == "fa"]
    assert bindings and bindings[0].pruned


def test_pass2_preserve_tools_not_pruned():
    # view 是 preserve_tools，空结果也不剪
    pad = _call(9, "pad", tokens=100)
    u1 = _call(0, "view", result="ok", tokens=10)
    cfg = LayerBudgetConfig(hot_ratio=0.1, warm_ratio=0.8, cold_ratio=0.05)
    plan = BudgetLayerer(cfg).layer(_seg([u1, pad]), 1000, "c1")
    bindings = [b for u in plan.warm for b in (u.calls or []) if b.tool_name == "view"]
    assert bindings and not bindings[0].pruned


def test_pass2_superseded_write_marked():
    # write(p) 后 read(p) → write 标记 superseded
    pad = _call(9, "pad", tokens=100)
    w = _call(0, "write", args={"path": "p"}, result="written", tokens=10)
    r = _call(1, "read", args={"path": "p"}, result="content", tokens=10)
    cfg = LayerBudgetConfig(hot_ratio=0.1, warm_ratio=0.8, cold_ratio=0.05)
    plan = BudgetLayerer(cfg).layer(_seg([w, r, pad]), 1000, "c1")
    write_bindings = [
        b for u in plan.warm for b in (u.calls or []) if b.tool_name == "write"
    ]
    assert write_bindings and write_bindings[0].superseded_content


def test_pass3_cold_batch_quantization():
    # 10 个 cold 单元，batch=4 → 8 个成 2 批，余 2 回 warm
    units = [_call(i, f"f{i}", tokens=100) for i in range(10)]
    cfg = LayerBudgetConfig(hot_ratio=0.001, warm_ratio=0.001, cold_ratio=0.9, cold_batch_units=4)
    plan = BudgetLayerer(cfg).layer(_seg(units), 100, "c1")
    total_cold = sum(len(b) for b in plan.cold)
    # cold 总数应是 4 的整数倍
    assert total_cold % 4 == 0


def test_pass4_single_rebalance_no_infinite_loop():
    # 仅验证 layer() 能正常返回（单次再平衡不死循环）
    units = [_call(i, f"f{i}", tokens=50) for i in range(30)]
    cfg = LayerBudgetConfig(hot_ratio=0.2, warm_ratio=0.2, cold_ratio=0.2, cold_batch_units=4)
    plan = BudgetLayerer(cfg).layer(_seg(units), 1000, "c1")
    # 守恒律：每个单元都有归属
    total = len(plan.hot) + len(plan.warm) + sum(len(b) for b in plan.cold)
    assert total == 30


def test_cleanup_hints_contain_cold_ids():
    units = [_call(i, f"f{i}", tokens=100) for i in range(12)]
    cfg = LayerBudgetConfig(hot_ratio=0.05, warm_ratio=0.05, cold_ratio=0.8, cold_batch_units=4)
    plan = BudgetLayerer(cfg).layer(_seg(units), 400, "c1")
    assert plan.cold_unit_message_ids
    # cold ids 都是真实 message_id（m*）
    assert all(i.startswith("m") for i in plan.cold_unit_message_ids)


def test_conservation_law():
    # 守恒律：hot + warm + cold 单元数 = 输入单元数（剪枝只打标不删单元）
    units = [_user(0)] + [_call(i, f"f{i}", tokens=50) for i in range(1, 25)]
    cfg = LayerBudgetConfig(hot_ratio=0.2, warm_ratio=0.2, cold_ratio=0.3, cold_batch_units=4)
    plan = BudgetLayerer(cfg).layer(_seg(units), 1000, "c1")
    total = len(plan.hot) + len(plan.warm) + sum(len(b) for b in plan.cold)
    assert total == len(units)
