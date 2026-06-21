"""Base class for built-in memory agents.

Memory agents are global singletons registered in `AgentManager`. They
are dispatched by name through the generic `agent_dispatcher` when a
memory hook fires. The hook event is delivered as a JSON string in
`received_message.content`; the agent parses `conv_id` (and any other
payload fields) from there — never from `self.agent_context`, which is
not set for singleton agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

from derisk.agent.core.action.blank_action import BlankAction
from derisk.agent.core.base_agent import ConversableAgent
from derisk.agent.core.profile import ProfileConfig
from derisk.agent.core.types import AgentMessage

logger = logging.getLogger(__name__)


class MemoryAgentBase(ConversableAgent):
    """Base class for memory agents.

    Subclasses provide a `ProfileConfig` and implement
    `_run_memory_task(event, bundle) -> str`. The base class handles:
    * parsing the hook event JSON from `received_message.content`
    * looking up the per-conv memory bundle
    * returning an `AgentMessage` with the task result
    """

    profile: ProfileConfig = ProfileConfig(
        name="MemoryAgentBase",
        role="Memory Agent",
        goal="Coordinate long-term memory operations",
        desc="Built-in memory agent (base).",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_actions([BlankAction])

    # ------------------------------------------------------------------
    # Event parsing / bundle lookup
    # ------------------------------------------------------------------

    def _parse_event(self, received_message: AgentMessage) -> Tuple[Dict[str, Any], str]:
        """Extract the event dict and conv_id from received_message.content.

        The dispatcher serializes the hook event into `content` as JSON.
        Falls back to empty event / empty conv_id on parse failure.
        """
        raw = received_message.content or ""
        if isinstance(raw, dict):
            event = raw
        else:
            try:
                event = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                logger.warning(
                    "[MemoryAgentBase] failed to parse event JSON: %s",
                    raw[:200],
                )
                event = {}
        conv_id = event.get("conv_id") or ""
        return event, conv_id

    def _get_bundle(self, conv_id: str) -> Optional[Any]:
        """Look up the per-conv MemoryIntegrationBundle."""
        if not conv_id:
            return None
        try:
            from derisk.agent.core.memory.hook_dispatcher import get_memory_bundle

            return get_memory_bundle(conv_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[MemoryAgentBase] bundle lookup failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # generate_reply — bypasses the heavy ConversableAgent loop
    # ------------------------------------------------------------------

    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: Any = None,
        reviewer: Any = None,
        rely_messages: Optional[list] = None,
        historical_dialogues: Optional[list] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        **kwargs,
    ) -> AgentMessage:
        """Handle a memory hook event.

        Bypasses the standard ConversableAgent loop (which requires a
        per-conv `agent_context` that singleton memory agents don't have).
        Parses the event, looks up the bundle, and delegates to
        `_run_memory_task`. Failures are swallowed — memory agents must
        never raise into the hook executor.
        """
        event, conv_id = self._parse_event(received_message)
        if not conv_id:
            logger.debug("[MemoryAgent=%s] no conv_id in event; skipping", self.name)
            return self._empty_reply()

        bundle = self._get_bundle(conv_id)
        if bundle is None or getattr(bundle, "manager", None) is None:
            logger.debug(
                "[MemoryAgent=%s] no bundle for conv %s; skipping", self.name, conv_id
            )
            return self._empty_reply()

        try:
            result = await self._run_memory_task(event, bundle, conv_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[MemoryAgent=%s] _run_memory_task failed (conv=%s): %s",
                self.name,
                conv_id,
                e,
            )
            return self._empty_reply()

        return AgentMessage(
            message_id=received_message.message_id,
            content=str(result) if result is not None else "",
            role="assistant",
            current_goal=received_message.current_goal,
            success=True,
        )

    def _empty_reply(self) -> AgentMessage:
        return AgentMessage(content="", role="assistant", success=True)

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    async def _run_memory_task(
        self, event: Dict[str, Any], bundle: Any, conv_id: str
    ) -> Optional[str]:
        """Subclass implements the actual memory work.

        Returns: a short status string (logged, ignored by dispatcher).
        """
        raise NotImplementedError
