"""V2 Runtime——Agent 框架内核.

六件套中的五件在 P1 落地：StepState/EventStream/StateStore/Recovery/PermissionGate。
SubAgent Runtime 在 P2 加。

参见设计文档：docs/superpowers/specs/2026-06-30-agent-framework-evolution-design.md
"""
from derisk.agent.core.v2.step_state import (
    StepState,
    VALID_TRANSITIONS,
    validate_transition,
    IllegalTransitionError,
)
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore, DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.recovery import RecoveryCoordinatorV2
from derisk.agent.core.v2.runtime import run_step, resume_step
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache, hash_tool_input
from derisk.agent.core.v2.permission_gate import (
    PermissionGate,
    PermissionResult,
    PermissionDecision,
    PermissionCheckResult,
    NoInteractionAdapterError,
)
from derisk.agent.core.v2.subagent_handle import (
    SubAgentHandle,
    SubAgentMode,
    SubAgentStatus,
)
from derisk.agent.core.v2.subagent_runtime import (
    SubAgentRuntime,
    SubAgentSpawnSpec,
)
from derisk.agent.core.v2.subagent_interaction_gateway import SubAgentInteractionGateway
from derisk.agent.core.v2.spawn_subagent_tool import SpawnSubagentTool
from derisk.agent.core.v2.ask_user_adapter import AskUserAdapter

__all__ = [
    "StepState",
    "VALID_TRANSITIONS",
    "validate_transition",
    "IllegalTransitionError",
    "StepEvent",
    "StateStore",
    "DbStateStore",
    "EventStream",
    "RecoveryCoordinatorV2",
    "run_step",
    "resume_step",
    "PermissionMode",
    "PermissionGate",
    "PermissionResult",
    "PermissionDecision",
    "SessionPermissionCache",
    "hash_tool_input",
    "NoInteractionAdapterError",
    "SubAgentRuntime",
    "SubAgentSpawnSpec",
    "SubAgentHandle",
    "SubAgentMode",
    "SubAgentStatus",
    "SubAgentInteractionGateway",
    "SpawnSubagentTool",
    "AskUserAdapter",
    "PermissionCheckResult",
]
