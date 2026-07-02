# packages/derisk-core/tests/agent/core/v2/test_package.py
from derisk.agent.core.v2 import (
    StepState,
    StepEvent,
    StateStore,
    DbStateStore,
    EventStream,
    RecoveryCoordinatorV2,
    run_step,
    resume_step,
    validate_transition,
    IllegalTransitionError,
    PermissionMode,
    PermissionGate,
    PermissionResult,
    PermissionDecision,
    SessionPermissionCache,
    hash_tool_input,
    NoInteractionAdapterError,
    SubAgentRuntime,
    SubAgentSpawnSpec,
    SubAgentHandle,
    SubAgentMode,
    SubAgentStatus,
    SubAgentInteractionGateway,
    SpawnSubagentTool,
    AskUserAdapter,
    PermissionCheckResult,
    StreamEvent,
    EVENT_TYPES,
    step_event_to_stream_event,
    stream_to_sse,
    BAIZESubsystemAdapter,
    emit_usage_metric,
    aggregate_usage,
)


def test_all_public_names_importable():
    assert StepState.INIT.value == "init"
    assert callable(run_step)
    assert callable(resume_step)
    assert callable(validate_transition)
    assert issubclass(IllegalTransitionError, Exception)
    assert issubclass(DbStateStore, StateStore)
    # P1 additions
    assert PermissionMode.DEFAULT.value == "default"
    assert PermissionMode.PLAN.value == "plan"
    assert PermissionMode.AUTO.value == "auto"
    assert PermissionMode.BYPASS.value == "bypass"
    assert callable(hash_tool_input)
    assert PermissionDecision.ALLOW == "allow"
    assert PermissionDecision.DENY == "deny"
    assert PermissionDecision.AWAITING == "awaiting"
    assert issubclass(NoInteractionAdapterError, RuntimeError)


def test_p2_exports():
    assert SubAgentMode.SYNC.value == "sync"
    assert SubAgentMode.ASYNC.value == "async"
    assert SubAgentStatus.RUNNING.value == "running"
    assert SubAgentStatus.DONE.value == "done"
    assert callable(SubAgentRuntime)
    assert callable(SpawnSubagentTool)
    assert callable(AskUserAdapter)
    assert PermissionCheckResult(decision="allow").decision == "allow"


def test_p3_exports():
    assert "usage_metric" in EVENT_TYPES
    assert StreamEvent(type="llm_token", payload={}, seq=0, timestamp=0.0).type == "llm_token"
    assert callable(step_event_to_stream_event)
    assert callable(stream_to_sse)
    assert callable(BAIZESubsystemAdapter)
    assert callable(emit_usage_metric)
    assert callable(aggregate_usage)
