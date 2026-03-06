"""
Adapters - 架构适配器

为不同 Agent 架构提供统一的接入方式：
- V1ContextAdapter: Core V1 (ConversableAgent) 适配器
- V2ContextAdapter: Core V2 (AgentHarness) 适配器
"""

from derisk.agent.shared.adapters.v1_adapter import (
    V1ContextAdapter,
    create_v1_adapter,
)

from derisk.agent.shared.adapters.v2_adapter import (
    V2ContextAdapter,
    create_v2_adapter,
)

__all__ = [
    "V1ContextAdapter",
    "V2ContextAdapter",
    "create_v1_adapter",
    "create_v2_adapter",
]