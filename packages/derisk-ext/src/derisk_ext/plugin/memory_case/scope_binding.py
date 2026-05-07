"""Bind case-memory scope before Agent runs (single entry for chat / core_v2)."""

from __future__ import annotations

from typing import Optional

from .tool_pack import set_memory_case_scope


def bind_memory_case_scope_for_agent(
    app_code: str,
    conv_id: Optional[str] = None,
) -> None:
    """Set ``app_code`` / ``conv_id`` on the async context used by memory_case tools."""
    set_memory_case_scope(app_code=app_code or "default", conv_id=conv_id)
