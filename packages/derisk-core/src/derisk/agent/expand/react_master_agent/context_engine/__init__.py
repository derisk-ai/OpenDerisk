"""BAIZE 统一上下文管理引擎 (ContextEngine)。

单一权威时间线 + 单一 join + 单一排序 + 发送前硬不变量门禁 + 低频压缩。
取代历史上分散的 7 套上下文/压缩实现。

数据流::

    gpts_messages ─┐
                   ├─► TimelineAssembler ─► Segmenter ─► BudgetLayerer ─► 渲染 ─► InvariantGuard ─► messages
    gpts_work_log ─┘   唯一 join+排序      conv_id分段   无状态分层+剪枝                发送前硬校验
                                                            ├─ hot/warm: 原文/截断
                                                            └─ cold: ColdSummarizer
                                                                    全量重整→单条 handoff
                                                                    ↕ gpts_cold_segments (持久化复用/恢复)

模块::

    text_utils  共享纯文本工具 (extract_text_content / build_user_content / token 估算)
    timeline    TimelineUnit / Segment / Timeline 数据模型
    assembler   TimelineAssembler (唯一真相源, message_id + tool_call_id join)
    segmenter   Segmenter (按 conv_id 结构化分段)
    layering    BudgetLayerer + LayerBudgetConfig (无状态分层 + 剪枝 + 批量量化)
    summarizer  ColdSummarizer (全量重整 + 单条 handoff + 持久化复用)
    invariants  InvariantGuard (I1-I6 硬不变量)
    engine      ContextEngine (门面 build_messages)
"""

from .engine import (
    ColdPersistenceAdapter,
    ContextEngine,
    EngineConfig,
    EventEmitter,
    BuildOutput,
    InMemoryColdPersistence,
    NoopEventEmitter,
)
from .invariants import GuardReport, InvariantGuard
from .layering import BudgetLayerer, Layer, LayerBudgetConfig, LayerPlan
from .segmenter import Segmenter
from .summarizer import ColdSummarizer, HandoffMessage, SummarizeFn
from .text_utils import (
    DEFAULT_CHARS_PER_TOKEN,
    build_user_content,
    estimate_message_tokens,
    estimate_tokens_text,
    extract_text_content,
)
from .timeline import (
    ResultStatus,
    Segment,
    Timeline,
    TimelineUnit,
    ToolCallBinding,
    UnitKind,
)
from .assembler import TimelineAssembler

__all__ = [
    "DEFAULT_CHARS_PER_TOKEN",
    "extract_text_content",
    "build_user_content",
    "estimate_tokens_text",
    "estimate_message_tokens",
    "UnitKind",
    "ResultStatus",
    "ToolCallBinding",
    "TimelineUnit",
    "Segment",
    "Timeline",
    "TimelineAssembler",
    "Segmenter",
    "Layer",
    "LayerBudgetConfig",
    "LayerPlan",
    "BudgetLayerer",
    "SummarizeFn",
    "HandoffMessage",
    "ColdSummarizer",
    "GuardReport",
    "InvariantGuard",
    "EngineConfig",
    "BuildOutput",
    "ContextEngine",
    "ColdPersistenceAdapter",
    "EventEmitter",
    "NoopEventEmitter",
    "InMemoryColdPersistence",
]
