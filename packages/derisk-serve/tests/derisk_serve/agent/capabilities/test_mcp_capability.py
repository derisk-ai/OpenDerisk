"""RFC-005 Step C: mcp capability(工具聚合)迁移测试。

MCP/ToolPack 子类:declare 产工具列表 TOOLS(每个工具一个 ToolEntry)。
"""

from types import SimpleNamespace

from derisk.core.interface.resource.bundle import Slot
from derisk.core.interface.resource.tool_entry import BUILTIN_EXECUTOR_ID
from derisk_serve.agent.capabilities.mcp import MCPCapabilityResource


def _make_tool(name="mcp_tool_1", description="an MCP tool"):
    return SimpleNamespace(name=name, description=description)


def _make_legacy_pack(tools):
    return SimpleNamespace(sub_resources=tools)


def test_mcp_declares_tools_from_legacy_pack():
    tools = [_make_tool("t1"), _make_tool("t2")]
    legacy = _make_legacy_pack(tools)
    res = MCPCapabilityResource(legacy_instance=legacy)
    contribs = res.declare_tools()
    assert len(contribs) == 2
    for c in contribs:
        assert c.slot == Slot.TOOLS
        assert c.capability_id == "mcp"
        entry = c.content
        assert entry.capability_id == "mcp"
        assert entry.executor_id == BUILTIN_EXECUTOR_ID


def test_mcp_declares_from_explicit_tools():
    tools = [_make_tool("s1")]
    res = MCPCapabilityResource(tools=tools)
    contribs = res.declare_tools()
    assert len(contribs) == 1
    assert contribs[0].content.tool_name == "s1"


def test_mcp_empty_when_no_tools():
    res = MCPCapabilityResource()
    assert res.declare_tools() == []


def test_mcp_empty_pack():
    """无 sub_resources 的 pack → 空 declare。"""
    legacy = SimpleNamespace(sub_resources=None)
    res = MCPCapabilityResource(legacy_instance=legacy)
    assert res.declare_tools() == []


def test_facade_wraps_legacy_toolpack():
    from derisk.agent.capabilities.facade import ResourceFacade
    facade = ResourceFacade()
    from derisk_serve.agent.capabilities.mcp import register_wrappers
    register_wrappers(facade)
    facade.register_legacy_wrapper(object, lambda x: MCPCapabilityResource(legacy_instance=x))
    legacy = _make_legacy_pack([_make_tool("t1")])
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, MCPCapabilityResource)
    contribs = wrapped.declare_tools()
    assert len(contribs) == 1
    assert contribs[0].content.tool_name == "t1"