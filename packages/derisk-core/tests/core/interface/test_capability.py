"""RFC-006 Capability ABC + facade 适配层单测。

验证:
- Capability ABC 可被子类实现并实例化。
- facade._to_resource_protocol 遇 Capability 注入执行面(executor_provider)+ 返 declare 适配器。
- 注册 register_capability_factory 后,assemble 能用 Capability 走全链(declare→acquire prepare→snapshot)。
- Capability.execute 经适配器被 registry.acquire 触发 prepare,经 provider.get 被 ToolDispatcher 取到。
"""

from typing import Any, List

import pytest

from derisk.agent.capabilities import Capability, ResourceFacade
from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.capability import Capability as _Cap
from derisk.core.interface.resource.data_requirement import DataRequirement
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)


# --------------------------------------------------------------------------- #
# 基础:ABC 可实例化 / 默认契约
# --------------------------------------------------------------------------- #
def test_capability_is_abstract():
    """Capability 不可直接实例化(declare/prepare/execute/release 未实现)。"""
    with pytest.raises(TypeError):
        _Cap()  # type: ignore[abstract]


def test_capability_subclass_instantiable_with_full_iface():
    """实现全部抽象方法的子类可实例化,executor_id 默认同 capability_id。"""

    class _R(Capability):
        capability_id = "r:test"

        def declare(self, config=None) -> List[Contribution]:
            return []

        async def prepare(self) -> None:
            pass

        async def execute(self, call: ExecutorCall) -> Any:
            return "ok"

        async def release(self, reason: ReleaseReason) -> None:
            pass

    r = _R()
    assert r.capability_id == "r:test"
    assert r.executor_id == "r:test"  # 默认同 capability_id
    assert r.requires(None) == ["r:test"]  # 默认 [self.executor_id]


def test_capability_consume_default_empty_and_fetch_not_implemented():
    class _R(Capability):
        capability_id = "r"

        def declare(self, config=None):
            return []

        async def prepare(self):
            pass

        async def execute(self, call):
            return None

        async def release(self, reason):
            pass

    import asyncio

    r = _R()
    assert asyncio.get_event_loop().run_until_complete(r.consume("x")) == []
    with pytest.raises(NotImplementedError):
        asyncio.get_event_loop().run_until_complete(
            r.fetch(DataRequirement(executor_id="r", capability_id="r", kind="k", params={}))
        )


# --------------------------------------------------------------------------- #
# facade 适配:Capability → declare 适配器 + executor 注入
# --------------------------------------------------------------------------- #
class _FakeCap(Capability):
    """带状态的伪 Capability:prepare 计数/execute 回放/fetch 回填。"""

    capability_id = "fake:cap"

    def __init__(self):
        self.prepare_calls = 0
        self.release_calls: list = []
        self._status = ExecutorStatus.UNINITIALIZED

    def declare(self, config=None) -> List[Contribution]:
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content="fake-system-text",
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=10,
            )
        ]

    def requires(self, config=None) -> List[str]:
        return [self.executor_id]

    async def prepare(self) -> None:
        self.prepare_calls += 1
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        return {"echo": call.args, "tool": call.tool_name}

    async def release(self, reason: ReleaseReason) -> None:
        self.release_calls.append(reason)
        self._status = ExecutorStatus.RELEASED

    async def fetch(self, requirement: DataRequirement) -> Any:
        return "fetched-text"

    async def consume(self, call_result: Any) -> List[Contribution]:
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content=f"consumed:{call_result}",
                lifetime=Lifetime.TURN,
                cache_scope=CacheScope.NONE,
            )
        ]


def test_to_resource_protocol_adapts_capability_and_injects_executor():
    """遇 Capability:注入执行面到 executor_provider,返 declare 适配器(ResourceProtocol)。"""
    facade = ResourceFacade()
    cap = _FakeCap()
    wrapped = facade._to_resource_protocol(cap)
    # 返回 declare 适配器(carry capability_id)
    assert wrapped is not None
    assert wrapped.capability_id == "fake:cap"
    assert callable(getattr(wrapped, "declare"))
    # 执行面已注入 executor_provider,executor_id 匹配
    assert cap.executor_id in facade.executor_provider
    executor = facade.executor_provider[cap.executor_id]
    assert executor.executor_id == "fake:cap"


