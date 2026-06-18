"""
Adapters - 架构适配器

为 Agent 架构提供统一的接入方式：
- V1ContextAdapter: Core V1 (ConversableAgent) 适配器
"""

from derisk.agent.shared.adapters.v1_adapter import (
    V1ContextAdapter,
    create_v1_adapter,
)

__all__ = [
    "V1ContextAdapter",
    "create_v1_adapter",
]
