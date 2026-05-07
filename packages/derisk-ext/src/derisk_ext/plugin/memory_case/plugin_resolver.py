"""Registry for the memory_case plugin (filled from derisk-serve McpService)."""

from __future__ import annotations

from typing import Callable, Optional

from derisk.component import SystemApp

from .service import MemoryCasePluginService

MemoryCasePluginResolver = Callable[[SystemApp], Optional[MemoryCasePluginService]]

_resolver: Optional[MemoryCasePluginResolver] = None


def register_memory_case_plugin_resolver(fn: MemoryCasePluginResolver) -> None:
    """Register how to obtain ``MemoryCasePluginService`` for a ``SystemApp``.

    Called from ``derisk_serve.mcp.service.Service.init_app`` after the plugin is built.
    """
    global _resolver
    _resolver = fn


def clear_memory_case_plugin_resolver() -> None:
    """Clear resolver (e.g. tests)."""
    global _resolver
    _resolver = None


def resolve_memory_case_plugin(
    system_app: SystemApp,
) -> Optional[MemoryCasePluginService]:
    if _resolver is None:
        return None
    return _resolver(system_app)
