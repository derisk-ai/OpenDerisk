"""RFC-005 §3.4 Executor 协议契约单测。

覆盖:
- AC-4  prepare 按 requires 拓扑并行;沙箱先于依赖它的 tool 就绪
-       循环依赖检测
- 引用计数:首次 acquire 触发 prepare;归零触发 release;多 capability 共享同一 executor
"""

import pytest

from derisk.core.interface.resource.executor import Executor, ExecutorCall, ExecutorRegistry, ExecutorStatus, InMemoryExecutorRegistry, ReleaseReason, topological_prepare
# 测试用 Executor:记录 prepare/release 时序
# --------------------------------------------------------------------------- #
class _RecordingExecutor(Executor):
    def __init__(self, eid: str, *, fail_prepare: bool = False, sleep: float = 0.0):
        self._id = eid
        self._fail = fail_prepare
        self._sleep = sleep
        self.prepare_calls = 0
        self.release_calls: list = []  # 记录 release 时的全局时序号
        self._order_log = None
        self.status = ExecutorStatus.UNINITIALIZED

    @property
    def executor_id(self) -> str:
        return self._id

    async def prepare(self) -> None:
        import asyncio

        self.prepare_calls += 1
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._fail:
            self.status = ExecutorStatus.FAILED
            raise RuntimeError(f"prepare failed: {self._id}")
        self.status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall):
        return f"exec:{self._id}"

    async def release(self, reason: ReleaseReason) -> None:
        self.release_calls.append(reason)
        self.status = ExecutorStatus.RELEASED


# --------------------------------------------------------------------------- #
# AC-4 拓扑:沙箱先于依赖它的 executor 就绪
# --------------------------------------------------------------------------- #
async def test_topological_prepare_orders_dependencies_first():
    """沙箱(executor: sandbox)先于依赖它的工具 executors 就绪。"""
    sandbox = _RecordingExecutor("sandbox")
    py_tool = _RecordingExecutor("py_tool")     # requires sandbox
    file_tool = _RecordingExecutor("file_tool")  # requires sandbox

    errors, order = await topological_prepare(
        [sandbox, py_tool, file_tool],
        requires_map={"py_tool": ["sandbox"], "file_tool": ["sandbox"]},
    )

    assert errors == {}
    assert order[0] == "sandbox"  # 被依赖者最先
    assert set(order[1:]) == {"py_tool", "file_tool"}


async def test_topological_prepare_parallel_within_same_depth():
    """同一深度(无相互依赖)的 executor 并行 prepare。"""
    import time

    a = _RecordingExecutor("a", sleep=0.1)
    b = _RecordingExecutor("b", sleep=0.1)
    start = time.monotonic()
    errors, order = await topological_prepare([a, b])
    elapsed = time.monotonic() - start
    # 并行:两个 0.1s 应在 ~0.1s 内完成,而非串行 0.2s
    assert errors == {}
    assert elapsed < 0.18
    assert a.prepare_calls == 1
    assert b.prepare_calls == 1


async def test_topological_prepare_is_idempotent_safe():
    """prepare 各 executor 只调一次。"""
    ex = _RecordingExecutor("ex")
    _, _ = await topological_prepare([ex])
    assert ex.prepare_calls == 1


async def test_failed_executor_does_not_block_independents():
    """prepare 失败的 executor 不阻塞不依赖它的 executor。"""
    failing = _RecordingExecutor("failing", fail_prepare=True)
    independent = _RecordingExecutor("independent")

    errors, order = await topological_prepare([failing, independent])

    assert "failing" in errors
    assert "independent" not in errors
    assert "independent" in order
    assert "failing" not in order


async def test_failed_executor_blocks_its_dependents():
    """依赖失败 executor 的也被标记失败(不卡死)。"""
    failing = _RecordingExecutor("db", fail_prepare=True)
    dependent = _RecordingExecutor("query_tool")  # requires db

    errors, order = await topological_prepare(
        [failing, dependent],
        requires_map={"query_tool": ["db"]},
    )

    assert "db" in errors
    assert "query_tool" in errors  # 因依赖失败而阻塞
    assert order == []


async def test_cycle_detection_raises():
    """循环依赖被检测并抛 ValueError(否则 topological_prepare 死循环)。"""
    a = _RecordingExecutor("a")
    b = _RecordingExecutor("b")
    # a 依赖 b,b 依赖 a → 环
    with pytest.raises(ValueError, match="cycle"):
        await topological_prepare(
            [a, b],
            requires_map={"a": ["b"], "b": ["a"]},
        )


