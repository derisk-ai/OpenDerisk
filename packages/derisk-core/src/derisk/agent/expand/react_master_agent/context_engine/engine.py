"""ContextEngine —— 门面/编排。

build_messages 串起：assemble → segment → layer → summarize_cold → render →
guard.repair → 记账。

引擎不持 agent 引用、不碰 GptsMemory。三个注入协作者保证可纯测：
  - ColdPersistenceAdapter: cold handoff 持久化（load_handoff / save_handoff）
  - SummarizeFn: 一次性 LLM 摘要 callable
  - EventEmitter: 压缩事件上报（emit）
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from .assembler import TimelineAssembler
from .invariants import GuardReport, InvariantGuard
from .layering import BudgetLayerer, LayerBudgetConfig, LayerPlan
from .segmenter import Segmenter
from .summarizer import ColdSummarizer, HandoffMessage, SummarizeFn
from .text_utils import (
    DEFAULT_CHARS_PER_TOKEN,
    estimate_messages_tokens,
    extract_text_content,
)
from .timeline import ResultStatus, TimelineUnit, ToolCallBinding, UnitKind

logger = logging.getLogger(__name__)

# 角色常量（与 ModelMessageRoleType 对齐，但不强依赖以便纯测）
ROLE_AI = "ai"
ROLE_HUMAN = "human"
ROLE_TOOL = "tool"

_SUPERSEDED_PLACEHOLDER = "[写入内容已被后续读取/写入覆盖，此处省略具体内容]"


# ---------------------------------------------------------------------- #
# 注入接口
# ---------------------------------------------------------------------- #
class ColdPersistenceAdapter(Protocol):
    async def load_handoff(
        self, session_id: str, content_hash: str
    ) -> Optional[HandoffMessage]:
        ...

    async def save_handoff(
        self, session_id: str, conv_id: str, handoff: HandoffMessage
    ) -> None:
        ...


class EventEmitter(Protocol):
    def emit(
        self,
        event_type: str,
        title: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        ...


class NoopEventEmitter:
    def emit(self, event_type, title, description="", metadata=None) -> None:
        return None


class InMemoryColdPersistence:
    """内存版 cold 持久化（降级/测试用）。无跨进程恢复能力。"""

    def __init__(self):
        self._store: Dict[tuple, HandoffMessage] = {}

    async def load_handoff(self, session_id, content_hash):
        return self._store.get((session_id, content_hash))

    async def save_handoff(self, session_id, conv_id, handoff):
        self._store[(session_id, handoff.content_hash)] = handoff


# ---------------------------------------------------------------------- #
# 配置 / 输出
# ---------------------------------------------------------------------- #
@dataclass
class EngineConfig:
    layer: LayerBudgetConfig = field(default_factory=LayerBudgetConfig)
    history_budget_ratio: float = 0.85
    enable_invariant_repair: bool = True
    hot_tool_result_max_length: int = 8000  # hot 层单条结果硬上限（防超大单条）
    chars_per_token: int = DEFAULT_CHARS_PER_TOKEN


@dataclass
class BuildOutput:
    messages: List[Dict[str, Any]] = field(default_factory=list)  # 不含 system
    layer_tokens: Dict[str, int] = field(default_factory=dict)
    total_tokens: int = 0
    cleanup_hints: Dict[str, List[str]] = field(default_factory=dict)
    guard_report: Optional[GuardReport] = None
    handoff: Optional[HandoffMessage] = None

    def get_cache_cleanup_hints(self) -> Dict[str, List[str]]:
        return self.cleanup_hints


# ---------------------------------------------------------------------- #
# 引擎
# ---------------------------------------------------------------------- #
class ContextEngine:
    def __init__(
        self,
        config: Optional[EngineConfig] = None,
        cold_persistence: Optional[ColdPersistenceAdapter] = None,
        summarize_fn: Optional[SummarizeFn] = None,
        events: Optional[EventEmitter] = None,
    ):
        self.config = config or EngineConfig()
        self.events = events or NoopEventEmitter()
        self.cold_persistence = cold_persistence or InMemoryColdPersistence()
        self.assembler = TimelineAssembler(self.config.chars_per_token)
        self.segmenter = Segmenter()
        self.layerer = BudgetLayerer(self.config.layer)
        self.summarizer = ColdSummarizer(
            summarize_fn=summarize_fn,
            persistence=self.cold_persistence,
            config=self.config.layer,
            events=self.events,
        )
        self.guard = InvariantGuard()

    async def build_messages(
        self,
        messages: List[Any],
        work_logs_by_conv: Dict[str, List[Any]],
        current_conv_id: str,
        session_id: str,
        context_window: int,
        subagent_goal_id: Optional[str] = None,
    ) -> BuildOutput:
        history_window = int(context_window * self.config.history_budget_ratio)

        # 1) 装配 → 分段 → 分层
        timeline = self.assembler.assemble(
            messages=messages,
            work_logs_by_conv=work_logs_by_conv,
            current_conv_id=current_conv_id,
            session_id=session_id,
            subagent_goal_id=subagent_goal_id,
        )
        segments = self.segmenter.segment(timeline)
        plan: LayerPlan = self.layerer.layer(
            segments, history_window, current_conv_id=current_conv_id
        )

        # 2) cold 重整（低频）
        handoff = await self.summarizer.summarize_cold(
            plan.cold, current_conv_id, session_id
        )

        # 3) 渲染：handoff(单条 human) → warm(截断) → hot(原文)
        out_messages: List[Dict[str, Any]] = []
        if handoff is not None:
            out_messages.append(handoff.to_message())
        out_messages.extend(self._render_units(plan.warm, layer="warm"))
        out_messages.extend(self._render_units(plan.hot, layer="hot"))

        # 4) 发送前不变量门禁
        if self.config.enable_invariant_repair:
            out_messages, report = self.guard.repair(out_messages)
        else:
            report = self.guard.check(out_messages)

        # 5) 记账 + cleanup hints
        total_tokens = estimate_messages_tokens(
            out_messages, self.config.chars_per_token
        )
        cleanup_hints = self._build_cleanup_hints(plan)

        return BuildOutput(
            messages=out_messages,
            layer_tokens=plan.layer_tokens,
            total_tokens=total_tokens,
            cleanup_hints=cleanup_hints,
            guard_report=report,
            handoff=handoff,
        )

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def _render_units(
        self, units: List[TimelineUnit], layer: str
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        for u in units:
            if u.kind == UnitKind.USER:
                if u.user_content:
                    messages.append(
                        {"role": ROLE_HUMAN, "content": u.user_content}
                    )
            elif u.kind == UnitKind.AI_TEXT:
                if u.ai_text and u.ai_text.strip():
                    messages.append({"role": ROLE_AI, "content": u.ai_text})
            elif u.kind == UnitKind.CALL:
                messages.extend(self._render_call_unit(u, layer))
        return messages

    def _render_call_unit(
        self, u: TimelineUnit, layer: str
    ) -> List[Dict[str, Any]]:
        renderable = u.renderable_calls()
        # 全部 MISSING/pruned 且无文本 → 不渲染（消灭 orphan）
        if not renderable:
            if u.ai_text and u.ai_text.strip():
                return [{"role": ROLE_AI, "content": u.ai_text}]
            return []

        out: List[Dict[str, Any]] = []
        tool_calls = []
        for b in renderable:
            tool_calls.append(
                {
                    "id": b.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": b.tool_name,
                        "arguments": self._args_to_str(b.args),
                    },
                }
            )
        out.append(
            {
                "role": ROLE_AI,
                "content": u.ai_text or "",
                "tool_calls": tool_calls,
            }
        )
        for b in renderable:
            out.append(
                {
                    "role": ROLE_TOOL,
                    "tool_call_id": b.tool_call_id,
                    "content": self._render_result(b, layer),
                }
            )
        return out

    def _render_result(self, b: ToolCallBinding, layer: str) -> str:
        if b.superseded_content:
            return _SUPERSEDED_PLACEHOLDER
        text = b.result_text or ""
        if b.result_status == ResultStatus.ERROR and not text:
            text = "[工具执行失败]"
        if layer == "warm":
            limit = self.config.layer.warm_tool_result_max_length
            if b.tool_name not in self.config.layer.warm_preserve_tools and len(
                text
            ) > limit:
                suffix = (
                    f"\n...(已截断，完整结果见归档 {b.full_result_archive})"
                    if b.full_result_archive
                    else "\n...(已截断)"
                )
                text = text[:limit] + suffix
        else:  # hot
            limit = self.config.hot_tool_result_max_length
            if len(text) > limit:
                suffix = (
                    f"\n...(过长已截断，完整结果见归档 {b.full_result_archive})"
                    if b.full_result_archive
                    else "\n...(过长已截断)"
                )
                text = text[:limit] + suffix
        return text or "[空结果]"

    # ------------------------------------------------------------------ #
    def _build_cleanup_hints(self, plan: LayerPlan) -> Dict[str, List[str]]:
        """生成与旧 BuildResult.get_cache_cleanup_hints 同形的清理建议。

        cold 与剪枝单元的 message_id 可从内存工作集驱逐（已被 handoff/剪枝替代）。
        """
        evict_msg_ids = list(
            dict.fromkeys(plan.cold_unit_message_ids + plan.pruned_unit_message_ids)
        )
        # 过滤掉合成 seq:* （非真实 message_id）
        real_ids = [i for i in evict_msg_ids if not str(i).startswith("seq:")]
        return {
            "can_evict_message_ids": real_ids,
            "can_evict_entry_message_ids": real_ids,
        }

    @staticmethod
    def _args_to_str(args: Any) -> str:
        if isinstance(args, str):
            return args
        try:
            return json.dumps(args, ensure_ascii=False, default=str)
        except Exception:
            return str(args)
