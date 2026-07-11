"""RFC-005 §3.2/§3.8 InputBundle 数据模型单测。

覆盖:
- AC-1  四槽位合并 / 排序 / freeze
- AC-14 Lifetime×CacheScope 矩阵合法/非法
- AC-15 排序确定且跨轮稳定;降级拼 str 与块数组路径同序
- AC-16 cache_control 挂载:仅在 scope 最后一块;≤4 含 history;超限按优先级丢
"""

import pytest

from derisk.core.interface.resource.bundle import CacheControlPoint, CacheScope, Contribution, FrozenBundle, InputBundle, Lifetime, Slot
# 构造辅助
# --------------------------------------------------------------------------- #
def _sys(text, scope=CacheScope.NONE, cap="cap", order=0, lifetime=Lifetime.CONFIG_STATIC):
    return Contribution(
        capability_id=cap,
        slot=Slot.SYSTEM,
        content=text,
        lifetime=lifetime,
        cache_scope=scope,
        order=order,
    )


# --------------------------------------------------------------------------- #
# AC-1 四槽位合并 / freeze
# --------------------------------------------------------------------------- #
def test_add_routes_to_correct_slot():
    """AC-1: Contribution 按 slot 落入对应槽位。"""
    bundle = InputBundle()
    bundle.add(_sys("identity", CacheScope.GLOBAL))
    bundle.add(Contribution("cap", Slot.USER_PART, "hello"))
    bundle.add(Contribution("cap", Slot.TOOLS, {"name": "t"}))
    bundle.add(Contribution("cap", Slot.VAR, ("k", "v")))

    assert len(bundle.system) == 1
    assert len(bundle.user_parts) == 1
    assert len(bundle.tools) == 1
    assert bundle.vars["k"].content == ("k", "v")


def test_freeze_produces_immutable_snapshot():
    """AC-1: freeze 产出不可变 FrozenBundle,后续对 bundle 的修改不影响快照。"""
    bundle = InputBundle()
    bundle.add(_sys("a", CacheScope.GLOBAL))
    bundle.add(_sys("b", CacheScope.USER))

    frozen = bundle.freeze(config_hash="h1", protocol_version=1)

    assert isinstance(frozen, FrozenBundle)
    assert frozen.config_hash == "h1"
    assert frozen.protocol_version == 1
    # 冻结后修改 bundle 不影响快照
    bundle.add(_sys("c", CacheScope.ENV))
    assert len(frozen.system) == 2


def test_freeze_freezes_each_block_text():
    """AC-1: 非字符串 content 在 freeze 时转为 str。"""
    bundle = InputBundle()
    bundle.add(Contribution("cap", Slot.SYSTEM, {"x": 1}, CacheScope.GLOBAL))
    frozen = bundle.freeze()
    assert frozen.system[0].text == "{'x': 1}"


# --------------------------------------------------------------------------- #
# AC-14 Lifetime×CacheScope 矩阵合法/非法
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "lifetime,scope,valid",
    [
        (Lifetime.CONFIG_STATIC, CacheScope.GLOBAL, True),
        (Lifetime.CONFIG_STATIC, CacheScope.USER, True),
        (Lifetime.CONFIG_STATIC, CacheScope.ENV, True),
        (Lifetime.CONFIG_STATIC, CacheScope.NONE, True),
        (Lifetime.SESSION, CacheScope.GLOBAL, False),   # 非法
        (Lifetime.SESSION, CacheScope.USER, True),
        (Lifetime.SESSION, CacheScope.ENV, True),
        (Lifetime.SESSION, CacheScope.NONE, True),
        (Lifetime.TURN, CacheScope.NONE, True),
        (Lifetime.TURN, CacheScope.GLOBAL, False),      # 非法
        (Lifetime.TURN, CacheScope.USER, False),        # 非法
        (Lifetime.TURN, CacheScope.ENV, False),         # 非法
    ],
)
def test_lifetime_cache_scope_matrix(lifetime, scope, valid):
    """AC-14: 矩阵合法/非法组合在 Contribution 构造时校验。"""
    if valid:
        c = Contribution(
            "cap", Slot.SYSTEM, "x", lifetime=lifetime, cache_scope=scope
        )
        assert c.lifetime == lifetime
        assert c.cache_scope == scope
    else:
        with pytest.raises(ValueError, match="Illegal Lifetime"):
            Contribution(
                "cap", Slot.SYSTEM, "x", lifetime=lifetime, cache_scope=scope
            )


