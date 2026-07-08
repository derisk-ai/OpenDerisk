"""PR 8: 会话级 usage 聚合。

V1 已有 ModelInferenceMetrics（每次 LLM 调用记录 prompt/completion/total_tokens），
持久化在 gpts_messages.metrics JSON。本模块补会话级聚合：
- aggregate_usage(conv_id): 扫 gpts_messages.metrics，按 model/role 聚合
- emit_usage_metric: 单次 LLM 调用 usage 记录（可选，写入内存聚合 buffer）
- estimate_cost: 用 model_pricing 表估算成本

设计为只读聚合（不写 DB），避免侵入 V1 现有 metrics 持久化路径。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from derisk.agent.core.model_pricing import get_pricing

logger = logging.getLogger(__name__)


@dataclass
class ConversationUsage:
    """会话级 usage 聚合。"""
    conv_id: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    total_cost_usd: float = 0.0
    by_model: Dict[str, int] = field(default_factory=dict)  # model_name -> total_tokens
    by_role: Dict[str, int] = field(default_factory=dict)  # main/subagent -> total_tokens

    def add_call(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        role: str = "main",
    ) -> None:
        """累加一次 LLM 调用。"""
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        call_total = prompt_tokens + completion_tokens

        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += call_total
        self.total_llm_calls += 1

        if model_name:
            self.by_model[model_name] = self.by_model.get(model_name, 0) + call_total
        self.by_role[role] = self.by_role.get(role, 0) + call_total
        self.total_cost_usd += estimate_cost(
            model_name, prompt_tokens, completion_tokens
        )


# PR 8: in-memory usage buffer，供 emit_usage_metric 实时累加
# conv_id -> ConversationUsage
_usage_buffers: Dict[str, ConversationUsage] = {}


def emit_usage_metric(
    conv_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    role: str = "main",
) -> None:
    """记录一次 LLM 调用的 usage 到 in-memory buffer。

    供 llm_client / base_agent 在 LLM 调用结束后调用。
    fire-and-forget：异常只 log warning，不影响 LLM 调用路径。
    """
    if not conv_id:
        return
    try:
        usage = _usage_buffers.get(conv_id)
        if usage is None:
            usage = ConversationUsage(conv_id=conv_id)
            _usage_buffers[conv_id] = usage
        usage.add_call(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            role=role,
        )
    except Exception as e:
        logger.warning(
            f"[usage] emit failed conv={conv_id} model={model_name}: {e}"
        )


def get_in_memory_usage(conv_id: str) -> Optional[ConversationUsage]:
    """读 in-memory buffer。无则 None。"""
    return _usage_buffers.get(conv_id)


def clear_in_memory_usage(conv_id: str) -> None:
    """清空 conv_id 的 in-memory buffer（会话结束时调用）。"""
    _usage_buffers.pop(conv_id, None)


def estimate_cost(
    model_name: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """用 model_pricing 估算成本（USD）。

    Args:
        model_name: 模型名（用于查定价表）
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数

    Returns:
        USD 成本，未知模型返回 0.0
    """
    if not model_name:
        return 0.0
    prompt_per_1m, completion_per_1m = get_pricing(model_name)
    return (
        (prompt_tokens or 0) * prompt_per_1m / 1_000_000
        + (completion_tokens or 0) * completion_per_1m / 1_000_000
    )


def _extract_llm_tokens(metrics_dict: Dict[str, Any]) -> tuple[int, int, int]:
    """从 MessageMetrics dict 提取 (prompt, completion, total) tokens。

    MessageMetrics 结构：{llm_metrics: {prompt_tokens, completion_tokens, total_tokens}, ...}
    """
    llm = metrics_dict.get("llm_metrics") or {}
    prompt = llm.get("prompt_tokens") or 0
    completion = llm.get("completion_tokens") or 0
    total = llm.get("total_tokens") or (prompt + completion)
    return (prompt, completion, total)


def aggregate_usage_from_messages(
    conv_id: str,
    messages: List[Any],
    role_resolver=None,
) -> ConversationUsage:
    """从 GptsMessage 列表聚合 usage。

    Args:
        conv_id: 会话 ID
        messages: GptsMessage 列表（或具有 model_name + metrics 字段的 duck-typed 对象）
        role_resolver: optional callable(msg) -> "main" | "subagent"，None 时全按 "main"

    Returns:
        ConversationUsage
    """
    usage = ConversationUsage(conv_id=conv_id)
    for msg in messages:
        model_name = getattr(msg, "model_name", None)
        metrics = getattr(msg, "metrics", None)
        if metrics is None:
            continue

        # metrics 可能是 dict / str / MessageMetrics 对象
        metrics_dict: Dict[str, Any]
        if isinstance(metrics, str):
            try:
                metrics_dict = json.loads(metrics)
            except Exception:
                continue
        elif isinstance(metrics, dict):
            metrics_dict = metrics
        elif hasattr(metrics, "to_dict"):
            metrics_dict = metrics.to_dict()
        else:
            continue

        prompt, completion, total = _extract_llm_tokens(metrics_dict)
        if total == 0:
            continue

        role = "main"
        if role_resolver is not None:
            try:
                role = role_resolver(msg) or "main"
            except Exception:
                role = "main"

        usage.add_call(
            model_name=model_name or "unknown",
            prompt_tokens=prompt,
            completion_tokens=completion,
            role=role,
        )
    return usage


async def aggregate_usage(conv_id: str) -> ConversationUsage:
    """异步聚合：从 DB 读 gpts_messages 聚合 usage。

    Lazy import 避免循环依赖（derisk-core → derisk-serve）。
    """
    from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao

    dao = GptsMessagesDao()
    messages = await dao.get_by_conv_id(conv_id)
    return aggregate_usage_from_messages(conv_id, messages)


def format_usage_log(usage: ConversationUsage) -> str:
    """格式化 usage 为一行日志。"""
    return (
        f"[usage] conv={usage.conv_id} "
        f"calls={usage.total_llm_calls} "
        f"prompt={usage.total_prompt_tokens} "
        f"completion={usage.total_completion_tokens} "
        f"total={usage.total_tokens} "
        f"cost=${usage.total_cost_usd:.4f} "
        f"by_model={usage.by_model} "
        f"by_role={usage.by_role}"
    )
