"""RFC-005 Step A: Executor.fetch + facade 数据需求回填测试。

declare 纯函数化 DB/知识等 I/O 数据的机制:declare 产出含 DataRequirement 的
Contribution 作占位,facade 调 executor.fetch 预取后用结果重建 Contribution。
"""

from typing import Any, Dict, List

import pytest

from derisk.core.interface.resource.bundle import CacheScope, Contribution, InputBundle, Lifetime, Slot
from derisk.core.interface.resource.executor import Executor, ExecutorCall, ExecutorRegistry, ExecutorStatus, InMemoryExecutorRegistry, ReleaseReason
from derisk.core.interface.resource.data_requirement import (
    DataRequirement,
    InjectionMode,
    injection_mode_for_table_count,
)
from derisk.agent.capabilities import ResourceFacade
from derisk.agent.capabilities.registry import CapabilityRegistry
from derisk.core.interface.resource.protocol import ResourceProtocol


# --------------------------------------------------------------------------- #
# 支持 fetch 的 fake executor
# --------------------------------------------------------------------------- #
class _FakeDBExecutor(Executor):
    """模拟 DB executor,fetch 返回 db_stats/table_count。"""

    def __init__(self):
        self.fetch_calls: List[DataRequirement] = []
        self.status = ExecutorStatus.READY

    @property
    def executor_id(self) -> str:
        return "db:conn1"

    async def prepare(self) -> None:
        pass

    async def execute(self, call: ExecutorCall) -> Any:
        return "exec"

    async def release(self, reason: ReleaseReason) -> None:
        pass

    async def fetch(self, requirement: DataRequirement) -> Any:
        self.fetch_calls.append(requirement)
        if requirement.kind == "db_stats":
            # 返回 table_count,declare 据此决定分级
            return {"table_count": 800, "groups": {}}
        return f"fetched-{requirement.kind}"


# --------------------------------------------------------------------------- #
# DB-style capability:declare 产 DataRequirement 占位
# --------------------------------------------------------------------------- #
class _DBCapResource(ResourceProtocol):
    """模拟 DB capability:declare 阶段产 DataRequirement 占位(因 table_count 需 I/O)。"""

    capability_id = "db"

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        # declare 纯函数:无法查 table_count,产 DataRequirement 让 facade 回填
        req = DataRequirement(
            executor_id="db:conn1",
            capability_id=cls.capability_id,
            kind="db_stats",
            params={"datasource_id": "ds1"},
        )
        return [
            Contribution(
                capability_id=cls.capability_id,
                slot=Slot.SYSTEM,
                content=req,            # 占位,待 fetch 回填
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=10,
            )
        ]


# --------------------------------------------------------------------------- #
# fetch 接口
# --------------------------------------------------------------------------- #
async def test_executor_fetch_default_not_implemented():
    """不覆盖 fetch 的 executor 调 fetch 抛 NotImplementedError(非抽象强制)。"""

    class _BareExecutor(Executor):
        @property
        def executor_id(self): return "bare"
        async def prepare(self): pass
        async def execute(self, call): pass
        async def release(self, reason): pass

    ex = _BareExecutor()
    req = DataRequirement(executor_id="bare", capability_id="c", kind="k")
    with pytest.raises(NotImplementedError):
        await ex.fetch(req)


async def test_fake_db_executor_fetch_returns_stats():
    ex = _FakeDBExecutor()
    req = DataRequirement(executor_id="db:conn1", capability_id="db", kind="db_stats")
    data = await ex.fetch(req)
    assert data["table_count"] == 800


# --------------------------------------------------------------------------- #
# facade 回填:declare DataRequirement → fetch → 重建 Contribution
# --------------------------------------------------------------------------- #
async def test_facade_resolves_data_requirement_via_executor_fetch():
    """facade 扫描 declare 产出的 DataRequirement,content 调 fetch 回填为文本。"""
    db_executor = _FakeDBExecutor()
    facade = ResourceFacade(executor_provider={"db:conn1": db_executor})

    # 模拟 declare 产出含 DataRequirement 的 bundle,经 facade 回填
    bundle = InputBundle()
    bundle.add(_DBCapResource.declare(None)[0])

    # 直接调内部回填(模拟 _build_static_bundle 末尾)
    await facade._resolve_data_requirements(bundle, conv_id="c1")

    assert len(bundle.system) == 1
    c = bundle.system[0]
    # content 已从 DataRequirement 回填为 fetch 结果的 str
    assert not isinstance(c.content, DataRequirement)
    assert "800" in str(c.content)
    # executor 被调
    assert len(db_executor.fetch_calls) == 1
    assert db_executor.fetch_calls[0].kind == "db_stats"
    # capability_id/slot 等保持
    assert c.capability_id == "db"
    assert c.slot == Slot.SYSTEM


async def test_facade_skips_when_no_executor_registered():
    """无对应 executor provider 时,DataRequirement 占位保留(declare 应容忍)。"""
    facade = ResourceFacade()  # 空 provider
    bundle = InputBundle()
    bundle.add(_DBCapResource.declare(None)[0])

    await facade._resolve_data_requirements(bundle, conv_id="c1")

    # 占位保留(无 executor)
    assert isinstance(bundle.system[0].content, DataRequirement)


# --------------------------------------------------------------------------- #
# DB 大库分级:data_requirement 纯函数 + fetch 回填后 declare 决策
# --------------------------------------------------------------------------- #
def test_db_injection_mode_decision_after_fetch():
    """模拟 declare 二次调(回填 table_count=800 后)决策注入模式。"""
    table_count = 800  # 假装 fetch 回填得到
    mode = injection_mode_for_table_count(table_count)
    assert mode == InjectionMode.LARGE
    # LARGE:不注入表列表,declare 改产工具指引(由 DB capability 决策)


async def test_facade_resolve_handles_fetch_failure():
    """executor.fetch 抛异常时,占位保留,不中断 facade。"""

    class _FailExecutor(_FakeDBExecutor):
        async def fetch(self, requirement: DataRequirement) -> Any:
            raise RuntimeError("db down")

    facade = ResourceFacade(executor_provider={"db:conn1": _FailExecutor()})
    bundle = InputBundle()
    bundle.add(_DBCapResource.declare(None)[0])

    await facade._resolve_data_requirements(bundle, conv_id="c1")
    # 失败保留占位
    assert isinstance(bundle.system[0].content, DataRequirement)