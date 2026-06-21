"""Memory Curate Agent — tier 3 session-end curation.

Fires on `conversation_complete` via the `memory_tier3_curate` hook.
Runs promotion (recall-frequency → frozen), archival of stale entries,
and a frozen snapshot for prefix-cache stability via the bundle's
`LongTermMemoryManager.curate_session`.

Mirrors hermes-agent's curator flow, but as a normal ConversableAgent
subclass dispatched by name through the generic `agent_dispatcher`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from derisk.agent.core.profile import DynConfig, ProfileConfig

from .base import MemoryAgentBase

logger = logging.getLogger(__name__)


class MemoryCurateAgent(MemoryAgentBase):
    """Tier 3: session-end curation agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "MemoryCurateAgent",
            category="agent",
            key="derisk_agent_expand_memory_curate_agent_profile_name",
        ),
        role=DynConfig(
            "Memory Curate Agent",
            category="agent",
            key="derisk_agent_expand_memory_curate_agent_profile_role",
        ),
        goal=DynConfig(
            "At session end, promote high-recall memories, archive stale "
            "ones, and refresh the frozen snapshot.",
            category="agent",
            key="derisk_agent_expand_memory_curate_agent_profile_goal",
        ),
        desc=DynConfig(
            "Built-in memory agent: session-end curation (tier 3).",
            category="agent",
            key="derisk_agent_expand_memory_curate_agent_profile_desc",
        ),
    )

    async def _run_memory_task(
        self, event: Dict[str, Any], bundle: Any, conv_id: str
    ) -> Optional[str]:
        extra = event.get("extra") or {}
        history = extra.get("conversation_history") or []

        await bundle.manager.curate_session(
            conversation_history=history,
            metadata={
                "conv_id": conv_id,
                "agent_name": event.get("agent_name"),
                "app_code": event.get("app_code"),
                "tier": 3,
            },
        )
        return "curated"
