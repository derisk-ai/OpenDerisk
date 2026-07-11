"""RFC-005 S18 ToolDispatcher 协议层派发单测。

覆盖:
- builtin 工具(executor_id=agent:builtin)→ builtin_executor 回调
- 资源工具(executor_id=真实 Executor)→ registry 取 executor.execute
- 未找到 tool_name → 失败
- builtin 但无 builtin_executor 注册 → 失败
- executor 未 acquire → 失败
- 旧式 Contribution(content=BaseTool)兼容查
- build_index 索引
"""

import pytest

from derisk.core.interface.resource.executor import Executor, ExecutorCall, ExecutorRegistry, ExecutorStatus, InMemoryExecutorRegistry, ReleaseReason
from derisk.core.interface.resource.dispatcher import ToolDispatchResult, ToolDispatcher
from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot
from derisk.core.interface.resource.tool_entry import BUILTIN_EXECUTOR_ID, ToolEntry
# 测试 Executor
# --------------------------------------------------------------------------- #
class _MockExecutor(Executor):
    def __init__(self, eid: str):
        self._id = eid
        self.executed: list = []
        self.status = ExecutorStatus.READY

    @property
    def executor_id(self) -> str:
        return self._id

    async def prepare(self) -> None:
        pass

    async def execute(self, call: ExecutorCall):
        self.executed.append(call.tool_name)
        return f"exec-result:{call.tool_name}"

    async def release(self, reason: ReleaseReason) -> None:
        pass


# --------------------------------------------------------------------------- #
# builtin 工具路由
# --------------------------------------------------------------------------- #
async def test_builtin_tool_routed_to_callback():
    """executor_id=agent:builtin → builtin_executor 回调。"""

    async def builtin_cb(tool_name, tool, args):
        assert tool_name == "spawn_agent_task"
        return f"builtin-{tool_name}"

    reg = InMemoryExecutorRegistry()
    dispatcher = ToolDispatcher(reg, builtin_executor=builtin_cb)
    entries = [
        ToolEntry(
            tool_name="spawn_agent_task",
            tool=object(),
            capability_id="agent:builtin",
            executor_id=BUILTIN_EXECUTOR_ID,
        )
    ]
    res = await dispatcher.dispatch(
        tool_name="spawn_agent_task", args={}, conv_id="c1", entries=entries,
    )
    assert res.success is True
    assert res.result == "builtin-spawn_agent_task"
    assert res.executor_id == BUILTIN_EXECUTOR_ID


# --------------------------------------------------------------------------- #
# 资源工具路由
# --------------------------------------------------------------------------- #
async def test_resource_tool_routed_to_executor():
    """executor_id 指向真实 Executor → registry 取 executor.execute。"""
    sandbox = _MockExecutor("sandbox")
    reg = InMemoryExecutorRegistry()
    await reg.acquire("c1", sandbox)  # 预先 acquire
    dispatcher = ToolDispatcher(reg)
    entries = [
        ToolEntry(
            tool_name="run_python",
            tool=object(),
            capability_id="sandbox",
            executor_id="sandbox",
        )
    ]
    res = await dispatcher.dispatch(
        tool_name="run_python", args={"code": "print(1)"}, conv_id="c1",
        entries=entries,
    )
    assert res.success is True
    assert res.result == "exec-result:run_python"
    assert sandbox.executed == ["run_python"]


async def test_builtin_executor_id_none_routes_to_builtin():
    """executor_id 缺省(旧式 builtin)也走 builtin 回调。    """
    called = []

    async def cb(name, tool, args):
        called.append(name)
        return "ok"

    reg = InMemoryExecutorRegistry()
    dispatcher = ToolDispatcher(reg, builtin_executor=cb)
    entries = [
        ToolEntry(
            tool_name="read_history_chapter", tool=object(),
            capability_id="agent:builtin", executor_id=None,
        )
    ]
    res = await dispatcher.dispatch(
        tool_name="read_history_chapter", args={}, conv_id="c1", entries=entries,
    )
    assert res.success is True
    assert called == ["read_history_chapter"]


# --------------------------------------------------------------------------- #
# 未找到 / 未注册 / 未 acquire
# --------------------------------------------------------------------------- #
async def test_tool_not_found():
    reg = InMemoryExecutorRegistry()
    dispatcher = ToolDispatcher(reg, builtin_executor=lambda *a: None)
    res = await dispatcher.dispatch(
        tool_name="nope", args={}, conv_id="c1", entries=[],
    )
    assert res.success is False
    assert "not found" in res.error


async def test_builtin_but_no_callback_registered():
    """builtin 工具但未注册 builtin_executor → 失败。
    """
    reg = InMemoryExecutorRegistry()
    dispatcher = ToolDispatcher(reg)  # 无 builtin_executor
    entries = [
        ToolEntry(
            tool_name="spawn_agent_task", tool=object(),
            capability_id="agent:builtin", executor_id=BUILTIN_EXECUTOR_ID,
        )
    ]
    res = await dispatcher.dispatch(
        tool_name="spawn_agent_task", args={}, conv_id="c1", entries=entries,
    )
    assert res.success is False
    assert "builtin" in res.error


async def test_resource_executor_not_acquired():
    """资源工具但 executor 未 acquire → 失败。"""
    reg = InMemoryExecutorRegistry()
    dispatcher = ToolDispatcher(reg)
    entries = [
        ToolEntry(
            tool_name="run_python", tool=object(),
            capability_id="sandbox", executor_id="sandbox",
        )
    ]
    res = await dispatcher.dispatch(
        tool_name="run_python", args={}, conv_id="c1", entries=entries,
    )
    assert res.success is False
    assert "not acquired" in res.error
    assert "sandbox" in res.error


# --------------------------------------------------------------------------- #
# 旧式 Contribution(content=BaseTool)兼容
# --------------------------------------------------------------------------- #
async def test_legacy_contribution_content_as_tool():
    """旧式 Contribution(content 是 BaseTool)能被按 .name 找到并 builtin 执行。
    """
    from derisk.agent.resource import FunctionTool

    def _fn(**kw):
        return "fn-result"

    _fn.__doc__ = "test tool"
    tool = FunctionTool(name="legacy_tool", func=_fn, description="test tool")
    received_tool = []

    async def cb(name, t, args):
        # 派发器应把原 BaseTool 透传给 builtin_executor
        received_tool.append(t)
        return f"cb-{name}"

    reg = InMemoryExecutorRegistry()
    dispatcher = ToolDispatcher(reg, builtin_executor=cb)
    # 旧式 Contribution:content=BaseTool
    contrib = Contribution(
        "legacy", Slot.TOOLS, tool,
        lifetime=Lifetime.CONFIG_STATIC, cache_scope=CacheScope.NONE,
    )
    res = await dispatcher.dispatch(
        tool_name="legacy_tool", args={}, conv_id="c1", entries=[contrib],
    )
    assert res.success is True
    assert res.result == "cb-legacy_tool"
    assert received_tool == [tool]  # 原 BaseTool 透传给 builtin_executor


# --------------------------------------------------------------------------- #
# build_index
# --------------------------------------------------------------------------- #
def test_build_index():
    entries = [
        ToolEntry("a", object(), "c1"),
        ToolEntry("b", object(), "c2", executor_id="sandbox"),
    ]
    idx = ToolDispatcher.build_index(entries)
    assert set(idx.keys()) == {"a", "b"}
    assert idx["a"].tool_name == "a"
    assert idx["b"].executor_id == "sandbox"
