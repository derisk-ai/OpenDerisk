"""Generic agent dispatcher for the unified hook system.

Routes `kind=agent` hook endpoints to real agents registered in
`AgentManager`. The endpoint's `agent_name` is resolved via
`AgentManager.get(name)` and the event is delivered through
`agent.generate_reply` as a JSON `AgentMessage`.

Tier 0 (prefetch) and tier 1 (per-turn write) of the memory subsystem
do NOT go through this dispatcher — they are `kind=function` endpoints
(see `hook_dispatcher.memory_prefetch_function` /
`memory_write_turn_function`), running as in-process callables without
an LLM fork. Tier 2 (reflect) and tier 3 (curate) are real agents
(`MemoryReflectAgent`, `MemoryCurateAgent`) and DO go through here.

Failures never propagate to the hook executor: every path returns
`{"action": "continue"}` so memory operations can never block the agent
loop.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


async def agent_dispatcher(
    agent_name: Optional[str] = None,
    app_code: Optional[str] = None,
    event: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Route a hook event to a real agent via AgentManager.

    Args:
        agent_name: Endpoint agent_name. Must be a real agent registered
            in `AgentManager` (e.g. `MemoryReflectAgent`,
            `MemoryCurateAgent`, or any user-defined agent).
        app_code: Optional app_code (logging + passed through to agent).
        event: The hook event dict. Serialized to JSON and delivered as
            `AgentMessage.content` so the target agent can extract
            `conv_id` and any other payload fields it needs.
        timeout: Per-call timeout hint (seconds). Currently best-effort —
            the dispatcher does not hard-cancel long-running agents.

    Returns:
        Always `{"action": "continue"}` — agent ops never block the
        hook executor.
    """
    event = event or {}
    return await _dispatch_to_agent(
        agent_name, event, app_code=app_code, timeout=timeout
    )


async def _dispatch_to_agent(
    agent_name: Optional[str],
    event: Dict[str, Any],
    app_code: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolve `agent_name` via AgentManager and call generate_reply.

    The full event dict is serialized into `AgentMessage.content` so the
    target agent (e.g. MemoryReflectAgent) can extract `conv_id` and any
    other payload fields it needs. Global singleton agents stay stateless
    — they look up per-conv state via `hook_dispatcher.get_memory_bundle`.
    """
    if not agent_name:
        logger.debug("[AgentDispatcher] dispatch: empty agent_name; skipping")
        return {"action": "continue"}

    try:
        from derisk.agent.core.agent_manage import get_agent_manager
    except Exception as e:  # noqa: BLE001
        logger.warning("[AgentDispatcher] AgentManager unavailable: %s", e)
        return {"action": "continue"}

    try:
        mgr = get_agent_manager()
    except Exception as e:  # noqa: BLE001
        logger.warning("[AgentDispatcher] get_agent_manager failed: %s", e)
        return {"action": "continue"}

    agent = mgr.get(agent_name) if mgr is not None else None
    if agent is None:
        logger.warning(
            "[AgentDispatcher] agent %s not registered; skipping "
            "(scan_agents did not pick it up?)",
            agent_name,
        )
        return {"action": "continue"}

    conv_id = event.get("conv_id") or ""
    logger.info(
        "[AgentDispatcher] dispatching to %s conv=%s round=%s",
        agent_name,
        conv_id,
        event.get("round"),
    )

    # Build an AgentMessage carrying the full event JSON. The agent
    # parses what it needs (conv_id, extra, etc.) from content.
    from derisk.agent.core.types import AgentMessage

    event_for_agent = dict(event)
    event_for_agent.setdefault("app_code", app_code)
    if "hook_event_name" not in event_for_agent:
        event_for_agent["hook_event_name"] = event_for_agent.get(
            "trigger_type", "agent_dispatch"
        )

    msg = AgentMessage(
        message_id=uuid4().hex,
        content=json.dumps(event_for_agent, ensure_ascii=False, default=str),
        current_goal=f"handle {event_for_agent['hook_event_name']}",
        role="user",
    )

    try:
        await agent.generate_reply(
            received_message=msg,
            sender=agent,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[AgentDispatcher] agent %s generate_reply failed (conv=%s): %s",
            agent_name,
            conv_id,
            e,
        )

    return {"action": "continue"}


__all__ = [
    "agent_dispatcher",
    "_dispatch_to_agent",
]
