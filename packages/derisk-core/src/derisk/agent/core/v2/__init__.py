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
from derisk.agent.core.v2.stream_event import StreamEvent, EVENT_TYPES
from derisk.agent.core.v2.stream_converter import step_event_to_stream_event
from derisk.agent.core.v2.sse_adapter import stream_to_sse
from derisk.agent.core.v2.baize_subsystem_adapter import BAIZESubsystemAdapter
from derisk.agent.core.v2.usage_metric import emit_usage_metric, aggregate_usage
from derisk.agent.core.v2.thinking_chunk import (
    ThinkingChunk, TokenChunk, ToolCallChunk, UsageChunk, AwaitUserChunk,
)
from derisk.agent.core.hook.schema import BlockingPolicy, HookDecision
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker
from derisk.agent.core.v2.retrying_thinking import retrying_thinking
from derisk.agent.core.v2.tool_resolver import ToolResolver
from derisk.agent.core.v2.tool_context_factory import ToolContextFactory
from derisk.agent.core.v2.hook_integration import (
    build_pre_tool_use_context,
    build_post_tool_use_context,
    build_turn_complete_context,
    build_conversation_complete_context,
)
from derisk.agent.core.v2.memory_hook_setup import register_memory_hooks
from derisk.agent.core.v2.default_acting import make_default_acting_fn
from derisk.agent.core.v2.default_thinking import make_default_thinking_fn
from derisk.agent.core.v2.llm_stream_adapter import make_derisk_llm_stream, make_derisk_llm_stream_fn
from derisk.agent.core.v2.run_loop import run_loop, trigger_conversation_complete

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
    "StreamEvent",
    "EVENT_TYPES",
    "step_event_to_stream_event",
    "stream_to_sse",
    "BAIZESubsystemAdapter",
    "emit_usage_metric",
    "aggregate_usage",
    "ThinkingChunk",
    "TokenChunk",
    "ToolCallChunk",
    "UsageChunk",
    "AwaitUserChunk",
    "BlockingPolicy",
    "HookDecision",
    "V2ToolCall",
    "V2ToolResult",
    "ToolFailureTracker",
    "retrying_thinking",
    "ToolResolver",
    "ToolContextFactory",
    "build_pre_tool_use_context",
    "build_post_tool_use_context",
    "build_turn_complete_context",
    "build_conversation_complete_context",
    "register_memory_hooks",
    "make_default_acting_fn",
    "make_default_thinking_fn",
    "make_derisk_llm_stream",
    "make_derisk_llm_stream_fn",
    "run_loop",
    "trigger_conversation_complete",
]
