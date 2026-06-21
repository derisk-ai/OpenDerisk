"""Memory hook dispatcher and default memory hook factory.

This module wires the unified hook system to the long-term memory
manager. It provides:

* `default_memory_hooks(config)` — returns four `HookConfig` entries
  (tier 0 prefetch, tier 1 per-turn write, tier 2 every-N-turns
  reflection, tier 3 session-end curation) that callers can append to a
  conversation's HookManager.

* `get_memory_bundle` / `register_memory_bundle` / `unregister_memory_bundle`
  — per-conversation bundle registry. Read by the memory function hooks
  (tier 0/1) and by the real memory agents (tier 2/3).

* `_do_prefetch` — the deterministic tier-0 prefetch task (background
  retrieval stashed in the per-conv `MemoryReadPipeline` cache).

* `memory_prefetch_function` / `memory_write_turn_function` — in-process
  callables registered with `FunctionRegistry`. They are the tier 0/1
  endpoints (kind=FUNCTION), running deterministically without an LLM.
  Tier 2/3 stay as real agents (`MemoryReflectAgent`,
  `MemoryCurateAgent`) routed via `agent_dispatcher._dispatch_to_agent`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from derisk.agent.core.hook.executors import FunctionRegistry
from derisk.agent.core.hook.schema import (
    HookConfig,
    HookEndpointConfig,
    HookKind,
    HookTriggerConfig,
    HookTriggerType,
)

logger = logging.getLogger(__name__)


# Function names registered with FunctionRegistry for the deterministic
# fast path (tier 0/1). These tiers run every turn — forking a real
# ReAct agent would be wasteful, so they stay programmatic in-process
# callables (mirrors hermes-agent's sync_turn and prefetch_all, which
# are also provider-level, not agent-level).
_MEMORY_PREFETCH_FN_NAME = "memory_prefetch"
_MEMORY_WRITE_TURN_FN_NAME = "memory_write_turn"

# Real agent names (registered in AgentManager via scan_agents).
_MEMORY_REFLECT_AGENT_NAME = "MemoryReflectAgent"
_MEMORY_CURATE_AGENT_NAME = "MemoryCurateAgent"

# Rooms excluded from dynamic retrieval (already frozen into system prompt
# as the static layer). Kept in sync with read_pipeline.STATIC_ROOMS.
_STATIC_ROOMS: List[str] = ["profile", "preference"]


async def _do_prefetch(
    conv_id: str,
    bundle: Any,
    query: str,
    pipeline_lookup: Optional[Any],
) -> None:
    """Background prefetch: retrieve dynamic memories and stash in cache.

    Runs as a fire-and-forget task. Failures are logged and swallowed —
    the next turn will just see no prefetch and fall back to sync retrieval.
    """
    pipeline = _lookup_pipeline(conv_id, pipeline_lookup)
    if pipeline is None:
        logger.debug(
            "[MemoryHookDispatcher] prefetch: no pipeline for conv %s; skipping",
            conv_id,
        )
        return
    try:
        manager = bundle.manager
        result = await manager.retrieve_relevant_memories(
            query=query,
            top_k=getattr(bundle.config, "top_k", 5),
            use_hybrid_search=True,
            exclude_rooms=_STATIC_ROOMS,
        )
        cache = pipeline.get_prefetch_cache()
        cache.reset()
        cache.set_result(query, result or "")
        logger.info(
            "[MemoryHookDispatcher] prefetch ready conv=%s (%d chars)",
            conv_id,
            len(result or ""),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[MemoryHookDispatcher] prefetch failed conv=%s: %s", conv_id, e
        )


def default_memory_hooks(
    config: Any,
    reflection_interval: Optional[int] = None,
) -> List[HookConfig]:
    """Build the four default memory hook entries for a conversation.

    Tier 0/1 use sentinel agent names routed through the deterministic
    fast path in `agent_dispatcher`. Tier 2/3 use real agent names
    (`MemoryReflectAgent`, `MemoryCurateAgent`) registered in
    `AgentManager` via `scan_agents("derisk.agent.expand")`.

    Args:
        config: LongTermMemoryConfig. Reads `reflection_interval` if present.
        reflection_interval: Override the tier 2 cadence. Defaults to
            `config.reflection_interval` or 10.

    Returns:
        Four HookConfig entries: tier 0 (prefetch), tier 1 (per-turn write),
        tier 2 (every-N-turns reflection), tier 3 (session-end curation).
    """
    if reflection_interval is None:
        reflection_interval = getattr(config, "reflection_interval", 10) or 10

    return [
        HookConfig(
            name="memory_tier0_prefetch",
            description="Prefetch dynamic memories for next turn (async)",
            trigger=HookTriggerConfig(
                trigger_type=HookTriggerType.TURN_COMPLETE.value,
                every_n_turns=1,
                extra={"tier": 0},
            ),
            endpoint=HookEndpointConfig(
                kind=HookKind.FUNCTION,
                function_name=_MEMORY_PREFETCH_FN_NAME,
                blocking=False,
            ),
            priority=190,
        ),
        HookConfig(
            name="memory_tier1_turn",
            description="Per-turn lightweight memory write (async)",
            trigger=HookTriggerConfig(
                trigger_type=HookTriggerType.TURN_COMPLETE.value,
                every_n_turns=1,
                extra={"tier": 1},
            ),
            endpoint=HookEndpointConfig(
                kind=HookKind.FUNCTION,
                function_name=_MEMORY_WRITE_TURN_FN_NAME,
                blocking=False,
            ),
            priority=200,
        ),
        HookConfig(
            name="memory_tier2_reflect",
            description=f"Cross-turn reflection every {reflection_interval} turns (async)",
            trigger=HookTriggerConfig(
                trigger_type=HookTriggerType.TURN_COMPLETE.value,
                every_n_turns=reflection_interval,
                extra={"tier": 2, "n": reflection_interval},
            ),
            endpoint=HookEndpointConfig(
                kind=HookKind.AGENT,
                agent_name=_MEMORY_REFLECT_AGENT_NAME,
                blocking=False,
            ),
            priority=210,
        ),
        HookConfig(
            name="memory_tier3_curate",
            description="Session-end curation: promotion + snapshot (async)",
            trigger=HookTriggerConfig(
                trigger_type=HookTriggerType.CONVERSATION_COMPLETE.value,
                extra={"tier": 3},
            ),
            endpoint=HookEndpointConfig(
                kind=HookKind.AGENT,
                agent_name=_MEMORY_CURATE_AGENT_NAME,
                blocking=False,
            ),
            priority=220,
        ),
    ]


# ---------------------------------------------------------------------------
# Tier 0/1 function endpoints (registered with FunctionRegistry)
# ---------------------------------------------------------------------------


async def memory_prefetch_function(
    event: Dict[str, Any],
    runtime: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tier 0 fast path: prefetch dynamic memories for the next turn.

    Runs every turn_complete. Fire-and-forget — the prefetch task is
    scheduled in the background so tier 1 (also on turn_complete) does
    not wait on us. Failures are logged and swallowed (the next turn
    just falls back to sync retrieval).

    Registered with FunctionRegistry as ``memory_prefetch``.
    """
    conv_id = event.get("conv_id")
    if not conv_id:
        logger.debug("[memory_prefetch] no conv_id; skipping")
        return {"action": "continue"}

    bundle = get_memory_bundle(conv_id)
    if bundle is None or getattr(bundle, "manager", None) is None:
        logger.debug(
            "[memory_prefetch] no bundle for conv %s; skipping", conv_id
        )
        return {"action": "continue"}

    extra = event.get("extra") or {}
    interrupted = extra.get("interrupted") or (event.get("success") is False)
    if interrupted:
        logger.info(
            "[memory_prefetch] skipped (interrupted) conv=%s", conv_id
        )
        return {"action": "continue"}

    query = event.get("user_prompt") or ""
    if not query:
        return {"action": "continue"}

    logger.info(
        "[memory_prefetch] fired conv=%s round=%s",
        conv_id,
        event.get("round"),
    )
    # Fire-and-forget — tier 1 should not wait on us.
    asyncio.create_task(_do_prefetch(conv_id, bundle, query, None))
    return {"action": "continue"}


