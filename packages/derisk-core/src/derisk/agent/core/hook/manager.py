"""Per-conversation hook orchestrator.

The HookManager is built once for each conversation from
`team_context.hook_config`. It owns:

* A list of `HookConfig` entries (config + plugin-imported).
* A `HookTriggerChecker` to decide who fires for a given trigger.
* The runtime needed by the executors (sandbox client, agent dispatcher, …).

It exposes two trigger entry points:

* `trigger(trigger_type, context)` — fire-and-forget, schedules each matching
  hook on the running event loop. Returns immediately.
* `trigger_blocking(trigger_type, context)` — awaits all hooks marked
  `endpoint.blocking=True` and returns a merged `HookDecision`. Non-blocking
  hooks are scheduled in the background.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .claude_code_plugin import load_plugin_hooks
from .executors import get_executor
from .schema import (
    BlockingPolicy,
    HookConfig,
    HookDecision,
    HookEvent,
    TeamHookConfig,
    merge_decisions,
    parse_team_hook_config,
)
from .trigger_checker import HookTriggerChecker

logger = logging.getLogger(__name__)


class HookManager:
    def __init__(
        self,
        config: Optional[TeamHookConfig],
        runtime: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config: TeamHookConfig = config or TeamHookConfig(enabled=False, hooks=[])
        self.runtime: Dict[str, Any] = runtime or {}
        self.checker = HookTriggerChecker()

        self._hooks: List[HookConfig] = list(self.config.hooks)
        if self.config.plugin_paths:
            try:
                imported = load_plugin_hooks(self.config.plugin_paths, in_sandbox=True)
                if imported:
                    logger.info(
                        "Imported %d hooks from %d Claude Code plugin paths",
                        len(imported),
                        len(self.config.plugin_paths),
                    )
                self._hooks.extend(imported)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to import CC plugins: %s", e)

        # Stable order: lower priority first (1 ≺ 50 ≺ 100).
        self._hooks.sort(key=lambda h: h.priority)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self._hooks)

    @property
    def hooks(self) -> List[HookConfig]:
        return list(self._hooks)

    def update_runtime(self, **kwargs: Any) -> None:
        """Late-binding for runtime values like the sandbox client."""
        self.runtime.update({k: v for k, v in kwargs.items() if v is not None})

    def append_hooks(self, hooks: List[HookConfig]) -> None:
        """Append hooks at runtime and re-sort by priority.

        Used by higher-level subsystems (e.g. the memory integration) to
        register their own hooks after the HookManager has been built from
        `team_context.hook_config`, without mutating the team config.
        """
        if not hooks:
            return
        self._hooks.extend(hooks)
        self._hooks.sort(key=lambda h: h.priority)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def trigger(self, trigger_type: str, context: Dict[str, Any]) -> None:
        """Fire-and-forget. Schedules execution and returns immediately."""
        if not self.enabled:
            return
        for hook in self._matching(trigger_type, context):
            asyncio.create_task(self._safe_execute(hook, trigger_type, context))

    async def trigger_blocking(
        self,
        trigger_type: str,
        context: Dict[str, Any],
    ) -> HookDecision:
        """Run all `blocking=True` hooks synchronously and merge their decisions.

        Hooks with `blocking=False` are still scheduled but their result is
        discarded.
        """
        if not self.enabled:
            return HookDecision.cont()
        matched = self._matching(trigger_type, context)
        if not matched:
            return HookDecision.cont()

        decisions: List[HookDecision] = []
        for hook in matched:
            if not hook.endpoint.blocking:
                # background, don't wait
                asyncio.create_task(self._safe_execute(hook, trigger_type, context))
                continue
            decision = await self._safe_execute(hook, trigger_type, context)
            decisions.append(decision)
            # short-circuit on terminal outcomes
            if decision.action in (BlockingPolicy.ABORT, BlockingPolicy.DENY):
                return decision
        return merge_decisions(decisions)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _matching(self, trigger_type: str, context: Dict[str, Any]) -> List[HookConfig]:
        return [
            h
            for h in self._hooks
            if self.checker.should_trigger(h, trigger_type, context)
        ]

    async def _safe_execute(
        self, hook: HookConfig, trigger_type: str, context: Dict[str, Any]
    ) -> HookDecision:
        event = self._build_event(hook, trigger_type, context)
        executor = get_executor(hook.endpoint.kind)
        start = time.time()
        try:
            decision = await executor.execute(event, hook.endpoint, self.runtime)
        except Exception as e:  # noqa: BLE001
            logger.exception("Hook %s execution crashed: %s", hook.name, e)
            return HookDecision.cont()
        cost_ms = int((time.time() - start) * 1000)
        if decision.action != BlockingPolicy.CONTINUE:
            logger.info(
                "Hook %s -> %s (reason=%s, %dms)",
                hook.name,
                decision.action.value,
                decision.reason,
                cost_ms,
            )
        else:
            logger.debug("Hook %s -> continue (%dms)", hook.name, cost_ms)
        return decision

    def _build_event(
        self, hook: HookConfig, trigger_type: str, context: Dict[str, Any]
    ) -> HookEvent:
        ctx = dict(context or {})
        return HookEvent(
            hook_event_name=trigger_type,
            conv_id=ctx.pop("conv_id", None),
            session_id=ctx.pop("session_id", None),
            agent_name=ctx.pop("agent_name", None),
            agent_role=ctx.pop("agent_role", None),
            app_code=ctx.pop("app_code", None),
            round=ctx.pop("round", None),
            tool_name=ctx.pop("tool_name", None),
            tool_input=ctx.pop("tool_input", None),
            tool_response=ctx.pop("tool_response", None),
            success=ctx.pop("success", None),
            session_state=ctx.pop("session_state", None),
            final_answer=ctx.pop("final_answer", None),
            user_prompt=ctx.pop("user_prompt", None),
            error=ctx.pop("error", None),
            extra=ctx,
        )


def build_hook_manager(
    team_context: Any,
    runtime: Optional[Dict[str, Any]] = None,
) -> Optional[HookManager]:
    """Build a HookManager from a TeamContext-like object.

    Returns None when no hook config is provided so callers can cheaply skip.
    """
    if team_context is None:
        return None
    raw = getattr(team_context, "hook_config", None)
    if raw is None and isinstance(team_context, dict):
        raw = team_context.get("hook_config")
    cfg = parse_team_hook_config(raw)
    if cfg is None or not cfg.enabled:
        return None
    return HookManager(cfg, runtime=runtime or {})


# ---------------------------------------------------------------------------
# Optional dispatch helper for kind=agent endpoints. The default implementation
# is intentionally a no-op so we don't pull dependencies on the agent runtime
# into this module. Higher-level glue can register a real dispatcher.
# ---------------------------------------------------------------------------

AgentDispatcher = Callable[..., Any]
