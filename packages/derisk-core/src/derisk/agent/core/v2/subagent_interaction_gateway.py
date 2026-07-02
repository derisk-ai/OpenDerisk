"""SubAgentInteractionGateway — 策略 C (spec §8.6).

Sync sub-agent: ask_user/permission requests bubble up to the parent agent's
InteractionGateway (so the parent's user sees them).
Async sub-agent: requests auto-deny (background agents must not interrupt
the parent's flow).
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from typing import Any, Dict, Optional
from derisk.agent.interaction.interaction_gateway import InteractionGateway
from derisk.agent.interaction.interaction_protocol import (
    InteractionRequest, InteractionResponse, InteractionType, InteractionOption,
    InteractionPriority,
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

    async def request_tool_permission(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str] = None,
        timeout: int = 120,
    ) -> InteractionResponse:
        """PermissionGate adapter entry point.

        Builds an authorization request and routes it through `send_and_wait`,
        so sync sub-agents delegate to the parent gateway and async sub-agents
        auto-deny without interrupting the parent.
        """
        request = InteractionRequest(
            interaction_type=InteractionType.AUTHORIZE,
            priority=InteractionPriority.CRITICAL,
            title=f"需要授权: {tool_name}",
            message=f"Sub-agent requests permission to use `{tool_name}`.",
            tool_name=tool_name,
            options=[
                InteractionOption(label="允许（本次）", value="allow_once", default=True),
                InteractionOption(label="允许（本次会话）", value="allow_session"),
                InteractionOption(label="拒绝", value="deny"),
            ],
            timeout=timeout,
            context={"tool_args": tool_args, "reason": reason},
        )
        return await self.send_and_wait(request)
