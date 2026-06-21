"""DeRisk Unified Hook System.

Public re-exports — keep import surface small and stable.
"""
from .schema import (
    BlockingPolicy,
    HookConfig,
    HookDecision,
    HookEndpointConfig,
    HookEvent,
    HookKind,
    HookTriggerConfig,
    HookTriggerType,
    TeamHookConfig,
    VALID_TRIGGER_TYPES,
    merge_decisions,
    parse_team_hook_config,
)
from .manager import HookManager, build_hook_manager
from .trigger_checker import HookTriggerChecker
from .executors import (
    AgentHookExecutor,
    ApiHookExecutor,
    BaseHookExecutor,
    CliHookExecutor,
    ExecutorRegistry,
    FunctionHookExecutor,
    FunctionRegistry,
    get_executor,
)
from .claude_code_plugin import load_plugin_hooks

__all__ = [
    "BlockingPolicy",
    "HookConfig",
    "HookDecision",
    "HookEndpointConfig",
    "HookEvent",
    "HookKind",
    "HookManager",
    "HookTriggerChecker",
    "HookTriggerConfig",
    "HookTriggerType",
    "TeamHookConfig",
    "VALID_TRIGGER_TYPES",
    "AgentHookExecutor",
    "ApiHookExecutor",
    "BaseHookExecutor",
    "CliHookExecutor",
    "ExecutorRegistry",
    "FunctionHookExecutor",
    "FunctionRegistry",
    "build_hook_manager",
    "get_executor",
    "load_plugin_hooks",
    "merge_decisions",
    "parse_team_hook_config",
]
