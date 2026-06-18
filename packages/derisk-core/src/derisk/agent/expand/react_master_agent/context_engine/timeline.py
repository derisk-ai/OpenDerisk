"""时间线数据模型 —— TimelineUnit / Segment / Timeline。

核心设计：**call + result 原子单元**。tool_call 与其结果绑成一个 TimelineUnit
（CALL），从源头消灭 orphan —— assistant tool_call 与 tool 结果永远一起被渲染、
一起跨层搬移，不会被分层边界切开。没有独立的 TOOL kind。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class UnitKind(str, Enum):
    """时间线单元类型。"""

    USER = "user"  # 用户输入（human 轮）
    AI_TEXT = "ai_text"  # assistant 纯文本（blank action / terminate）
    CALL = "call"  # assistant 发起的 tool_call(s) + 其结果（原子）


class ResultStatus(str, Enum):
    """工具结果状态。"""

    OK = "ok"  # 正常结果
    ERROR = "error"  # WorkEntry.success 为 False
    MISSING = "missing"  # 找不到对应 WorkEntry —— 绝不渲染成 tool 消息


@dataclass
class ToolCallBinding:
    """单个 tool_call 与其结果的绑定（原子单元的成员）。"""

    tool_call_id: str
    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    result_status: ResultStatus = ResultStatus.MISSING
    result_text: Optional[str] = None  # OK/ERROR 的原始结果；MISSING 时为 None
    full_result_archive: Optional[str] = None
    summary: Optional[str] = None  # WorkEntry.summary，cold 重整时用
    tokens: int = 0
    # 剪枝标记（layering Pass-2 打标，渲染时跳过；不违反守恒律——最新副本仍在）
    pruned: bool = False
    superseded_content: bool = False  # 写入被后续读取覆盖：截断为占位
    work_entry: Optional[Any] = field(default=None, repr=False)

    @property
    def is_renderable(self) -> bool:
        """是否应渲染为 tool 消息。MISSING / pruned 不渲染。"""
        return self.result_status != ResultStatus.MISSING and not self.pruned


@dataclass
class TimelineUnit:
    """时间线最小单元。"""

    kind: UnitKind
    conv_id: str
    message_id: Optional[str] = None  # GptsMessage.message_id（合成单元为 None）
    rounds: int = 0  # 仅作排序参考之一
    created_at: float = 0.0  # epoch 秒，排序主键之一
    seq: int = 0  # assemble 时赋的全局稳定序号（最终 tiebreak）

    # 角色专属载荷
    user_content: Optional[Union[str, List[Any]]] = None  # USER
    ai_text: Optional[str] = None  # AI_TEXT 或 CALL 的 assistant 文本
    calls: List[ToolCallBinding] = field(default_factory=list)  # CALL only

    # 记账
    tokens: int = 0
    goal_id: Optional[str] = None
    current_goal: Optional[str] = None

    def is_renderable(self) -> bool:
        """单元是否有可渲染内容。"""
        if self.kind == UnitKind.USER:
            return bool(self.user_content)
        if self.kind == UnitKind.AI_TEXT:
            return bool(self.ai_text and str(self.ai_text).strip())
        if self.kind == UnitKind.CALL:
            # 至少有一个可渲染 binding，或有 assistant 文本
            return any(b.is_renderable for b in self.calls) or bool(
                self.ai_text and str(self.ai_text).strip()
            )
        return False

    def renderable_calls(self) -> List[ToolCallBinding]:
        """返回应渲染的 binding（过滤 MISSING / pruned）。"""
        return [b for b in self.calls if b.is_renderable]

    @property
    def sort_key(self):
        """单一排序键：(rounds, created_at, seq)。不含不可靠的字段。"""
        return (self.rounds, self.created_at, self.seq)


@dataclass
class Segment:
    """一个 conv_id（一个用户轮次）对应一个段。"""

    conv_id: str
    units: List[TimelineUnit] = field(default_factory=list)
    first_rounds: int = 0
    first_created_at: float = 0.0

    @property
    def sort_key(self):
        return (self.first_rounds, self.first_created_at)


@dataclass
class Timeline:
    """全局有序、原子化的时间线（唯一真相源）。"""

    units: List[TimelineUnit] = field(default_factory=list)
    current_conv_id: str = ""
    session_id: str = ""