# --------------------------------------------------------------------------- #
# AC-15 排序:先 scope 优先级分桶,再 order;跨轮稳定;双路径同序
# --------------------------------------------------------------------------- #
def test_sort_system_by_scope_then_order():
    """AC-15: 先按 cache_scope 优先级(GLOBAL<USER<ENV<NONE),桶内按 order。"""
    bundle = InputBundle()
    # 故意乱序插入
    bundle.add(_sys("env1", CacheScope.ENV, order=0))
    bundle.add(_sys("none1", CacheScope.NONE, order=0))
    bundle.add(_sys("user2", CacheScope.USER, order=1))
    bundle.add(_sys("user1", CacheScope.USER, order=0))
    bundle.add(_sys("global2", CacheScope.GLOBAL, order=1))
    bundle.add(_sys("global1", CacheScope.GLOBAL, order=0))

    ordered = [b.text for b in bundle.freeze().system]

    assert ordered == [
        "global1", "global2",  # GLOBAL 桶,order 升序
        "user1", "user2",      # USER 桶
        "env1",                # ENV 桶
        "none1",               # NONE 桶
    ]


def test_order_does_not_cross_scope():
    """AC-15: order 不能跨 scope 重排(用一个超大 order 的 GLOBAL 仍排在前)。"""
    bundle = InputBundle()
    bundle.add(_sys("user", CacheScope.USER, order=0))
    bundle.add(_sys("global", CacheScope.GLOBAL, order=9999))

    ordered = [b.text for b in bundle.freeze().system]
    # GLOBAL 优先级 0 < USER 优先级 1,故 global 仍在前,order=9999 不生效
    assert ordered == ["global", "user"]


def test_sort_is_stable_across_repeated_freeze():
    """AC-15: 排序跨轮稳定——同一 bundle 反复 freeze 顺序不变。"""
    bundle = InputBundle()
    for scope, order, text in [
        (CacheScope.NONE, 0, "n"),
        (CacheScope.GLOBAL, 1, "g2"),
        (CacheScope.GLOBAL, 0, "g1"),
        (CacheScope.USER, 0, "u"),
    ]:
        bundle.add(_sys(text, scope, order=order))

    first = [b.text for b in bundle.freeze().system]
    second = [b.text for b in bundle.freeze().system]
    assert first == second == ["g1", "g2", "u", "n"]


def test_degraded_str_same_order_as_blocks():
    """AC-15: 降级拼 str 与块数组路径同序,仅 separator 不同。

    用两个 separator 跑,断言切片顺序一致。
    """
    bundle = InputBundle()
    bundle.add(_sys("u", CacheScope.USER, order=0))
    bundle.add(_sys("g", CacheScope.GLOBAL, order=0))
    bundle.add(_sys("n", CacheScope.NONE, order=0))

    frozen = bundle.freeze()
    block_order = [b.text for b in frozen.system]

    legacy = frozen.merge_to_str(separator="\n\n---\n\n")
    native = frozen.merge_to_str(separator="\n\n")

    assert legacy.split("\n\n---\n\n") == block_order
    assert native.split("\n\n") == block_order


# --------------------------------------------------------------------------- #
# AC-16 cache_control 挂载
# --------------------------------------------------------------------------- #
def _bundle_with_scopes(*scopes: CacheScope) -> InputBundle:
    b = InputBundle()
    for i, s in enumerate(scopes):
        b.add(_sys(f"blk-{s.value}-{i}", s))
    return b


def test_cache_control_only_at_scope_boundary():
    """AC-16: 仅在每个非 NONE scope 的'最后一块'挂,同 scope 多块只挂末块。"""
    # GLOBAL 两块 + USER 两块 + NONE 一块
    bundle = _bundle_with_scopes(
        CacheScope.GLOBAL, CacheScope.GLOBAL,
        CacheScope.USER, CacheScope.USER,
        CacheScope.NONE,
    )
    frozen = bundle.freeze()
    pts = frozen.cache_control_points()

    # GLOBAL 最后一块 = index 1,USER 最后一块 = index 3,NONE 不挂
    assert len(pts) == 2
    assert {p.block_index for p in pts} == {1, 3}
    assert all(p.scope != CacheScope.NONE for p in pts)


