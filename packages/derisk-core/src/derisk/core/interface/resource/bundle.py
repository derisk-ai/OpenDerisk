"""Agent 输入载体契约(RFC-005 §3.2 / §3.8)。

纯数据模型与确定性算法(排序 / 校验 / freeze / cache_control
挂载点 / 降级合并),不依赖 v1/v2 任一架构。provider 层消费 FrozenBundle。

实现 RFC-005 §3.8 钉死的规则:
- Lifetime(何时变)× CacheScope(谁能共享)正交;非法组合被拒绝。
- 排序:先 cache_scope 优先级分桶(GLOBAL<USER<ENV<NONE),桶内按 order。
- cache_control 仅挂"非 NONE scope 的最后一块"末尾;单请求≤4(含 history)。
- 降级 merge_to_str:存量委托路径用 separator 保字节等价,原生路径用 \\n\\n。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #
class Slot(str, Enum):
    """Contribution 落入的输入槽位。

    model kwargs(temperature / tool_choice / ...)永不在其中——不是输入层职责。
    """

    SYSTEM = "system"      # system prompt(分段+有序)
    USER_PART = "user_part"  # 用户轮内容(含多模态 part)
    TOOLS = "tools"        # 工具声明(资源工具 + agent builtin)
    VAR = "var"            # 可被 prompt 模板引用的命名变量


class Lifetime(str, Enum):
    """Contribution 的生命周期——"何时变化/失效"。"""

    CONFIG_STATIC = "config"  # 配置态即定 → 缓存到配置变更
    SESSION = "session"       # 会话级(加载的图片/会话级检索)
    TURN = "turn"            # 仅本轮(RAG inline chunks)


class CacheScope(str, Enum):
    """Contribution 的缓存共享范围——"谁能共享"。

    与 Lifetime 正交。Anthropic cache 按前缀匹配:块顺序即 cache 断点,
    乱序即全 miss。GLOBAL 在前以最大化跨用户共享前缀。
    """

    GLOBAL = "global"  # 跨用户共享(agent 模板/通用行为块)
    USER = "user"      # 跨会话但不跨用户(用户级资源声明/偏好)
    ENV = "env"        # 本会话环境,不跨会话(gitStatus/env 摘要)
    NONE = "none"      # 不缓存(每轮或随时变)


# cache_scope 排序优先级:值越小越靠前(GLOBAL 必须在最前)。
SCOPE_PRIORITY: Dict[CacheScope, int] = {
    CacheScope.GLOBAL: 0,
    CacheScope.USER: 1,
    CacheScope.ENV: 2,
    CacheScope.NONE: 3,
}


def is_valid_lifetime_cache_scope(
    lifetime: Lifetime, cache_scope: CacheScope
) -> bool:
    """RFC-005 §3.8.1 合法组合校验。

    非法组合(逻辑矛盾):
    - SESSION + GLOBAL:会话级内容不可能跨用户共享。
    - TURN + {GLOBAL, USER, ENV}:每轮变的内容不可能共享缓存。
    """
    if lifetime == Lifetime.SESSION and cache_scope == CacheScope.GLOBAL:
        return False
    if lifetime == Lifetime.TURN and cache_scope != CacheScope.NONE:
        return False
    return True


# --------------------------------------------------------------------------- #
# Contribution 与分块
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Contribution:
    """一次贡献:写哪个槽、内容、来源、生命周期、缓存范围。

    frozen 以保证可哈希、可放入 InputBundle 后不被外部篡改。
    """

    capability_id: str
    slot: Slot
    content: Any              # str | ToolSpec | ContentPart | dict
    lifetime: Lifetime = Lifetime.CONFIG_STATIC
    cache_scope: CacheScope = CacheScope.NONE
    order: int = 0            # 槽内/桶内确定性排序(默认 0)

    def __post_init__(self) -> None:
        if not is_valid_lifetime_cache_scope(self.lifetime, self.cache_scope):
            raise ValueError(
                f"Illegal Lifetime×CacheScope combination: "
                f"{self.lifetime.value}+{self.cache_scope.value} for "
                f"capability={self.capability_id}. See RFC-005 §3.8.1."
            )


@dataclass(frozen=True)
class SystemBlock:
    """system prompt 的物理分块(RFC-005 §3.8.2)。

    provider 据此组 Anthropic 数组式 system + cache_control;降级时按
    确定性顺序拼 str。
    """

    text: str
    cache_scope: CacheScope


@dataclass(frozen=True)
class CacheControlPoint:
    """一个 cache_control 挂载点(provider 层消费)。

    index 指向 system 块列表(或 None 表示无挂载,如 NONE scope)。
    """

    block_index: int          # 挂在哪个 system 块末尾
    scope: CacheScope          # 该断点的 scope(用于 budget 优先级决策)


# --------------------------------------------------------------------------- #
# InputBundle
# --------------------------------------------------------------------------- #
@dataclass
class InputBundle:
    """Agent 输入的可变载体。资源/Agent/消费工具不断往里写 Contribution。

    freeze() 产出不可变 FrozenBundle 供 provider 消费/缓存/跨进程传递。
    """

    system: List[Contribution] = field(default_factory=list)
    user_parts: List[Contribution] = field(default_factory=list)
    tools: List[Contribution] = field(default_factory=list)
    vars: Dict[str, Contribution] = field(default_factory=dict)

    def add(self, contribution: Contribution) -> "InputBundle":
        """追加一条 Contribution 到对应槽(VAR 槽按 content 中的 key 入 dict)。"""
        slot = contribution.slot
        if slot == Slot.VAR:
            # VAR 槽:content 期望为 (key, value) 二元组;否则用 capability_id 作 key
            key = (
                contribution.content[0]
                if isinstance(contribution.content, (list, tuple))
                and len(contribution.content) == 2
                else str(contribution.capability_id)
            )
            self.vars[key] = contribution
        elif slot == Slot.SYSTEM:
            self.system.append(contribution)
        elif slot == Slot.USER_PART:
            self.user_parts.append(contribution)
        elif slot == Slot.TOOLS:
            self.tools.append(contribution)
        else:  # pragma: no cover - exhaustive
            raise ValueError(f"Unknown slot: {slot}")
        return self

    def extend(self, contributions: List[Contribution]) -> "InputBundle":
        for c in contributions:
            self.add(c)
        return self

    # ----------------------------- 排序 ------------------------------------ #
    @staticmethod
    def _sort_system_key(c: Contribution) -> Tuple[int, int]:
        """system 槽排序键:先 cache_scope 优先级,再 order。

        RFC-005 §3.8.2:order 仅在"同一 cache_scope 内"生效,不能跨 scope 重排。
        """
        return (SCOPE_PRIORITY[c.cache_scope], c.order)

    def sorted_system(self) -> List[Contribution]:
        """返回按 RFC-005 §3.8.2 确定性排序后的 system Contribution 列表。"""
        return sorted(self.system, key=self._sort_system_key)

    # ----------------------------- freeze ---------------------------------- #
    def freeze(
        self,
        *,
        config_hash: str = "",
        protocol_version: int = 1,
    ) -> "FrozenBundle":
        """产出不可变快照。排序在此固化,保证 cache 路径与降级路径同序。"""
        ordered_system = self.sorted_system()
        system_blocks = tuple(
            SystemBlock(
                text=str(c.content) if not isinstance(c.content, str) else c.content,
                cache_scope=c.cache_scope,
            )
            for c in ordered_system
        )
        return FrozenBundle(
            system=system_blocks,
            user_parts=tuple(self.user_parts),
            tools=tuple(self.tools),
            vars=dict(self.vars),
            config_hash=config_hash,
            protocol_version=protocol_version,
        )


# --------------------------------------------------------------------------- #
# FrozenBundle(不可变快照,协议对外锚点)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FrozenBundle:
    """不可变输入快照(RFC-005 §3.6 AgentInputsSnapshot 的等价实现)。

    可缓存、可序列化、可跨进程传递;v1/v2 共同消费的纯数据契约。
    provider 据 system(SystemBlock 列表)组 cache_control 或降级合并 str。
    """

    system: Tuple[SystemBlock, ...]
    user_parts: Tuple[Contribution, ...]
    tools: Tuple[Contribution, ...]
    vars: Dict[str, Contribution]
    config_hash: str
    protocol_version: int = 1

    # ----------------------- system 文本视图 -------------------------------- #
    def merge_to_str(self, separator: str = "\n\n") -> str:
        """降级:把 system 块按确定性顺序拼成 str(RFC-005 §3.8.6)。

        - 存量委托路径:传入现 PromptAssembler 的 section_separator
          (``\\n\\n---\\n\\n``)以保字节等价。
        - 原生 declare 路径:用默认 ``\\n\\n``。

        无论 separator 如何,块顺序均来自 frozen 时的排序(slice 已固化),
        故 cache 路径与降级路径**同序**,仅分隔符不同。
        """
        return separator.join(b.text for b in self.system if b.text)

    # --------------------- cache_control 挂载点 ----------------------------- #
    def cache_control_points(
        self,
        *,
        history_breakpoint: bool = False,
        max_breakpoints: int = 4,
    ) -> Tuple[CacheControlPoint, ...]:
        """计算 cache_control 挂载点(RFC-005 §3.8.3)。

        规则:
        - 仅在"非 NONE scope 的最后一块"末尾挂。
        - 单请求总挂载数 ≤ max_breakpoints(默认 4,Anthropic 上限)。
        - history 若占一个断点(history_breakpoint=True),从预算中扣除。
        - 超限时按 scope 优先级丢弃:先丢 ENV,再丢 USER,GLOBAL 最后丢。

        Args:
            history_breakpoint: history 是否会自行占用一个 cache 断点
                (由 provider 在最新稳态消息挂)。占则 system 可用额度 -1。
            max_breakpoints: Anthropic 单请求 cache_creation 上限(默认 4)。

        Returns:
            挂载点列表(按 block_index 升序),可能为空。
        """
        available = max_breakpoints - (1 if history_breakpoint else 0)
        if available <= 0 or not self.system:
            return ()

        # 找每个非 NONE scope 的"最后一块"索引,按 scope 优先级排序(高优先在前)
        last_by_scope: Dict[CacheScope, int] = {}
        for idx, block in enumerate(self.system):
            if block.cache_scope != CacheScope.NONE:
                last_by_scope[block.cache_scope] = idx  # 保留该 scope 最大 idx

        # 按 scope 优先级升序(GLOBAL 优先保留),仅取 available 个
        scopes_by_priority = sorted(
            last_by_scope.keys(), key=lambda s: SCOPE_PRIORITY[s]
        )
        kept_scopes = set(scopes_by_priority[:available])

        points = [
            CacheControlPoint(block_index=last_by_scope[s], scope=s)
            for s in scopes_by_priority
            if s in kept_scopes
        ]
        points.sort(key=lambda p: p.block_index)
        return tuple(points)

    # --------------------------- 便利访问 ----------------------------------- #
    def system_text(self, separator: str = "\n\n") -> str:
        """merge_to_str 的语义别名,便于直接取 system 文本。"""
        return self.merge_to_str(separator)


# --------------------------------------------------------------------------- #
# provider 形态转换(RFC-005 §3.8.3 / §3.8.6,S12)
# --------------------------------------------------------------------------- #
# Anthropic 数组式 system 块的形态:{"type": "text", "text": ..., "cache_control"?}
AnthropicSystemBlock = Dict[str, Any]


def to_anthropic_system(
    frozen: "FrozenBundle",
    *,
    history_breakpoint: bool = False,
    max_breakpoints: int = 4,
    cache_type: str = "ephemeral",
) -> List[AnthropicSystemBlock]:
    """把 FrozenBundle.system 转为 Anthropic 数组式 system(RFC-005 §3.8.3)。

    规则(已在 ``cache_control_points`` 钉死):
    - 仅在"非 NONE scope 的最后一块"末尾挂 ``cache_control``。
    - 总挂载数 ≤ max_breakpoints(含 history 占用)。
    - 超限按 scope 优先级丢弃(先 ENV→USER→GLOBAL)。

    本函数是纯转换,不直接调用 API;provider 层把返回值放进 ``params["system"]``。
    非 Anthropic provider 用 ``FrozenBundle.merge_to_str`` 降级。

    Args:
        frozen: 已 freeze 的输入快照。
        history_breakpoint: history 是否会自行占一个 cache 断点(provider 在
            最新稳态消息挂)。占则 system 可用额度 -1。
        max_breakpoints: Anthropic 单请求 cache_creation 上限(默认 4)。
        cache_type: cache_control 类型,默认 "ephemeral"。

    Returns:
        Anthropic system 块数组,顺序 = frozen.system 的确定序。
    """
    points = frozen.cache_control_points(
        history_breakpoint=history_breakpoint,
        max_breakpoints=max_breakpoints,
    )
    point_indices = {p.block_index for p in points}

    blocks: List[AnthropicSystemBlock] = []
    for idx, blk in enumerate(frozen.system):
        if not blk.text:
            continue
        item: AnthropicSystemBlock = {"type": "text", "text": blk.text}
        if idx in point_indices:
            item["cache_control"] = {"type": cache_type}
        blocks.append(item)
    return blocks


def to_legacy_system_message(
    frozen: "FrozenBundle", separator: str = "\n\n---\n\n"
) -> str:
    """降级:把 system 合并为 str(供无数组式 system 的 provider)。

    与现 ``claude_provider.py:48-49`` 拼接语义对齐,默认 separator 取现
    PromptAssembler 的 ``section_separator`` 以保字节等价(AC-2 / AC-17)。
    """
    return frozen.merge_to_str(separator)