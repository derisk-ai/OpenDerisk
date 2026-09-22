"""Pluggable hooks for binding per-conversation context before an Agent runs.

Extensions (e.g. case-memory) register callables; chat / core_v2 call
``bind_conversation_scope_for_agent`` with no knowledge of specific plugins.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# (app_code, conv_id) — conv_id may be None
ConversationScopeHook = Callable[[str, Optional[str]], None]

_hooks: List[ConversationScopeHook] = []


def register_conversation_scope_hook(fn: ConversationScopeHook) -> None:
    """Register a hook; duplicate registrations are ignored."""
    if fn in _hooks:
        return
    _hooks.append(fn)


def clear_conversation_scope_hooks() -> None:
    """Clear all hooks (intended for tests)."""
    _hooks.clear()


def bind_conversation_scope_for_agent(
    app_code: str,
    conv_id: Optional[str] = None,
) -> None:
    """Invoke every registered scope hook (best-effort; one failure does not block others)."""
    code = app_code or "default"
    for fn in list(_hooks):
        try:
            fn(code, conv_id)
        except Exception:
            logger.exception("conversation_scope_hook failed: %s", getattr(fn, "__name__", fn))
