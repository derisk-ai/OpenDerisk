"""Trigger matching for the unified hook system."""
from __future__ import annotations

import fnmatch
import logging
from typing import Any, Dict

from .schema import HookConfig, HookTriggerType, VALID_TRIGGER_TYPES

logger = logging.getLogger(__name__)


class HookTriggerChecker:
    """Decide whether a HookConfig should fire for a given event context."""

    def should_trigger(self, hook: HookConfig, trigger_type: str, context: Dict[str, Any]) -> bool:
        if not hook.enabled:
            return False
        if hook.trigger.trigger_type != trigger_type:
            return False
        if trigger_type not in VALID_TRIGGER_TYPES:
            logger.debug("Unknown trigger_type=%s — skipping hook %s", trigger_type, hook.name)
            return False

        if trigger_type in (
            HookTriggerType.PRE_TOOL_USE.value,
            HookTriggerType.POST_TOOL_USE.value,
        ):
            return self._match_tool(hook, context)

        if trigger_type == HookTriggerType.STATE_CHANGE.value:
            return self._match_state(hook, context)

        if trigger_type == HookTriggerType.TURN_COMPLETE.value:
            return self._match_every_n_turns(hook, context)

        return True

    @staticmethod
    def _match_every_n_turns(hook: HookConfig, context: Dict[str, Any]) -> bool:
        n = hook.trigger.every_n_turns
        if n is None or n <= 1:
            return True
        round_ = context.get("round") or 0
        if round_ <= 0:
            return False
        return (round_ % n) == 0

    @staticmethod
    def _match_tool(hook: HookConfig, context: Dict[str, Any]) -> bool:
        tool_name = context.get("tool_name") or ""
        globs = hook.trigger.tool_name_globs or ["*"]
        return any(fnmatch.fnmatchcase(tool_name, g) for g in globs)

    @staticmethod
    def _match_state(hook: HookConfig, context: Dict[str, Any]) -> bool:
        state = context.get("session_state") or {}
        if hook.trigger.state_from and state.get("from") != hook.trigger.state_from:
            return False
        if hook.trigger.state_to and state.get("to") != hook.trigger.state_to:
            return False
        return True
