"""
Core_v2 Integration Layer

提供 Core_v2 与原架构的集成适配层
"""

from .adapter import (
    V2Adapter,
    V2MessageConverter,
    V2ResourceBridge,
    V2ContextBridge,
    V2StreamChunk,
)
from .runtime import V2AgentRuntime, RuntimeConfig, SessionContext, RuntimeState
from .builder import V2ApplicationBuilder, AgentBuildResult
from .dispatcher import V2AgentDispatcher, DispatchTask, DispatchPriority
from .agent_impl import (
    V2PDCAAgent,
    V2SimpleAgent,
    create_v2_agent,
    create_default_agent,
)
from ..production_agent import ProductionAgent, AgentBuilder
from ..production_interaction import (
    ProductionAgentInteractionMixin,
    ProductionAgentWithInteraction,
)

__all__ = [
    "V2Adapter",
    "V2MessageConverter",
    "V2ResourceBridge",
    "V2ContextBridge",
    "V2StreamChunk",
    "V2AgentRuntime",
    "RuntimeConfig",
    "SessionContext",
    "RuntimeState",
    "V2ApplicationBuilder",
    "AgentBuildResult",
    "V2AgentDispatcher",
    "DispatchTask",
    "DispatchPriority",
    "V2PDCAAgent",
    "V2SimpleAgent",
    "create_v2_agent",
    "create_default_agent",
    "ProductionAgent",
    "AgentBuilder",
    "ProductionAgentInteractionMixin",
    "ProductionAgentWithInteraction",
]
