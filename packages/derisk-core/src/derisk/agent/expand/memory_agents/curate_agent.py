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
        # AgentManager 注册时以 `role` 字符串（"Memory Curate Agent"）
        # 作为 key，而 hook_dispatcher 通过 `name`（"MemoryCurateAgent"）
        # 调用 mgr.get(...)。注册别名让两条路径对齐，否则 tier 3 curate
        # 会被 agent_dispatcher 跳过。
        aliases=["MemoryCurateAgent"],
    )

    async def _run_memory_task(
        self, event: Dict[str, Any], bundle: Any, conv_id: str
    ) -> Optional[str]:
        # Cron 路径：cron job 的 message 形如 "curate:{space_slug}"。
        # isolated session 无 bundle，直接走 curate_space 全量整理。
        user_msg = event.get("user_prompt") or event.get("final_answer") or ""
        if isinstance(user_msg, str) and user_msg.startswith("curate:"):
            slug = user_msg.split(":", 1)[1].strip()
            if not slug:
                logger.warning("[MemoryCurateAgent] cron path: empty slug")
                return "curated"
            from derisk.agent.core.memory.longterm_manager import LongTermMemoryManager

            # 从 self 解析 system_app 和可选 llm_client
            system_app = getattr(self, "system_app", None)
            llm_client = None
            try:
                llm_client = getattr(
                    getattr(self, "llm_config", None), "llm_client", None
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                await LongTermMemoryManager.curate_space(
                    space_slug=slug,
                    system_app=system_app,
                    llm_client=llm_client,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[MemoryCurateAgent] cron curate_space slug=%s failed: %s",
                    slug, e,
                )
            return "curated"

        # Hook 路径（conversation_complete）：会话结束轻量 promotion/snapshot。
        if bundle is None or getattr(bundle, "manager", None) is None:
            logger.debug(
                "[MemoryCurateAgent] hook path: no bundle for conv %s; skipping",
                conv_id,
            )
            return "curated"

        extra = event.get("extra") or {}
        history = extra.get("conversation_history") or []

        # 兜底 tier2：短对话不足 every_n_turns 阈值，会话结束时强制
        # 对全部历史 reflect 一次，保证 L0 → L1 抽取链路不被跳过。
        turns = _reconstruct_turns_from_history(history)
        if turns:
            try:
                await bundle.manager.reflect_on_last_n_turns(
                    n=len(turns),
                    turns=turns,
                    metadata={
                        "conv_id": conv_id,
                        "agent_name": event.get("agent_name"),
                        "app_code": event.get("app_code"),
                        "user_id": event.get("user_id"),
                        "user_name": event.get("user_name"),
                        "tier": 2,
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[MemoryCurateAgent] fallback tier2 reflect failed: %s", e
                )

        await bundle.manager.curate_session(
            conversation_history=history,
            metadata={
                "conv_id": conv_id,
                "agent_name": event.get("agent_name"),
                "app_code": event.get("app_code"),
                "user_id": event.get("user_id"),
                "user_name": event.get("user_name"),
                "tier": 3,
            },
        )
        return "curated"


def _reconstruct_turns_from_history(
    history: list,
) -> list:
    """把 flat message list 重构成 [{user, assistant}] 配对。

    history 项期望形如 {"role": "user"|"assistant"|"human"|"ai", "content": ...}。
    连续的 user 后跟一个 assistant 算一轮；user 后无 assistant 则把
    assistant 留空。非 user/assistant 角色（system/tool）跳过。
    """
    turns: list = []
    current: dict = {}
    for msg in history or []:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").lower()
        content = msg.get("content") or ""
        if role in ("user", "human"):
            if current.get("user") is not None:
                turns.append(current)
                current = {}
            current["user"] = content
        elif role in ("assistant", "ai"):
            current["assistant"] = content
            turns.append(current)
            current = {}
    if current.get("user") is not None:
        turns.append(current)
    return turns