def test_declare_adapter_renders_and_requires():
    """declare 适配器代理 declare/requires/consume 到 Capability。"""
    import asyncio

    facade = ResourceFacade()
    cap = _FakeCap()
    wrapped = facade._to_resource_protocol(cap)

    contribs = wrapped.declare(None)
    assert len(contribs) == 1
    assert contribs[0].content == "fake-system-text"
    assert wrapped.requires(None) == ["fake:cap"]
    consumed = asyncio.get_event_loop().run_until_complete(wrapped.consume("r"))
    assert consumed[0].content == "consumed:r"


def test_executor_adapter_prepare_execute_release():
    """executor 适配器代理 prepare/execute/release/fetch,并维护 status。"""
    import asyncio

    facade = ResourceFacade()
    cap = _FakeCap()
    facade._to_resource_protocol(cap)  # 注入 executor 适配器
    executor = facade.executor_provider["fake:cap"]

    loop = asyncio.get_event_loop()
    assert executor.status == ExecutorStatus.UNINITIALIZED
    loop.run_until_complete(executor.prepare())
    assert cap.prepare_calls == 1
    assert executor.status == ExecutorStatus.READY

    result = loop.run_until_complete(
        executor.execute(ExecutorCall(executor_id="fake:cap", capability_id="fake:cap", tool_name="t", args={"a": 1}))
    )
    assert result == {"echo": {"a": 1}, "tool": "t"}

    fetched = loop.run_until_complete(
        executor.fetch(DataRequirement(executor_id="fake:cap", capability_id="fake:cap", kind="k", params={}))
    )
    assert fetched == "fetched-text"

    loop.run_until_complete(executor.release(ReleaseReason.SESSION_END))
    assert cap.release_calls == [ReleaseReason.SESSION_END]
    assert executor.status == ExecutorStatus.RELEASED


# --------------------------------------------------------------------------- #
# 全链:facade.assemble 走 Capability(declare→acquire prepare→snapshot)
# --------------------------------------------------------------------------- #
class _CapPack:
    """伪 ResourcePack:sub_resources 是一个 Capability 实例。"""

    is_pack = True

    def __init__(self, cap: Capability):
        self._cap = cap

    @property
    def sub_resources(self):
        return [self._cap]


async def test_assemble_runs_capability_full_chain():
    """Capability 经 assemble:declare 进 system + acquire 触发 prepare + 执行面入 provider。"""
    facade = ResourceFacade()
    cap = _FakeCap()
    pack = _CapPack(cap)

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=pack,
        identity="id", control_block="ctl",
    )
    # declare 产出进 system
    texts = [b.text for b in snap.frozen.system]
    assert "fake-system-text" in texts
    # acquire 触发 prepare(经 requires=["fake:cap"] → registry.acquire → executor_adapter.prepare)
    assert cap.prepare_calls == 1
    assert snap.executors_ready is True
    # 执行面可通过 provider 取到(供 ToolDispatcher Route B)
    assert "fake:cap" in facade.executor_provider


async def test_register_capability_factory_builds_from_config():
    """register_capability_factory 注册后,assemble 能识别 AgentResource 配置产 Capability。

    注:factory 路径在 Stage 4+ 各 capability 的 register_capability 中接入;此处仅验
    注册表存在 + factory 可调用。assemble 从 config 直接构造 Capability 的完整接入在
    ResourceManager 改造(各 capability Stage)落地后补端到端。
    """
    facade = ResourceFacade()
    built = {}

    def _factory(value: dict, system_app) -> Capability:
        c = _FakeCap()
        built["value"] = value
        return c

    facade.register_capability_factory("fake", _factory)
    assert "fake" in facade._capability_factories
    cap = facade._capability_factories["fake"]({"k": "v"}, None)
    assert isinstance(cap, _FakeCap)
    assert built["value"] == {"k": "v"}