def test_cache_control_respects_four_limit_with_history():
    """AC-16: ≤4 上限;history 占一个断点时 system 额度 -1,超限按优先级丢 ENV。"""
    # 四个非 NONE scope(GLOBAL/USER/ENV)+ history 占 1 → 可用 3,GLOBAL/USER/ENV 都能挂
    bundle = _bundle_with_scopes(
        CacheScope.GLOBAL, CacheScope.USER, CacheScope.ENV
    )
    frozen = bundle.freeze()

    pts_no_history = frozen.cache_control_points(history_breakpoint=False)
    assert len(pts_no_history) == 3  # GLOBAL/USER/ENV 各一

    # history 占 1 → 可用 3,仍能挂 3 个
    pts_with_history = frozen.cache_control_points(history_breakpoint=True)
    assert len(pts_with_history) == 3


def test_cache_control_drops_low_priority_when_over_budget():
    """AC-16: 超限时按 scope 优先级丢弃(先 ENV,再 USER,GLOBAL 最后丢)。"""
    # 把 max_breakpoints 压到 2,迫使丢弃
    bundle = _bundle_with_scopes(
        CacheScope.GLOBAL, CacheScope.USER, CacheScope.ENV
    )
    frozen = bundle.freeze()

    # max=2 → 保 GLOBAL+USER,丢 ENV
    pts = frozen.cache_control_points(max_breakpoints=2)
    scopes = {p.scope for p in pts}
    assert CacheScope.GLOBAL in scopes
    assert CacheScope.USER in scopes
    assert CacheScope.ENV not in scopes

    # max=1 → 只保 GLOBAL
    pts1 = frozen.cache_control_points(max_breakpoints=1)
    assert {p.scope for p in pts1} == {CacheScope.GLOBAL}


def test_cache_control_none_when_no_static_scope():
    """AC-16: 全 NONE scope + 无 system 时不挂任何断点。"""
    bundle = _bundle_with_scopes(CacheScope.NONE, CacheScope.NONE)
    frozen = bundle.freeze()
    assert frozen.cache_control_points() == ()

    empty = InputBundle().freeze()
    assert empty.cache_control_points() == ()


def test_cache_control_zero_budget_returns_empty():
    """AC-16: history 占满 4 个断点 → system 可用 0,返回空。"""
    bundle = _bundle_with_scopes(CacheScope.GLOBAL, CacheScope.USER)
    frozen = bundle.freeze()
    # max=4 且 history 占 1 → 可用 3(非 0);用 max=1+history 验 0
    pts = frozen.cache_control_points(history_breakpoint=True, max_breakpoints=1)
    assert pts == ()

# --------------------------------------------------------------------------- #
# S12 provider 形态转换(AC-16 / AC-17)
# --------------------------------------------------------------------------- #
from derisk.core.interface.resource.bundle import (
    to_anthropic_system,
    to_legacy_system_message,
)


def _bundle_scopes(*scopes):
    from derisk.core.interface.resource.bundle import InputBundle, CacheScope

    b = InputBundle()
    for i, s in enumerate(scopes):
        b.add(_sys(f"blk-{s.value}-{i}", s))
    return b


def test_to_anthropic_system_attaches_cache_only_at_boundary():
    """AC-16: cache_control 仅挂"非 NONE scope 最后一块";同 scope 多块只挂末块。"""
    frozen = _bundle_scopes(
        CacheScope.GLOBAL, CacheScope.GLOBAL,
        CacheScope.USER, CacheScope.USER,
        CacheScope.NONE,
    ).freeze()

    blocks = to_anthropic_system(frozen)
    # 5 块全保留(text 非空)
    assert len(blocks) == 5
    # cache_control 挂在 index 1(GLOBAL 末)和 3(USER 末),index 4(NONE)不挂
    assert "cache_control" in blocks[1]
    assert "cache_control" in blocks[3]
    assert "cache_control" not in blocks[0]
    assert "cache_control" not in blocks[2]
    assert "cache_control" not in blocks[4]


