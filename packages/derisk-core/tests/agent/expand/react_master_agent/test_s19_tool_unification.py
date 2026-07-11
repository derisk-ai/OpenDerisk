"""RFC-005 S19 工具执行面与声明面同源验证。

验证 ToolAction.run 的工具句柄查找(经 agent.resolve_tool_entry)与 function_calling_params
(经 snapshot.all_tools)取自同一 snapshot,消除多 dict 两源不一致。
"""

from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot
from derisk.core.interface.resource.tool_entry import BUILTIN_EXECUTOR_ID, ToolEntry
from derisk.agent.capabilities.facade import ResourceFacade


class _FakeSandboxClient:
    provider = staticmethod(lambda: "local")
    skill_dir = "/s"


class _FakeAgent:
    """模拟 react_master_agent 的关键面:resolve_tool_entry + _last_snapshot。"""

    def __init__(self, snapshot):
        self._last_snapshot = snapshot

    def resolve_tool_entry(self, tool_name: str):
        snap = getattr(self, "_last_snapshot", None)
        if snap is None:
            return None
        from derisk.core.interface.resource.dispatcher import ToolDispatcher

        idx = ToolDispatcher.build_index(snap.all_tools())
        entry = idx.get(tool_name)
        if entry is None:
            return None
        return getattr(entry, "tool", None) or getattr(entry, "content", None)


async def _make_snapshot_with_tools():
    from derisk.agent.resource import FunctionTool

    def _fn(**kw):
        return "ok"

    spawn = FunctionTool(name="spawn_agent_task", func=_fn, description="spawn")
    run_py = FunctionTool(name="run_python", func=_fn, description="run python")

    facade = ResourceFacade()
    return await facade.assemble(
        agent_id="canvas-agent", conv_id="c1",
        identity="id", control_block="ctl",
        builtin_tools={"spawn_agent_task": spawn, "run_python": run_py},
    )


# --------------------------------------------------------------------------- #
# resolve_tool_entry 与 function_calling_params 同源
# --------------------------------------------------------------------------- #
async def test_resolve_tool_entry_finds_builtin_tools():
    """执行面 resolve_tool_entry 能查到声明面 builtin tools。"""
    snap = await _make_snapshot_with_tools()
    agent = _FakeAgent(snap)
    assert agent.resolve_tool_entry("spawn_agent_task") is not None
    assert agent.resolve_tool_entry("run_python") is not None


async def test_resolve_and_declare_share_same_handle():
    """声明面(snapshot.all_tools)与执行面(resolve_tool_entry)返回同一句柄。"""
    snap = await _make_snapshot_with_tools()
    agent = _FakeAgent(snap)

    # 声明面:function_calling_params 会用 snapshot.all_tools() 转的句柄
    declared_handles = {}
    for entry in snap.all_tools():
        handle = getattr(entry, "tool", None) or getattr(entry, "content", None)
        name = getattr(entry, "tool_name", None) or getattr(handle, "name", None)
        declared_handles[name] = handle

    # 执行面:resolve_tool_entry 返回的句柄
    for name in ("spawn_agent_task", "run_python"):
        resolved = agent.resolve_tool_entry(name)
        assert resolved is declared_handles[name]  # 同一对象


async def test_resolve_unknown_returns_none():
    snap = await _make_snapshot_with_tools()
    agent = _FakeAgent(snap)
    assert agent.resolve_tool_entry("nonexistent_tool") is None


async def test_resolve_without_snapshot_returns_none():
    agent = _FakeAgent(None)
    assert agent.resolve_tool_entry("spawn_agent_task") is None


async def test_builtin_tools_marked_agent_builtin():
    """builtin 工具的 ToolEntry.executor_id==agent:builtin(派发器据此走 builtin 回调)。"""
    snap = await _make_snapshot_with_tools()
    for entry in snap.builtin_tools:
        assert entry.executor_id == BUILTIN_EXECUTOR_ID
        assert entry.capability_id == "agent:builtin"
