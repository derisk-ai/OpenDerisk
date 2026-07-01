"""SubAgentInteractionGateway — 策略 C (spec §8.6).

Sync sub-agent: ask_user/permission requests bubble up to the parent agent's
InteractionGateway (so the parent's user sees them).
Async sub-agent: requests auto-deny (background agents must not interrupt
the parent's flow).
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from derisk.agent.interaction.interaction_gateway import InteractionGateway
from derisk.agent.interaction.interaction_protocol import (
    InteractionRequest, InteractionResponse,
)

if TYPE_CHECKING:
    pass


class SubAgentInteractionGateway(InteractionGateway):
    def __init__(self, parent_gateway: InteractionGateway, sync: bool):
        # NOTE: do NOT call super().__init__ — we don't want the parent's
        # internal state. We only delegate send_and_wait.
        self._parent = parent_gateway
        self._sync = sync

    async def send_and_wait(self, request: InteractionRequest) -> InteractionResponse:
        if self._sync:
            return await self._parent.send_and_wait(request)
        return InteractionResponse(
            request_id=request.request_id,
            choice="deny",
            cancel_reason="auto-deny for background agent",
        )
