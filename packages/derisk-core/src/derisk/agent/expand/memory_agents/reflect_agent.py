"""Memory Reflect Agent — tier 2 cross-turn reflection.

Fires every N turns (default 10) via the `memory_tier2_reflect` hook.
Reviews recent conversation turns and consolidates user-profile /
preference / decision memories via the bundle's
`LongTermMemoryManager.reflect_on_last_n_turns`.

This mirrors hermes-agent's `_spawn_background_review`, which forks an
AIAgent to run `_MEMORY_REVIEW_PROMPT`. Here the agent is a normal
ConversableAgent subclass dispatched by name through the generic
`agent_dispatcher`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from derisk.agent.core.profile import DynConfig, ProfileConfig

from .base import MemoryAgentBase

logger = logging.getLogger(__name__)


class MemoryReflectAgent(MemoryAgentBase):
    """Tier 2: every-N-turns reflection agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "MemoryReflectAgent",
            category="agent",
            key="derisk_agent_expand_memory_reflect_agent_profile_name",
        ),
        role=DynConfig(
            "Memory Reflect Agent",
            category="agent",
            key="derisk_agent_expand_memory_reflect_agent_profile_role",
        ),
        goal=DynConfig(
            "Review recent turns and consolidate user profile, preferences, "
            "and decisions into long-term memory.",
            category="agent",
            key="derisk_agent_expand_memory_reflect_agent_profile_goal",
        ),
        desc=DynConfig(
            "Built-in memory agent: cross-turn reflection (tier 2).",
            category="agent",
            key="derisk_agent_expand_memory_reflect_agent_profile_desc",
        ),
        # 见 curate_agent.py 同款注释：让 mgr.get("MemoryReflectAgent")
        # 能解析到 role="Memory Reflect Agent"。
        aliases=["MemoryReflectAgent"],
    )

    async def _run_memory_task(
        self, event: Dict[str, Any], bundle: Any, conv_id: str
    ) -> Optional[str]:
        extra = event.get("extra") or {}
        turns = extra.get("turns")
        n = extra.get("n") or getattr(bundle.config, "reflection_interval", 10) or 10

        await bundle.manager.reflect_on_last_n_turns(
            n=n,
            turns=turns,
            metadata={
                "conv_id": conv_id,
                "agent_name": event.get("agent_name"),
                "app_code": event.get("app_code"),
                "round": event.get("round"),
                "tier": 2,
            },
        )
        return f"reflected n={n}"