def test_to_anthropic_system_respects_four_limit_with_history():
    """AC-16: max_breakpoints=4,history 占 1 → system 可用 3,GLOBAL/USER/ENV 都挂。"""
    frozen = _bundle_scopes(
        CacheScope.GLOBAL, CacheScope.USER, CacheScope.ENV
    ).freeze()
    blocks = to_anthropic_system(frozen, history_breakpoint=True)
    cc_count = sum(1 for b in blocks if "cache_control" in b)
    assert cc_count == 3


def test_to_anthropic_system_drops_low_priority_when_over_budget():
    """AC-16: 超限时按 scope 优先级丢(先 ENV→USER→GLOBAL)。"""
    frozen = _bundle_scopes(
        CacheScope.GLOBAL, CacheScope.USER, CacheScope.ENV
    ).freeze()

    # max=2 → 保 GLOBAL+USER,丢 ENV
    blocks = to_anthropic_system(frozen, max_breakpoints=2)
    scopes_with_cc = {
        frozen.system[i].cache_scope
        for i, b in enumerate(blocks) if "cache_control" in b
    }
    assert CacheScope.GLOBAL in scopes_with_cc
    assert CacheScope.USER in scopes_with_cc
    assert CacheScope.ENV not in scopes_with_cc

    # max=1 → 只 GLOBAL
    blocks1 = to_anthropic_system(frozen, max_breakpoints=1)
    scopes1 = {
        frozen.system[i].cache_scope
        for i, b in enumerate(blocks1) if "cache_control" in b
    }
    assert scopes1 == {CacheScope.GLOBAL}


def test_to_anthropic_system_no_cc_when_all_none():
    """AC-16: 全 NONE 时不挂任何 cache_control。"""
    frozen = _bundle_scopes(CacheScope.NONE, CacheScope.NONE).freeze()
    blocks = to_anthropic_system(frozen)
    assert all("cache_control" not in b for b in blocks)


def test_to_anthropic_system_cache_type_ephemeral():
    """cache_control 类型默认 ephemeral。"""
    frozen = _bundle_scopes(CacheScope.GLOBAL).freeze()
    blocks = to_anthropic_system(frozen)
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_to_legacy_system_message_default_separator():
    """AC-17: 降级默认 separator 是现 PromptAssembler 的 \\n\\n---\\n\\n。"""
    from derisk.core.interface.resource.bundle import CacheScope

    bundle = _bundle_scopes(CacheScope.USER, CacheScope.GLOBAL)
    frozen = bundle.freeze()
    # 注意:GLOBAL 优先级在前,故顺序是 GLOBAL 块、USER 块
    expected = frozen.system[0].text + "\n\n---\n\n" + frozen.system[1].text
    assert to_legacy_system_message(frozen) == expected


def test_to_legacy_same_text_as_merge_to_str():
    """AC-17: to_legacy_system_message 与 merge_to_str 等价(同序同分隔符)。"""
    frozen = _bundle_scopes(
        CacheScope.GLOBAL, CacheScope.USER, CacheScope.NONE
    ).freeze()
    assert to_legacy_system_message(frozen, "\n\n") == frozen.merge_to_str("\n\n")
    assert to_legacy_system_message(frozen, "\n\n---\n\n") == frozen.merge_to_str(
        "\n\n---\n\n"
    )


def test_to_anthropic_and_legacy_share_order():
    """AC-15: Anthropic 数组与降级 str 同序(均来自 frozen.system)。"""
    frozen = _bundle_scopes(
        CacheScope.NONE, CacheScope.GLOBAL, CacheScope.USER
    ).freeze()

    anthropic_texts = [b["text"] for b in to_anthropic_system(frozen)]
    legacy_texts = to_legacy_system_message(frozen, "\n\n").split("\n\n")

    assert anthropic_texts == legacy_texts
    # 且顺序是 GLOBAL→USER→NONE(scope 优先级)
    assert anthropic_texts == [
        "blk-global-1", "blk-user-2", "blk-none-0"
    ]
