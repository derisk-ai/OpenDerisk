"""RFC-005 Step B: app capability 迁移测试。"""

from types import SimpleNamespace

from derisk.core.interface.resource.bundle import CacheScope, Lifetime, Slot
from derisk_serve.agent.capabilities.app import AppCapabilityResource
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