async def memory_write_turn_function(
    event: Dict[str, Any],
    runtime: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tier 1 fast path: per-turn lightweight memory write.

    Runs every turn_complete. Calls `LongTermMemoryManager.write_turn_lightweight`
    directly (no LLM fork, no AgentManager). Each bound space processes
    the turn independently based on its own strategy.

    Registered with FunctionRegistry as ``memory_write_turn``.
    """
    conv_id = event.get("conv_id")
    if not conv_id:
        logger.debug("[memory_write_turn] no conv_id; skipping")
        return {"action": "continue"}

    bundle = get_memory_bundle(conv_id)
    if bundle is None or getattr(bundle, "manager", None) is None:
        logger.debug(
            "[memory_write_turn] no bundle for conv %s; skipping", conv_id
        )
        return {"action": "continue"}

    user_msg = event.get("user_prompt") or ""
    ai_msg = event.get("final_answer") or ""
    if not (user_msg or ai_msg):
        return {"action": "continue"}

    manager = bundle.manager
    app_code = event.get("app_code")
    logger.info(
        "[memory_write_turn] fired conv=%s round=%s",
        conv_id,
        event.get("round"),
    )
    try:
        await manager.write_turn_lightweight(
            user_message=user_msg,
            agent_response=ai_msg,
            metadata={
                "conv_id": conv_id,
                "agent_name": event.get("agent_name"),
                "app_code": app_code,
                "round": event.get("round"),
                "tier": 1,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[memory_write_turn] failed for conv %s: %s", conv_id, e
        )
    return {"action": "continue"}


# Register on import so HookManager can resolve the function_name as
# soon as default_memory_hooks() emits tier 0/1 entries.
FunctionRegistry.register(_MEMORY_PREFETCH_FN_NAME, memory_prefetch_function)
FunctionRegistry.register(_MEMORY_WRITE_TURN_FN_NAME, memory_write_turn_function)


# ---------------------------------------------------------------------------
# Bundle registry
# ---------------------------------------------------------------------------


# Per-conversation bundle registry. gpts_memory.register_memory_bundle
# populates this; the agent_dispatcher reads from it. Kept module-level
# so the dispatcher can be registered as a plain callable without closure
# state.
_BUNDLE_REGISTRY: Dict[str, Any] = {}

# Per-conversation MemoryReadPipeline registry. Populated lazily by
# gpts_memory.get_memory_pipeline; the dispatcher reads from it for tier 0
# prefetch. Falls back to gpts_memory if not registered here.
_PIPELINE_REGISTRY: Dict[str, Any] = {}


def register_memory_bundle(conv_id: str, bundle: Any) -> None:
    """Register a memory bundle for a conversation."""
    if conv_id:
        _BUNDLE_REGISTRY[conv_id] = bundle


def register_memory_pipeline(conv_id: str, pipeline: Any) -> None:
    """Register a MemoryReadPipeline for a conversation (optional hint)."""
    if conv_id:
        _PIPELINE_REGISTRY[conv_id] = pipeline


def unregister_memory_bundle(conv_id: str) -> None:
    """Remove a bundle (and its pipeline) from the registry."""
    _BUNDLE_REGISTRY.pop(conv_id, None)
    _PIPELINE_REGISTRY.pop(conv_id, None)


def get_memory_bundle(conv_id: str) -> Optional[Any]:
    """Look up a registered bundle by conv_id."""
    return _BUNDLE_REGISTRY.get(conv_id)


def get_memory_pipeline(conv_id: str) -> Optional[Any]:
    """Look up a registered pipeline by conv_id (registry hint only)."""
    return _PIPELINE_REGISTRY.get(conv_id)


def _lookup_bundle(conv_id: str, bundle_lookup: Optional[Any]) -> Optional[Any]:
    if bundle_lookup is not None:
        try:
            return bundle_lookup(conv_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("[MemoryHookDispatcher] bundle_lookup failed: %s", e)
            return None
    return get_memory_bundle(conv_id)


def _lookup_pipeline(
    conv_id: str, pipeline_lookup: Optional[Any]
) -> Optional[Any]:
    if pipeline_lookup is not None:
        try:
            return pipeline_lookup(conv_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("[MemoryHookDispatcher] pipeline_lookup failed: %s", e)
            return None
    pipeline = get_memory_pipeline(conv_id)
    if pipeline is not None:
        return pipeline
    # Fall back to the bundle's gpts_memory if attached.
    return None


__all__ = [
    "default_memory_hooks",
    "memory_prefetch_function",
    "memory_write_turn_function",
    "register_memory_bundle",
    "register_memory_pipeline",
    "unregister_memory_bundle",
    "get_memory_bundle",
    "get_memory_pipeline",
]
