"""PR 8: 模型定价表 — 用于会话级成本估算。

定价单位：USD per 1M tokens (prompt / completion 分别计价)。
来源：各模型厂商公开定价（2026-Q2），可在配置文件覆盖。

只覆盖常见模型，未知模型 cost 视为 0（避免误报）。
"""
from __future__ import annotations

from typing import Dict, Tuple


# 单位：USD / 1M tokens
DEFAULT_PRICING: Dict[str, Tuple[float, float]] = {
    # prompt, completion
    "gpt-4": (30.0, 60.0),
    "gpt-4-turbo": (10.0, 30.0),
    "gpt-4-turbo-preview": (10.0, 30.0),
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-3.5-turbo-16k": (3.0, 4.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-sonnet": (3.0, 15.0),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-haiku-4": (1.0, 5.0),
    "glm-4": (0.50, 1.50),
    "glm-4-air": (0.10, 0.50),
    "glm-4-flash": (0.10, 0.50),
    "glm-4-plus": (5.0, 5.0),
    "qwen-max": (40.0, 120.0),
    "qwen-plus": (4.0, 12.0),
    "qwen-turbo": (2.0, 6.0),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-coder": (0.14, 0.28),
}


def get_pricing(model_name: str) -> Tuple[float, float]:
    """获取模型定价 (prompt_usd_per_1m, completion_usd_per_1m)。

    未知模型返回 (0.0, 0.0)。
    """
    if not model_name:
        return (0.0, 0.0)
    # 精确匹配
    if model_name in DEFAULT_PRICING:
        return DEFAULT_PRICING[model_name]
    # 前缀匹配（处理 -latest / -preview / -0125 等变体）
    # 按前缀长度降序，避免 "gpt-4" 误匹配 "gpt-4o-..."
    for prefix in sorted(DEFAULT_PRICING.keys(), key=len, reverse=True):
        if model_name.startswith(prefix):
            return DEFAULT_PRICING[prefix]
    return (0.0, 0.0)
