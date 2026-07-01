"""PermissionGate — 5-level check chain before every tool call.

Spec §9.3. Levels (in order):
  1. PermissionMode short-circuit (bypass/auto/plan)
  2. session cache (allow_session)
  3. permission_ruleset (static rules: ALLOW/DENY/ASK)
  4. (P1 deferred) Tool.check_permissions hook — no Tool integration yet
  5. ask → emit AWAITING_TOOL_PERMISSION event + persist checkpoint +
     delegate to InteractionAdapter.request_tool_permission

check() is an async generator: it yields AWAITING_TOOL_PERMISSION events
when asking; the caller reads gate.last_result for the final decision.
"""
from __future__ import annotations
import time
import uuid
from typing import AsyncGenerator, Optional, TYPE_CHECKING
from derisk._private.pydantic import BaseModel, ConfigDict
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache, hash_tool_input
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState
from derisk_core.permission.ruleset import PermissionRuleset, PermissionAction

if TYPE_CHECKING:
    from derisk.agent.core.v2.state_store import StateStore
    from derisk.agent.core.v2.event_stream import EventStream
    from derisk.agent.core.interaction_adapter import InteractionAdapter


# Tools that have side effects (write/delete/execute). In P1 we use a simple
# heuristic: tools whose name matches these patterns are side-effecting.
# P2+ can replace this with Tool.metadata.risk_level.
_SIDE_EFFECT_PATTERNS = ("rm", "write", "delete", "execute", "bash", "shell",
                         "mv", "cp", "mkdir", "rmdir", "chmod", "chown")


def _is_side_effecting(tool_name: str) -> bool:
    lower = tool_name.lower()
    return any(p in lower for p in _SIDE_EFFECT_PATTERNS)


class NoInteractionAdapterError(RuntimeError):
    """Raised when PermissionGate reaches the ASK path but no adapter is configured."""


class PermissionDecision:
    ALLOW = "allow"
    DENY = "deny"
    AWAITING = "awaiting"


class PermissionResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)
    decision: str  # PermissionDecision.*
    reason: str = ""
    request_id: Optional[str] = None


class PermissionGate:
    def __init__(
        self,
        state_store: "StateStore",
        event_stream: "EventStream",
        interaction_adapter: Optional["InteractionAdapter"] = None,
        session_cache: Optional[SessionPermissionCache] = None,
        ruleset: Optional[PermissionRuleset] = None,
        mode: PermissionMode = PermissionMode.DEFAULT,
        step_id: Optional[str] = None,
        conv_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        self._store = state_store
        self._stream = event_stream
        self._adapter = interaction_adapter
        self._cache = session_cache or SessionPermissionCache()
        self._ruleset = ruleset
        self._mode = mode
        self._step_id = step_id
        self._conv_id = conv_id
        self._agent_id = agent_id
        self.last_result: PermissionResult = PermissionResult(
            decision=PermissionDecision.DENY, reason="not checked"
        )

    async def check(self, tool_call: dict) -> AsyncGenerator[StepEvent, None]:
        """Run the 5-level check. Yields AWAITING_TOOL_PERMISSION events when asking.
        Sets self.last_result. Caller reads last_result after generator exhausts.
        """
        tool_name = tool_call.get("tool", "")
        tool_input = tool_call.get("input", {}) or {}
        input_hash = hash_tool_input(tool_input)

        # Level 1: PermissionMode short-circuit
        if self._mode is PermissionMode.BYPASS:
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="bypass mode")
            return
        if self._mode is PermissionMode.AUTO:
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="auto mode")
            return
        if self._mode is PermissionMode.PLAN and _is_side_effecting(tool_name):
            self.last_result = PermissionResult(decision=PermissionDecision.DENY, reason="plan mode denies side-effecting tool")
            return

        # Level 2: session cache
        if self._cache.is_allowed(tool_name, input_hash):
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="session cache")
            return

        # Level 3: permission_ruleset
        # No ruleset → ALLOW (safe fallback for P1; caller can pass a ruleset
        # with default_action=ASK to force asking)
        action = PermissionAction.ALLOW
        if self._ruleset is not None:
            action = self._ruleset.check(tool_name, context={})
        if action is PermissionAction.ALLOW:
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="ruleset allow")
            return
        if action is PermissionAction.DENY:
            self.last_result = PermissionResult(decision=PermissionDecision.DENY, reason="ruleset deny")
            return

        # Level 4: Tool.check_permissions — P1 defers this (no Tool integration yet)
        # TODO(P2): if tool has check_permissions, call it; non-None result short-circuits

        # Level 5: ask → emit event + persist + delegate
        if self._adapter is None:
            raise NoInteractionAdapterError(
                f"PermissionGate reached ASK for tool '{tool_name}' but no "
                f"InteractionAdapter is configured"
            )

        request_id = f"req-{uuid.uuid4().hex[:8]}"
        request_payload = {
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "step_id": self._step_id,
            "conv_id": self._conv_id,
        }
        # Persist checkpoint BEFORE emitting (durability before visibility)
        await self._store.save_interaction_checkpoint(
            request_id, self._step_id, self._conv_id, request_payload
        )
        # Emit AWAITING_TOOL_PERMISSION event
        event = StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id=self._step_id,
            conv_id=self._conv_id,
            agent_id=self._agent_id,
            parent_step_id=None,
            state=StepState.AWAITING_TOOL_PERMISSION,
            event_type="interaction_request",
            input=request_payload,
            output={},
            seq=0,  # runtime's _make_emit will overwrite seq; gate uses 0 placeholder
            timestamp=time.time(),
        )
        # Persist + yield via EventStream
        persisted = await self._stream.emit(event)
        yield persisted

        # Delegate to InteractionAdapter (blocks until user responds)
        response = await self._adapter.request_tool_permission(
            tool_name=tool_name, tool_args=tool_input,
        )
        action_str = getattr(response, "action", "deny")
        # Checkpoint deletion is deferred to the runtime (run_step) — it deletes
        # after the tool executes (ALLOW) or skips (DENY). This way the request
        # survives crashes between user approval and tool execution.

        if action_str == "deny":
            self._cache.deny(tool_name, input_hash)
            self.last_result = PermissionResult(
                decision=PermissionDecision.DENY,
                reason="user denied",
                request_id=request_id,
            )
            return
        if action_str == "allow_session":
            self._cache.allow_session(tool_name, input_hash)
        # allow_once: no cache update
        self.last_result = PermissionResult(
            decision=PermissionDecision.ALLOW,
            reason=f"user {action_str}",
            request_id=request_id,
        )
