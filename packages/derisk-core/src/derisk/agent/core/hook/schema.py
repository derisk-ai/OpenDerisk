"""Unified Hook System schema.

This module defines the configuration schema and runtime data structures for
the OpenDerisk unified hook platform. The platform supports three endpoint
kinds (`agent`, `api`, `cli`), several trigger points, and four blocking
policies. The CLI/API protocols are aligned with Anthropic Claude Code so
existing CC plugin hooks can be reused without modification.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, Field, model_to_dict


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class HookKind(str, Enum):
    AGENT = "agent"
    API = "api"
    CLI = "cli"
    FUNCTION = "function"


class BlockingPolicy(str, Enum):
    """Result of a hook execution.

    - continue: 放行
    - deny: 软阻断（跳过当前工具，原因回灌给 LLM，对话继续）
    - abort: 硬终止（终结整个对话）
    - modify: 改写工具参数后继续
    """

    CONTINUE = "continue"
    DENY = "deny"
    ABORT = "abort"
    MODIFY = "modify"


class HookTriggerType(str, Enum):
    """The supported trigger points.

    名称尽量与 Claude Code 对齐，便于直接复用 CC plugin hooks 的事件名。
    """

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    CONVERSATION_START = "conversation_start"
    CONVERSATION_COMPLETE = "conversation_complete"
    STATE_CHANGE = "state_change"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    ERROR_OCCURRED = "error_occurred"
    TURN_COMPLETE = "turn_complete"


VALID_TRIGGER_TYPES = {t.value for t in HookTriggerType}


# Mapping between Claude Code event names (CamelCase) and our snake_case ones,
# so plugin manifests can be imported as-is.
CC_EVENT_TO_TRIGGER: Dict[str, str] = {
    "PreToolUse": HookTriggerType.PRE_TOOL_USE.value,
    "PostToolUse": HookTriggerType.POST_TOOL_USE.value,
    "UserPromptSubmit": HookTriggerType.USER_PROMPT_SUBMIT.value,
    "SessionStart": HookTriggerType.CONVERSATION_START.value,
    "SessionEnd": HookTriggerType.CONVERSATION_COMPLETE.value,
    "Stop": HookTriggerType.CONVERSATION_COMPLETE.value,
    "Notification": HookTriggerType.STATE_CHANGE.value,
}


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------


class HookEndpointConfig(BaseModel):
    """Where a hook actually executes.

    `kind` chooses one of three execution backends and the corresponding
    fields are honoured.
    """

    kind: HookKind = Field(HookKind.API, description="Endpoint kind")

    # --- agent kind ---
    agent_name: Optional[str] = Field(
        None,
        description="Target agent name to dispatch the hook event to",
    )
    agent_app_code: Optional[str] = Field(
        None,
        description="Optional app_code if the hook is implemented as a sub-app",
    )

    # --- api kind ---
    api_url: Optional[str] = Field(None, description="HTTPS POST endpoint URL")
    api_headers: Dict[str, str] = Field(
        default_factory=dict, description="Static headers"
    )
    api_auth_token: Optional[str] = Field(
        None, description="If set, sent as `Authorization: Bearer <token>`"
    )

    # --- cli kind ---
    cli_command: Optional[str] = Field(
        None,
        description="Shell command template; the JSON event is delivered via stdin",
    )
    cli_allowlist: List[str] = Field(
        default_factory=list,
        description="Allowed first-token of cli_command. Required when in_sandbox is False",
    )
    cli_in_sandbox: bool = Field(
        True,
        description="Execute inside the agent sandbox (recommended). When False, uses local subprocess restricted to allowlist.",
    )
    cli_cwd: Optional[str] = Field(
        None,
        description="Working directory for the CLI command (sandbox path or host path)",
    )

    # --- function kind ---
    function_name: Optional[str] = Field(
        None,
        description=(
            "Registered internal callable name. Resolved via FunctionRegistry "
            "at execution time. Use this for in-process hooks that do not "
            "need an LLM or a real Agent (e.g. memory tier 0/1 fast paths)."
        ),
    )

    # --- generic ---
    timeout: int = Field(30, description="Per-execution timeout in seconds")
    blocking: bool = Field(
        False,
        description="When True, the hook runs synchronously and its decision is honoured. "
        "Only meaningful for pre_* triggers.",
    )
    default_on_error: BlockingPolicy = Field(
        BlockingPolicy.CONTINUE,
        description="Decision used when the hook execution fails or times out",
    )

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self)


class HookTriggerConfig(BaseModel):
    """Conditions that decide whether a hook fires for a given event."""

    trigger_type: str = Field(..., description="See HookTriggerType")
    tool_name_globs: List[str] = Field(
        default_factory=lambda: ["*"],
        description="fnmatch-style filters on tool name. Used for pre/post_tool_use.",
    )
    state_from: Optional[str] = Field(
        None, description="Filter on state_change: from-state"
    )
    state_to: Optional[str] = Field(
        None, description="Filter on state_change: to-state"
    )
    every_n_turns: Optional[int] = Field(
        None,
        description="Only fire every N turns. Used with turn_complete. "
        "None or 1 means every turn. N>1 fires only when round % N == 0.",
    )
    extra: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self)


class HookConfig(BaseModel):
    """A single hook entry: a trigger + an endpoint."""

    name: str = Field(..., description="Stable identifier shown in logs / UI")
    enabled: bool = Field(True)
    trigger: HookTriggerConfig
    endpoint: HookEndpointConfig
    description: Optional[str] = None
    priority: int = Field(
        100,
        description="Lower runs first. When multiple hooks fire for the same trigger, "
        "they execute in priority order; the first abort/deny short-circuits.",
    )

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self)


class TeamHookConfig(BaseModel):
    """The hook bundle attached to an app's TeamContext."""

    enabled: bool = Field(True, description="Master switch")
    hooks: List[HookConfig] = Field(default_factory=list)
    plugin_paths: List[str] = Field(
        default_factory=list,
        description="Filesystem paths or package URIs of Claude Code style plugins to merge",
    )

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self)


