# packages/derisk-core/tests/agent/core/v2/test_subagent_interaction_gateway.py
import pytest
from derisk.agent.core.v2.subagent_interaction_gateway import SubAgentInteractionGateway
from derisk.agent.interaction.interaction_protocol import (
    InteractionRequest, InteractionResponse, InteractionType,
)


class FakeParentGateway:
    """Fake parent gateway for testing — records what was delegated."""
    def __init__(self, response_choice="allow_once"):
        self._response_choice = response_choice
        self.last_request = None

    async def send_and_wait(self, request):
        self.last_request = request
        return InteractionResponse(
            request_id=request.request_id,
            choice=self._response_choice,
        )


async def test_sync_mode_delegates_to_parent():
    parent = FakeParentGateway(response_choice="allow_session")
    gw = SubAgentInteractionGateway(parent_gateway=parent, sync=True)
    req = InteractionRequest(
        interaction_type=InteractionType.AUTHORIZE,
        title="Authorize",
        message="Sub-agent authorization request",
        request_id="req-1",
        options=[],
    )
    resp = await gw.send_and_wait(req)
    assert resp.choice == "allow_session"
    assert parent.last_request is req


async def test_async_mode_auto_denies():
    parent = FakeParentGateway()
    gw = SubAgentInteractionGateway(parent_gateway=parent, sync=False)
    req = InteractionRequest(
        interaction_type=InteractionType.AUTHORIZE,
        title="Authorize",
        message="Sub-agent authorization request",
        request_id="req-1",
        options=[],
    )
    resp = await gw.send_and_wait(req)
    assert resp.choice == "deny"
    assert "background" in (resp.cancel_reason or "").lower()
    # Parent was NOT called
    assert parent.last_request is None


async def test_sync_mode_can_deny_via_parent():
    """If parent denies, sub-agent sees the denial."""
    parent = FakeParentGateway(response_choice="deny")
    gw = SubAgentInteractionGateway(parent_gateway=parent, sync=True)
    req = InteractionRequest(
        interaction_type=InteractionType.AUTHORIZE,
        title="Authorize",
        message="Sub-agent authorization request",
        request_id="req-1",
        options=[],
    )
    resp = await gw.send_and_wait(req)
    assert resp.choice == "deny"
