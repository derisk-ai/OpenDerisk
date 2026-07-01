import pytest
import tempfile
import os
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache
from derisk.agent.core.v2.permission_gate import (
    PermissionGate, PermissionDecision, PermissionCheckResult,
)
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction
from derisk.agent.tools.base import ToolBase
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import ToolResult


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


@pytest.fixture
def stream(store):
    return EventStream(store)


class _AllowTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    async def check_permissions(self, input, context=None):
        return PermissionCheckResult(decision="allow", reason="tool says allow")


class _DenyTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    async def check_permissions(self, input, context=None):
        return PermissionCheckResult(decision="deny", reason="tool says deny")


class _AskTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    async def check_permissions(self, input, context=None):
        return PermissionCheckResult(decision="ask", reason="tool says ask")


class _NoOpinionTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    # no check_permissions override -> default returns None


def _gate(store, stream, tool=None, ruleset=None):
    return PermissionGate(
        state_store=store, event_stream=stream,
        interaction_adapter=None,
        session_cache=SessionPermissionCache(),
        ruleset=ruleset, mode=PermissionMode.DEFAULT,
        step_id="step-1", conv_id="conv-1", agent_id="agent-1",
        tool=tool,
    )


async def test_tool_check_permissions_allow_short_circuits(store, stream):
    """Level 4: tool says allow -> ALLOW without asking."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, tool=_AllowTool(), ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW
    assert "tool says allow" in gate.last_result.reason


async def test_tool_check_permissions_deny_short_circuits(store, stream):
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, tool=_DenyTool(), ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_tool_check_permissions_ask_falls_through_to_level_5(store, stream):
    """If tool says ask, Level 5 (InteractionRequest) handles it."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ASK)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice="allow_once")
    gate = _gate(store, stream, tool=_AskTool(), ruleset=ruleset)
    gate._adapter = FakeAdapter()
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert len(events) == 1
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_tool_check_permissions_none_falls_through(store, stream):
    """Default check_permissions returns None -> fall through to ruleset/ask."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, tool=_NoOpinionTool(), ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW
    assert "ruleset" in gate.last_result.reason


async def test_no_tool_passed_skips_level_4(store, stream):
    """When no tool is provided (default), Level 4 is skipped -- backwards compat with P1."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, tool=None, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW
