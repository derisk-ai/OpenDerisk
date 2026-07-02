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
