"""RFC-006 Stage 2: SandboxExecutor lifecycle + provider 接线单测。"""

import pytest

from derisk.agent.capabilities import ResourceFacade
from derisk.agent.capabilities.sandbox.executor import (
    SANDBOX_EXECUTOR_ID,
    SandboxExecutor,
)
from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.executor import (
    Executor,
    ExecutorStatus,
    ReleaseReason,
)


# --------------------------------------------------------------------------- #
# 伪 sandbox_manager(带 client 属性)
# --------------------------------------------------------------------------- #
class _FakeSandboxManager:
    def __init__(self, has_client=True):
        self.client = object() if has_client else None


class _NeedsSandboxCapability(Executor):
    """伪 executor (capability 经适配器会注册进 provider),requires=['sandbox']。

    用于验 facade _prepare_executors 据 requires 触发 sandbox acquire。
    """

    def __init__(self):
        self._status = ExecutorStatus.UNINITIALIZED
        self.prepare_calls = 0

    @property
    def executor_id(self):
        return "need-sandbox-mock"

    @property
    def status(self):
        return self._status

    async def prepare(self):
        self.prepare_calls += 1
        self._status = ExecutorStatus.READY

    async def execute(self, call):
        return None

    async def release(self, reason):
        self._status = ExecutorStatus.RELEASED


def test_executor_id_is_sandbox():
    assert SandboxExecutor(_FakeSandboxManager()).executor_id == SANDBOX_EXECUTOR_ID


def test_prepare_ready_when_client_available():
    ex = SandboxExecutor(_FakeSandboxManager(has_client=True))
    assert ex.status == ExecutorStatus.UNINITIALIZED
    import asyncio

    asyncio.get_event_loop().run_until_complete(ex.prepare())
    assert ex.status == ExecutorStatus.READY


def test_prepare_raises_when_no_client():
    ex = SandboxExecutor(_FakeSandboxManager(has_client=False))
    import asyncio

    with pytest.raises(RuntimeError, match="not available"):
        asyncio.get_event_loop().run_until_complete(ex.prepare())
    assert ex.status == ExecutorStatus.UNINITIALIZED


def test_release_sets_released():
    ex = SandboxExecutor(_FakeSandboxManager(has_client=True))
    import asyncio

    loop = asyncio.get_event_loop()
    loop.run_until_complete(ex.prepare())
    loop.run_until_complete(ex.release(ReleaseReason.SESSION_END))
    assert ex.status == ExecutorStatus.RELEASED


def test_execute_not_implemented():
    ex = SandboxExecutor(_FakeSandboxManager(has_client=True))
    import asyncio

    with pytest.raises(NotImplementedError):
        asyncio.get_event_loop().run_until_complete(
            ex.execute(type("C", (), {"executor_id": "sandbox", "tool_name": "x", "args": {}}))
        )


async def test_facade_acquire_sandbox_when_required():
    """facade 注入 SandboxExecutor 后,requires=['sandbox'] 触发 registry.acquire→prepare。"""
    facade = ResourceFacade()
    facade.executor_provider["sandbox"] = SandboxExecutor(_FakeSandboxManager(has_client=True))
    # 伪 capability executor,依赖 sandbox
    cap_ex = _NeedsSandboxCapability()
    facade.executor_provider[cap_ex.executor_id] = cap_ex

    ready = await facade._prepare_executors(
        conv_id="c1", required_ids=["sandbox", cap_ex.executor_id]
    )
    assert ready is True
    assert facade.executor_provider["sandbox"].status == ExecutorStatus.READY
    assert cap_ex.prepare_calls == 1


async def test_facade_acquire_sandbox_skips_when_not_in_provider():
    """无 sandbox 在 provider 时,required_ids 含 'sandbox' 不报错、跳过(纯协议场景)。"""
    facade = ResourceFacade()
    cap_ex = _NeedsSandboxCapability()
    facade.executor_provider[cap_ex.executor_id] = cap_ex

    ready = await facade._prepare_executors(
        conv_id="c1", required_ids=["sandbox", cap_ex.executor_id]
    )
    # sandbox 跳过(无 provider),cap 准备成功,ready 由 cap 决定
    assert ready is True
    assert cap_ex.prepare_calls == 1