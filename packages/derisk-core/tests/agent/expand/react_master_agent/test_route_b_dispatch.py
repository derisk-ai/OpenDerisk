"""RFC-006 Stage 3:工具执行 Route B 派发单测。

验证:
- ToolDispatcher Route B 端到端:非 BUILTIN executor_id → registry.get → executor.execute(ExecutorCall)。
- ToolAction._execute_tool 对非 BUILTIN entry 走 Route B(dispatch);对 BUILTIN 走 Route A(直调)。
- 无 _tool_dispatcher / 无 snapshot 时 fallback Route A(测试兼容)。
"""

import asyncio
from typing import Any, List

import pytest

from derisk.agent.capabilities import ResourceFacade
from derisk.agent.capabilities.facade import _iter_sub_resources
from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.dispatcher import ToolDispatcher
from derisk.core.interface.resource.executor import (
    Executor,
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)
from derisk.core.interface.resource.tool_entry import (
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)


# --------------------------------------------------------------------------- #
# 伪 Capability executor(非 BUILTIN,记 call)
# --------------------------------------------------------------------------- #
class _RecordingExecutor(Executor):
    def __init__(self, eid="cap:demo"):
        self._id = eid
        self.executed_calls: List[ExecutorCall] = []
        self._status = ExecutorStatus.UNINITIALIZED

    @property
    def executor_id(self):
        return self._id

    @property
    def status(self):
        return self._status

    async def prepare(self):
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        self.executed_calls.append(call)
        return f"executed:{call.tool_name}:{call.args.get('q', '')}"

    async def release(self, reason):
        self._status = ExecutorStatus.RELEASED


# --------------------------------------------------------------------------- #
# dispatcher Route B 端到端
# --------------------------------------------------------------------------- #
async def test_dispatch_route_b_calls_executor_execute():
    """非 BUILTIN executor_id → registry.acquire(触发 prepare)→ dispatch → executor.execute。"""
    facade = ResourceFacade()
    ex = _RecordingExecutor("cap:demo")
    facade.executor_provider["cap:demo"] = ex

    # acquire(模拟 facade _prepare_executors):触发 prepare,executor 入 registry
    await facade.registry.acquire("conv1", ex)

    entry = ToolEntry(
        tool_name="search_things",
        tool=None,  # Route B 不用 tool 句柄
        capability_id="cap:demo",
        executor_id="cap:demo",
        description="demo",
    )
    dispatcher = ToolDispatcher(registry=facade.registry)
    res = await dispatcher.dispatch(
        tool_name="search_things",
        args={"q": "hello"},
        conv_id="conv1",
        entries=[entry],
    )
    assert res.success is True
    assert res.executor_id == "cap:demo"
    assert res.result == "executed:search_things:hello"
    assert len(ex.executed_calls) == 1
    assert ex.executed_calls[0].tool_name == "search_things"
    assert ex.executed_calls[0].args == {"q": "hello"}


async def test_dispatch_route_b_executor_not_acquired_fails():
    """executor 未 acquire 时 registry.get 返 None → dispatch fail(非静默)。"""
    facade = ResourceFacade()
    ex = _RecordingExecutor("cap:ghost")
    facade.executor_provider["cap:ghost"] = ex
    # 故意不 acquire

    entry = ToolEntry(
        tool_name="t", tool=None, capability_id="cap:ghost",
        executor_id="cap:ghost", description="",
    )
    dispatcher = ToolDispatcher(registry=facade.registry)
    res = await dispatcher.dispatch(
        tool_name="t", args={}, conv_id="convX", entries=[entry],
    )
    assert res.success is False
    assert "not acquired" in (res.error or "")


# --------------------------------------------------------------------------- #
# ToolAction._execute_tool 分流:Route B vs Route A vs fallback
# --------------------------------------------------------------------------- #
async def test_execute_tool_route_b_for_non_builtin_entry():
    """agent 带 _tool_dispatcher + _last_snapshot,entry.executor_id 非 BUILTIN → 走 Route B。"""
    from derisk.agent.expand.actions.tool_action import ToolAction

    ex = _RecordingExecutor("cap:demo")
    facade = ResourceFacade()
    facade.executor_provider["cap:demo"] = ex
    await facade.registry.acquire("conv1", ex)

    entry = ToolEntry(
        tool_name="search_things", tool=None, capability_id="cap:demo",
        executor_id="cap:demo", description="",
    )

    class _Snap:
        def all_tools(self):
            return (entry,)

    class _FakeAgent:
        _tool_dispatcher = ToolDispatcher(registry=facade.registry)
        _last_snapshot = _Snap()

        class _Ctx:
            conv_id = "conv1"
            agent_app_code = "a1"
            conv_session_id = "s1"
            env_context = {}

        agent_context = _Ctx()

    # 造一个极简 tool_info(name 必须匹配 entry.tool_name)。Route B 不调它的 execute。
    class _ToolInfo:
        name = "search_things"
        is_async = False
        args = {"q": None}

    action = ToolAction()
    result = await action._execute_tool(
        tool_info=_ToolInfo(), args={"q": "hi"}, agent=_FakeAgent()
    )
    assert result["success"] is True
    assert "executed:search_things:hi" in result["content"]
    assert len(ex.executed_calls) == 1


async def test_execute_tool_route_a_for_builtin_entry():
    """BUILTIN executor_id → 走 Route A 现有直调(tool_info.execute),不经 dispatcher。"""
    from derisk.agent.expand.actions.tool_action import ToolAction

    called = {"n": 0}

    class _ToolInfo:
        name = "builtin_tool"
        is_async = False
        args = {"text": None}

        def execute(self, **kwargs):
            called["n"] += 1
            return f"builtin-ran:{kwargs.get('text', '')}"

    entry = ToolEntry(
        tool_name="builtin_tool",
        tool=_ToolInfo(),
        capability_id="agent:builtin",
        executor_id=BUILTIN_EXECUTOR_ID,
        description="",
    )

    class _Snap:
        def all_tools(self):
            return (entry,)

    class _FakeAgent:
        _tool_dispatcher = ToolDispatcher(registry=ResourceFacade().registry)
        _last_snapshot = _Snap()

        class _Ctx:
            conv_id = "conv1"
            agent_app_code = "a1"
            conv_session_id = "s1"
            env_context = {}

        agent_context = _Ctx()

    action = ToolAction()
    result = await action._execute_tool(
        tool_info=_ToolInfo(), args={"text": "x"}, agent=_FakeAgent()
    )
    assert result["success"] is True
    assert "builtin-ran:x" in result["content"]
    assert called["n"] == 1  # 走 Route A 直调了一次


async def test_execute_tool_fallback_route_a_when_no_dispatcher():
    """agent 无 _tool_dispatcher(或无 snapshot)→ fallback Route A 直调(测试/存量兼容)。"""
    from derisk.agent.expand.actions.tool_action import ToolAction

    called = {"n": 0}

    class _ToolInfo:
        name = "t"
        is_async = False
        args = {"x": None}

        def execute(self, **kwargs):
            called["n"] += 1
            return "ok"

    class _FakeAgent:
        _tool_dispatcher = None  # 无 dispatcher
        _last_snapshot = None

        class _Ctx:
            conv_id = "conv1"
            agent_app_code = "a1"
            conv_session_id = "s1"
            env_context = {}

        agent_context = _Ctx()

    action = ToolAction()
    result = await action._execute_tool(
        tool_info=_ToolInfo(), args={"x": 1}, agent=_FakeAgent()
    )
    assert result["success"] is True
    assert called["n"] == 1