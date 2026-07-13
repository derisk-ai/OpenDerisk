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

# =========================================================================== #
# RFC-006 Stage 7: MCPCapability 自管理(对象模型统一)
# =========================================================================== #
def test_mcp_capability_from_legacy_declares_tools():
    from derisk_serve.agent.capabilities.mcp import MCPCapability
    legacy = _make_legacy_pack([_make_tool("s1"), _make_tool("s2")])
    cap = MCPCapability.from_legacy(legacy)
    contribs = cap.declare()
    assert len(contribs) == 2
    names = {c.content.tool_name for c in contribs}
    assert names == {"s1", "s2"}


async def test_mcp_capability_register_and_facade_flip():
    """真实 ToolPack(含 FunctionTool)→ facade 翻成 MCPCapability(_is_toolpack_legacy isinstance 命中)。"""
    from derisk.agent.capabilities.facade import ResourceFacade, _CapabilityDeclareAdapter
    from derisk_serve.agent.capabilities.mcp import register_capability
    from derisk.agent.resource import FunctionTool, ToolPack

    def _fn(**k):
        return "ok"

    _fn.__doc__ = "d"
    tool = FunctionTool(name="mcp_x", func=_fn, description="d")
    pack = ToolPack([tool])

    facade = ResourceFacade()
    register_capability(facade)
    assert "tool" in facade._capability_factories
    wrapped = facade._to_resource_protocol(pack)
    assert isinstance(wrapped, _CapabilityDeclareAdapter)
    assert wrapped.capability_id.startswith("mcp")
    assert len(wrapped.declare()) == 1


# =========================================================================== #
# RFC-006 Stage 8: MCPCapability prepare 自管 preload(连 server + 重建工具)
# =========================================================================== #
async def test_mcp_capability_prepare_loads_tools_from_server(monkeypatch):
    """prepare 调 get_mcp_tool_list，逐工具用 FunctionTool 重建，declare 出 ToolEntry。"""
    from derisk_serve.agent.capabilities.mcp import MCPCapability
    fake_tool = SimpleNamespace(name="mcp_sum", description="sum", inputSchema={"properties": {"a": {"type": "number", "description": "x"}}, "required": ["a"]})
    fake_result = SimpleNamespace(tools=[fake_tool])

    async def _fake_get(mcp_name, server, **kw):
        return fake_result

    monkeypatch.setattr(
        "derisk_serve.agent.capabilities.mcp.capability.get_mcp_tool_list", _fake_get, raising=False
    )
    # mcp_utils 在 prepare 内 import,monkeypatch 顶层 import 名需 patch 真模块
    import derisk_serve.agent.capabilities.mcp.capability as mcp_mod, sys
    # prepare 内 from ...mcp_utils import get_mcp_tool_list —— 用 sys.modules 兜底
    real_utils = sys.modules.get("derisk_serve.agent.resource.tool.mcp_utils")
    import derisk_serve.agent.resource.tool.mcp_utils as utils
    monkeypatch.setattr(utils, "get_mcp_tool_list", _fake_get)

    cap = MCPCapability(
        mcp_name="demo", mcp_servers="http://x/sse", headers={}, tool_id="t1", timeout=10
    )
    await cap.prepare()
    assert cap.capability_id == "mcp:demo"
    contribs = cap.declare()
    assert len(contribs) == 1
    assert contribs[0].content.tool_name == "mcp_sum"
    assert contribs[0].content.executor_id == BUILTIN_EXECUTOR_ID


async def test_mcp_capability_prepare_no_servers_ready():
    from derisk_serve.agent.capabilities.mcp import MCPCapability
    cap = MCPCapability(mcp_name="x", mcp_servers=None)
    await cap.prepare()
    assert cap._status.value == "ready"
    assert cap.declare() == []


async def test_mcp_capability_prepare_degrades_on_failure(monkeypatch):
    """get_mcp_tool_list 抛异常 → 降级(空工具列表,不崩,ready)。"""
    from derisk_serve.agent.capabilities.mcp import MCPCapability
    import derisk_serve.agent.resource.tool.mcp_utils as utils

    async def _boom(*a, **kw):
        raise RuntimeError("server down")

    monkeypatch.setattr(utils, "get_mcp_tool_list", _boom)
    cap = MCPCapability(mcp_name="demo", mcp_servers="http://x/sse")
    await cap.prepare()
    assert cap._status.value == "ready"
    assert cap.declare() == []


async def test_mcp_capability_from_legacy_reuses_loaded_tools():
    """from_legacy 复用旧实例已 preload 的工具(过渡期,_loaded=True)。"""
    from derisk_serve.agent.capabilities.mcp import MCPCapability
    fake_tool = SimpleNamespace(name="t", description="d")
    legacy = SimpleNamespace(
        name="demo", _mcp_servers="http://x/sse", _headers={}, _allow_tools=None,
        _tool_id="t1", _timeout=60, _source="faas", _overwrite_same_tool=True,
        _loaded=True, sub_resources=[fake_tool],
    )
    cap = MCPCapability.from_legacy(legacy)
    assert cap.capability_id == "mcp:demo"
    assert cap._tools == [fake_tool]
    # prepare 命中已 loaded → 不重新拉
    import derisk_serve.agent.resource.tool.mcp_utils as utils
    async def _should_not_call(*a, **kw):
        raise AssertionError("should not call get_mcp_tool_list when tools loaded")
    utils.get_mcp_tool_list = _should_not_call  # 若误调会抛
    await cap.prepare()
    assert cap._status.value == "ready"


# =========================================================================== #
# RFC-006 Phase C: facade.assemble 读 agent.capability_pack(MCP 走纯新协议)
# =========================================================================== #
async def test_facade_assemble_reads_capability_pack_for_mcp(monkeypatch):
    """agent.capability_pack 含 MCPCapability(已 preload 工具)→ facade.assemble
    从 capability_pack 读,declare 出 MCP 工具 ToolEntry(走纯新协议,不翻旧 ToolPack)。"""
    from derisk.agent.capabilities import ResourceFacade
    from derisk.agent.capabilities.facade import _CapabilityDeclareAdapter
    from derisk_serve.agent.capabilities.mcp import MCPCapability
    from derisk.agent.resource import FunctionTool
    from derisk.core.interface.resource.capability import CapabilityPack

    # 造一个已 prepare 的 MCPCapability(自带工具,免 server)
    def _fn(**k):
        return "ok"
    _fn.__doc__ = "d"
    cap = MCPCapability(mcp_name="demo", mcp_servers="http://x/sse")
    cap._tools = [FunctionTool(name="mcp_loaded", func=_fn, description="d")]
    from derisk.core.interface.resource.executor import ExecutorStatus
    cap._status = ExecutorStatus.READY

    pack = CapabilityPack([cap])

    class _FakeAgent:
        capability_pack = pack
        resource = None

    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", agent=_FakeAgent(),
        identity="id", control_block="ctl",
    )
    # MCP 工具进 snapshot tools
    tool_names = {getattr(c.content, "tool_name", None) for c in snap.tools}
    assert "mcp_loaded" in tool_names
