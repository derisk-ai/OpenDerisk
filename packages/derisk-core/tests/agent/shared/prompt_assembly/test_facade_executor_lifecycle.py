"""RFC-005 S5/S6 Facade executor 生命周期与构建态缓存单测。

覆盖:
- S5:facade 据 requires acquire executor(触发 prepare);end_session release(SESSION_END)
- S5:executor 会话级复用(acquire 不重复 prepare)
- S6:静态快照缓存(config_hash 命中)使 executor prepare 只在首次静态构建时发生
- 桥接路径(无 executor_provider)不阻塞
"""

from typing import Any, List

import pytest

from derisk.core.interface.resource.executor import Executor, ExecutorCall, ExecutorStatus, ReleaseReason
from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot
from derisk.agent.capabilities.facade import ResourceFacade
from derisk.core.interface.resource.protocol import ResourceProtocol


# --------------------------------------------------------------------------- #
# 测试 Executor
# --------------------------------------------------------------------------- #
class _RecordingExecutor(Executor):
    def __init__(self, eid: str, fail_prepare: bool = False):
        self._id = eid
        self._fail = fail_prepare
        self.prepare_calls = 0
        self.release_calls: list = []
        self.status = ExecutorStatus.UNINITIALIZED

    @property
    def executor_id(self) -> str:
        return self._id

    async def prepare(self) -> None:
        self.prepare_calls += 1
        if self._fail:
            self.status = ExecutorStatus.FAILED
            raise RuntimeError("prepare failed")
        self.status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall):
        return "ok"

    async def release(self, reason: ReleaseReason) -> None:
        self.release_calls.append(reason)
        self.status = ExecutorStatus.RELEASED


# --------------------------------------------------------------------------- #
# 原生 declare + requires 的资源
# --------------------------------------------------------------------------- #
def _make_native_resource(cap_id: str, requires_ids: List[str]):
    class _R(ResourceProtocol):
        capability_id = cap_id

        @classmethod
        def declare(cls, config: Any) -> List[Contribution]:
            return [
                Contribution(
                    capability_id=cls.capability_id,
                    slot=Slot.SYSTEM,
                    content=f"sys-{cls.capability_id}",
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.USER,
                )
            ]

        @classmethod
        def requires(cls, config: Any) -> List[str]:
            return list(requires_ids)

    return _R()


def _pack_with(*resources):
    class _Pack:
        is_pack = True

        @property
        def sub_resources(self):
            return list(resources)

    return _Pack()


# --------------------------------------------------------------------------- #
# S5: acquire 触发 prepare
# --------------------------------------------------------------------------- #
async def test_facade_acquires_required_executor_and_prepares():
    """原生资源 requires=['sandbox'],facade acquire 触发 sandbox.prepare。"""
    sandbox = _RecordingExecutor("sandbox")
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    assert sandbox.prepare_calls == 1
    assert snap.executors_ready is True


async def test_facade_executor_prepared_once_per_session():
    """同会话多次 assemble:executor prepare 只一次(会话级复用)。"""
    sandbox = _RecordingExecutor("sandbox")
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    await facade.assemble(agent_id="a1", conv_id="c1", resource_root=_pack_with(res))
    # 第二次:静态快照缓存命中,不重建 bundle;executor 已 acquire 不重复
    await facade.assemble(agent_id="a1", conv_id="c1", resource_root=_pack_with(res))
    assert sandbox.prepare_calls == 1


async def test_end_session_releases_executors():
    """end_session 触发该会话 executor release(SESSION_END)。"""
    sandbox = _RecordingExecutor("sandbox")
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    await facade.assemble(agent_id="a1", conv_id="c1", resource_root=_pack_with(res))
    await facade.end_session("c1")

    assert sandbox.release_calls == [ReleaseReason.SESSION_END]


async def test_executor_shared_across_resources_prepared_once():
    """多资源 requires 同一 sandbox → prepare 一次(共享底座,引用计数)。"""
    sandbox = _RecordingExecutor("sandbox")
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res1 = _make_native_resource("py_tool", requires_ids=["sandbox"])
    res2 = _make_native_resource("file_tool", requires_ids=["sandbox"])

    await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res1, res2),
    )
    assert sandbox.prepare_calls == 1


async def test_failed_prepare_does_not_block_bundle():
    """executor prepare 失败不阻塞 bundle 构建;executors_ready=False。"""
    sandbox = _RecordingExecutor("sandbox", fail_prepare=True)
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    assert sandbox.prepare_calls == 1
    assert snap.executors_ready is False
    # bundle 仍有 system
    assert len(snap.frozen.system) == 1


# --------------------------------------------------------------------------- #
# 无 executor_provider:桥接/纯协议不阻塞
# --------------------------------------------------------------------------- #
async def test_no_executor_provider_does_not_block():
    """无 executor_provider 注册时,requires 的 executor 跳过,不报错。"""
    facade = ResourceFacade()  # 无 provider
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    assert snap.executors_ready is True  # 无需准备也视为 ready


# --------------------------------------------------------------------------- #
# S6: 静态快照缓存使 executor prepare 仅首次
# --------------------------------------------------------------------------- #
async def test_cache_hit_skips_bundle_rebuild_same_session():
    """同会话第二次 assemble 命中静态缓存 → 不重建 bundle;executor 不重 prepare。

    注:当前 registry 为会话级 lifecycle(DB连接器随会话)。
    沙箱类 Agent 级共享 executor(跨会话复用)见 RFC §3.4 开放问题1,
    由 S10 接入时以 Pool 化 registry 补充,此处不覆盖。
    """
    sandbox = _RecordingExecutor("sandbox")
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    snap1 = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    snap2 = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    assert snap1.frozen is snap2.frozen  # 缓存命中,不重建
    assert sandbox.prepare_calls == 1    # 同会话内复用,不重 prepare


async def test_invalidate_config_rebuilds_and_reacquires():
    """配置变更 invalidate 后重建 bundle,重新 acquire executor(prepare 复用已就绪)。"""
    sandbox = _RecordingExecutor("sandbox")
    facade = ResourceFacade(executor_provider={"sandbox": sandbox})
    res = _make_native_resource("py_tool", requires_ids=["sandbox"])

    snap1 = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    facade.invalidate_config("a1", snap1.config_hash)

    snap2 = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_pack_with(res),
    )
    assert snap1.frozen is not snap2.frozen  # 重建
    # executor 已就绪,重新 acquire 不重 prepare
    assert sandbox.prepare_calls == 1