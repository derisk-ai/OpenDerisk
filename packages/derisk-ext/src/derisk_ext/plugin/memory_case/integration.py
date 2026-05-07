"""Wire memory_case into derisk-core ResourceResolver (no hard-coded branch in core)."""

from __future__ import annotations

_registered = False


def ensure_memory_case_resource_resolver_registered() -> None:
    """Idempotent: register tool(memory_case) / memory_case on ResourceResolver."""
    global _registered
    if _registered:
        return
    from derisk.agent.core_v2.agent_binding import ResourceResolver

    from .resource_resolve import resolve_memory_case_resource_value

    ResourceResolver.register_custom_resource_resolver(
        "tool(memory_case)",
        resolve_memory_case_resource_value,
    )
    ResourceResolver.register_custom_resource_resolver(
        "memory_case",
        resolve_memory_case_resource_value,
    )

    from derisk.agent.conversation_scope_hooks import register_conversation_scope_hook

    from .scope_binding import bind_memory_case_scope_for_agent

    register_conversation_scope_hook(bind_memory_case_scope_for_agent)

    _registered = True