# ---------------------------------------------------------------------------
# Runtime data
# ---------------------------------------------------------------------------


class HookEvent(BaseModel):
    """The JSON payload sent to API/CLI hooks (and to agent hooks as context)."""

    hook_event_name: str
    conv_id: Optional[str] = None
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    app_code: Optional[str] = None
    round: Optional[int] = None

    # tool fields
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_response: Optional[Any] = None
    success: Optional[bool] = None

    # state-change / lifecycle
    session_state: Optional[Dict[str, str]] = None
    final_answer: Optional[str] = None
    user_prompt: Optional[str] = None
    error: Optional[str] = None

    timestamp: int = Field(default_factory=lambda: int(time.time()))
    extra: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self, exclude_none=True)


class HookDecision(BaseModel):
    """The unified result returned by a hook execution."""

    action: BlockingPolicy = BlockingPolicy.CONTINUE
    reason: Optional[str] = None
    modified_input: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def cont(cls) -> "HookDecision":
        return cls(action=BlockingPolicy.CONTINUE)

    @classmethod
    def deny(cls, reason: str) -> "HookDecision":
        return cls(action=BlockingPolicy.DENY, reason=reason)

    @classmethod
    def abort(cls, reason: str) -> "HookDecision":
        return cls(action=BlockingPolicy.ABORT, reason=reason)

    @classmethod
    def modify(
        cls, modified_input: Dict[str, Any], reason: Optional[str] = None
    ) -> "HookDecision":
        return cls(
            action=BlockingPolicy.MODIFY,
            modified_input=modified_input,
            reason=reason,
        )

    def to_dict(self) -> Dict[str, Any]:
        return model_to_dict(self, exclude_none=True)


# Decision merge order, the higher the integer, the higher the priority.
_DECISION_PRIORITY: Dict[BlockingPolicy, int] = {
    BlockingPolicy.CONTINUE: 0,
    BlockingPolicy.MODIFY: 1,
    BlockingPolicy.DENY: 2,
    BlockingPolicy.ABORT: 3,
}


def merge_decisions(decisions: List[HookDecision]) -> HookDecision:
    """Combine decisions from multiple hooks for the same trigger.

    Order: abort > deny > modify > continue. The first abort/deny short-circuits;
    multiple modify decisions are merged left-to-right.
    """
    if not decisions:
        return HookDecision.cont()

    final = HookDecision.cont()
    merged_input: Dict[str, Any] = {}
    has_modify = False
    for d in decisions:
        if d.action == BlockingPolicy.ABORT:
            return d
        if d.action == BlockingPolicy.DENY:
            return d
        if d.action == BlockingPolicy.MODIFY and d.modified_input:
            merged_input.update(d.modified_input)
            has_modify = True
            final = d
    if has_modify:
        return HookDecision(
            action=BlockingPolicy.MODIFY,
            modified_input=merged_input,
            reason=final.reason,
        )
    return HookDecision.cont()


def parse_team_hook_config(raw: Any) -> Optional[TeamHookConfig]:
    """Parse arbitrary user input (dict / json str / model) into TeamHookConfig."""
    if raw is None:
        return None
    if isinstance(raw, TeamHookConfig):
        return raw
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, dict):
        try:
            return TeamHookConfig(**raw)
        except Exception:
            return None
    return None