async def test_external_dependency_not_in_set_is_ignored():
    """被依赖项不在集合中(外部已就绪)→ 不阻塞,正常 prepare。"""
    ex = _RecordingExecutor("ex")
    errors, order = await topological_prepare(
        [ex],
        requires_map={"ex": ["external_ready"]},  # external_ready 不在集合
    )
    assert errors == {}
    assert order == ["ex"]


# --------------------------------------------------------------------------- #
# 引用计数 registry
# --------------------------------------------------------------------------- #
async def test_acquire_first_triggers_prepare():
    """首次 acquire 触发 prepare;再次 acquire 不重复 prepare。"""
    reg = InMemoryExecutorRegistry()
    ex = _RecordingExecutor("sandbox")

    await reg.acquire("conv1", ex)
    assert ex.prepare_calls == 1

    await reg.acquire("conv1", ex)  # 同会话再次 acquire
    assert ex.prepare_calls == 1  # 不重复


async def test_release_single_decrements_then_releases_on_zero():
    """单条 release 逐 capability 减计数;归零才 release(共享 executor 不被连累)。"""
    reg = InMemoryExecutorRegistry()
    sandbox = _RecordingExecutor("sandbox")

    # 两个 capability 共享同一 sandbox → 计数 2
    await reg.acquire("conv1", sandbox)
    await reg.acquire("conv1", sandbox)

    # 第一个 capability 释放:计数 1,不 release
    await reg.release("conv1", sandbox.executor_id, ReleaseReason.SESSION_END)
    assert sandbox.release_calls == []
    assert reg.get("conv1", "sandbox") is sandbox  # 仍持有

    # 第二个释放:计数归零,release
    await reg.release("conv1", sandbox.executor_id, ReleaseReason.AGENT_END)
    assert sandbox.release_calls == [ReleaseReason.AGENT_END]
    assert reg.get("conv1", "sandbox") is None


async def test_release_unknown_executor_is_noop():
    reg = InMemoryExecutorRegistry()
    # 不抛异常
    await reg.release("conv1", "no_such", ReleaseReason.SESSION_END)


async def test_release_session_releases_all_session_refs():
    """release_session 释放该会话所有引用,归零者 release。"""
    reg = InMemoryExecutorRegistry()
    sandbox = _RecordingExecutor("sandbox")
    db = _RecordingExecutor("db")

    # conv1 acquire sandbox 两次(模拟多 capability 共享) + db 一次
    await reg.acquire("conv1", sandbox)
    await reg.acquire("conv1", sandbox)
    await reg.acquire("conv1", db)

    await reg.release_session("conv1", ReleaseReason.SESSION_END)

    assert sandbox.release_calls == [ReleaseReason.SESSION_END]
    assert db.release_calls == [ReleaseReason.SESSION_END]


async def test_shared_executor_across_capabilities_single_prepare():
    """多 capability 共享同一 executor → prepare 只一次(共享底座)。"""
    reg = InMemoryExecutorRegistry()
    sandbox = _RecordingExecutor("sandbox")

    # 模拟 py_tool / file_tool 两个 capability 都 acquire 同一 sandbox
    await reg.acquire("conv1", sandbox)  # capability1
    await reg.acquire("conv1", sandbox)  # capability2
    assert sandbox.prepare_calls == 1


async def test_release_is_idempotent():
    """对未 acquire 的会话 release 不报错。"""
    reg = InMemoryExecutorRegistry()
    # 不抛异常
    await reg.release_session("no_such_conv", ReleaseReason.SESSION_END)


async def test_get_returns_none_when_not_acquired():
    reg = InMemoryExecutorRegistry()
    assert reg.get("conv1", "sandbox") is None
    ex = _RecordingExecutor("sandbox")
    await reg.acquire("conv1", ex)
    assert reg.get("conv1", "sandbox") is ex


async def test_isolates_sessions():
    """不同会话隔离:conv1 release 不影响 conv2 的 executor。"""
    reg = InMemoryExecutorRegistry()
    sb1 = _RecordingExecutor("sandbox-1")
    sb2 = _RecordingExecutor("sandbox-2")

    await reg.acquire("conv1", sb1)
    await reg.acquire("conv2", sb2)

    await reg.release_session("conv1", ReleaseReason.SESSION_END)

    assert sb1.release_calls == [ReleaseReason.SESSION_END]
    assert sb2.release_calls == []  # conv2 未受影响
    assert reg.get("conv2", "sandbox-2") is sb2