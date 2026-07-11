"""RFC-005 Step B / RFC-006 Stage 4: app capability 迁移测试。"""

from types import SimpleNamespace

import pytest

from derisk.core.interface.resource.bundle import CacheScope, Lifetime, Slot
from derisk_serve.agent.capabilities.app import (
    AppCapability,
    AppCapabilityResource,
    build_capability,
    register_capability,
)
from derisk.agent.capabilities.facade import ResourceFacade


def _make_legacy_app(app_name="DB 诊断", app_code="db-agent", app_desc="数据库诊断助手"):
    return SimpleNamespace(app_name=app_name, app_code=app_code, app_desc=app_desc)


def test_app_declares_from_legacy():
    legacy = _make_legacy_app()
    res = AppCapabilityResource(legacy_instance=legacy)
    contribs = res.declare_app()
    assert len(contribs) == 1
    c = contribs[0]
    assert c.slot == Slot.SYSTEM
    assert c.capability_id == "app"
    assert c.cache_scope == CacheScope.USER
    assert "DB 诊断" in c.content
    assert "db-agent" in c.content


def test_app_declares_from_explicit():
    res = AppCapabilityResource(
        app_name="App1", app_code="code1", description="desc1"
    )
    contribs = res.declare_app()
    assert len(contribs) == 1
    assert "App1" in contribs[0].content


def test_app_empty_when_no_data():
    res = AppCapabilityResource()
    assert res.declare_app() == []


def test_facade_wraps_legacy_app():
    facade = ResourceFacade()
    from derisk_serve.agent.capabilities.app import register_wrappers
    register_wrappers(facade)
    # object 基类命中(演示;真实用 AppResource 类)
    facade.register_legacy_wrapper(object, lambda x: AppCapabilityResource(legacy_instance=x))
    legacy = _make_legacy_app()
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, AppCapabilityResource)
    contribs = wrapped.declare_app()
    assert "DB 诊断" in contribs[0].content


# =========================================================================== #
# RFC-006 Stage 4:AppCapability 自管理对象模型(走 facade.assemble 全链)
# =========================================================================== #
def test_app_capability_from_config():
    """factory 从 config dict 产 AppCapability(无 I/O,无旧 Resource 实例)。"""
    cap = build_capability(
        {"app_name": "DB 诊断", "app_code": "db-agent", "app_desc": "数据库诊断助手"},
        system_app=None,
    )
    assert isinstance(cap, AppCapability)
    assert cap.capability_id == "app"
    assert cap.executor_id == "app:db-agent"  # 多 app 唯一


def test_app_capability_declare_renders_description():
    """AppCapability.declare 产 app 描述 SYSTEM(修复旧 declare 桩返回 [])。"""
    cap = build_capability(
        {"app_name": "DB 诊断", "app_code": "db-agent", "app_desc": "数据库诊断助手"},
    )
    contribs = cap.declare()
    assert len(contribs) == 1
    c = contribs[0]
    assert c.slot == Slot.SYSTEM
    assert c.capability_id == "app"
    assert c.cache_scope == CacheScope.USER
    assert "DB 诊断" in c.content
    assert "db-agent" in c.content
    assert "数据库诊断助手" in c.content


def test_app_capability_declare_empty_when_no_name():
    assert AppCapability(app_name="", app_code="", description="").declare() == []


async def test_register_capability_registers_factory():
    facade = ResourceFacade()
    register_capability(facade)
    assert "app" in facade._capability_factories


async def test_assemble_declares_app_via_capability_pack():
    """Agent 持有 CapabilityPack(对象)→ facade.assemble 经适配器产 app 描述进 system。

    验证对象模型自洽:factory→对象→pack→facade declare 适配器→system,无需 config
    再流到 facade(config 在更上游构造期已被消费成对象)。
    """
    from derisk.agent.capabilities.facade import _iter_sub_resources
    from derisk.core.interface.resource.capability import CapabilityPack

    facade = ResourceFacade()
    cap = AppCapability(app_name="Canvas", app_code="canvas", description="画布助手")
    pack = CapabilityPack([cap])
    # _iter_sub_resources 能把 CapabilityPack 当 pack 遍历
    assert _iter_sub_resources(pack) == [cap]

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=pack,
        identity="id", control_block="ctl",
    )
    texts = [b.text for b in snap.frozen.system]
    assert any("Canvas" in t and "画布助手" in t for t in texts)


def test_app_capability_prepare_release_and_execute():
    import asyncio
    from derisk.core.interface.resource.executor import (
        ExecutorCall,
        ExecutorStatus,
        ReleaseReason,
    )

    cap = AppCapability(app_name="Z", app_code="z", description="")
    loop = asyncio.get_event_loop()
    assert cap._status == ExecutorStatus.UNINITIALIZED
    loop.run_until_complete(cap.prepare())
    assert cap._status == ExecutorStatus.READY
    loop.run_until_complete(cap.release(ReleaseReason.SESSION_END))
    assert cap._status == ExecutorStatus.RELEASED
    # execute 不接管 agent_start(保持 AgentAction)
    with pytest.raises(NotImplementedError):
        loop.run_until_complete(
            cap.execute(
                ExecutorCall(executor_id="app:z", capability_id="app", tool_name="agent_start", args={})
            )
        )


# =========================================================================== #
# Stage 4.5:旧 GptAppResource 实例 → AppCapability 过渡(生产路径行为)
# =========================================================================== #
def test_app_capability_from_legacy():
    """from_legacy 读旧实例属性产 AppCapability(无 I/O)。"""
    legacy = _make_legacy_app()
    cap = AppCapability.from_legacy(legacy)
    assert isinstance(cap, AppCapability)
    assert "DB 诊断" in cap.declare()[0].content


def test_legacy_app_instance_becomes_capability_in_facade():
    """facade 遍历旧 GptAppResource 实例 → 翻成 AppCapability(经 provider),declare 出描述。

    这是生产路径行为核心:旧 ResourcePack 里的旧实例被 register_legacy_capability_provider
    翻成自管理 Capability,修复旧 wrapper declare 空桩 → app 描述进 system。
    """
    facade = ResourceFacade()
    register_capability(facade)  # 注册 legacy provider
    legacy = _make_legacy_app()
    wrapped = facade._to_resource_protocol(legacy)
    # 返回的是 declare 适配器,委托到真正的 AppCapability(非旧 AppCapabilityResource)
    from derisk.agent.capabilities.facade import _CapabilityDeclareAdapter

    assert isinstance(wrapped, _CapabilityDeclareAdapter)
    contribs = wrapped.declare()
    assert len(contribs) == 1
    assert "DB 诊断" in contribs[0].content
    # 执行面已注入 executor_provider
    assert "app:db-agent" in facade.executor_provider


async def test_assemble_legacy_app_pack_declares_description():
    """端到端:旧 ResourcePack(含旧 app 实例)→ facade.assemble → app 描述进 system。"""
    from derisk.agent.capabilities.facade import _iter_sub_resources
    from derisk.agent.resource import ResourcePack

    facade = ResourceFacade()
    register_capability(facade)
    legacy = _make_legacy_app()
    # 造一个真 ResourcePack 包住旧实例(模拟 agent.resource)
    pack = ResourcePack([legacy])

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=pack,
        identity="id", control_block="ctl",
    )
    texts = [b.text for b in snap.frozen.system]
    assert any("DB 诊断" in t for t in texts)