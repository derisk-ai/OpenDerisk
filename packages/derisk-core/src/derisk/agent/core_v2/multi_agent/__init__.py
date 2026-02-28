"""
Multi-Agent Module

This module provides multi-agent collaboration capabilities including:
- Agent orchestration and team management
- Task planning and decomposition
- Parallel execution support
- Shared context and resource management
- Product-level agent binding

@see ARCHITECTURE.md#12-multiagent-架构设计
"""

from .shared_context import (
    SharedContext,
    SharedMemory,
    Artifact,
    ResourceScope,
    ResourceBinding,
)
from .orchestrator import (
    MultiAgentOrchestrator,
    ExecutionStrategy,
    TaskPlan,
    SubTask,
    TaskStatus,
    TaskResult,
    ExecutionResult,
)
from .team import (
    AgentTeam,
    AgentRole,
    AgentStatus,
    WorkerAgent,
    TeamConfig,
)
from .planner import (
    TaskPlanner,
    DecompositionStrategy,
    TaskDependency,
    TaskPriority,
)
from .router import (
    AgentRouter,
    RoutingStrategy,
    AgentCapability,
    AgentSelectionResult,
)
from .messenger import (
    TeamMessenger,
    MessageType,
    AgentMessage,
    BroadcastMessage,
)
from .monitor import (
    TeamMonitor,
    TeamMetrics,
    AgentMetrics,
    ExecutionProgress,
)

__all__ = [
    "SharedContext",
    "SharedMemory",
    "Artifact",
    "ResourceScope",
    "ResourceBinding",
    "MultiAgentOrchestrator",
    "ExecutionStrategy",
    "TaskPlan",
    "SubTask",
    "TaskStatus",
    "TaskResult",
    "ExecutionResult",
    "AgentTeam",
    "AgentRole",
    "AgentStatus",
    "WorkerAgent",
    "TeamConfig",
    "TaskPlanner",
    "DecompositionStrategy",
    "TaskDependency",
    "TaskPriority",
    "AgentRouter",
    "RoutingStrategy",
    "AgentCapability",
    "AgentSelectionResult",
    "TeamMessenger",
    "MessageType",
    "AgentMessage",
    "BroadcastMessage",
    "TeamMonitor",
    "TeamMetrics",
    "AgentMetrics",
    "ExecutionProgress",
]