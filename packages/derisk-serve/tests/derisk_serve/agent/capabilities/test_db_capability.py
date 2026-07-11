"""RFC-005 Step C: db capability 输入投影测试(纯 core 部分)。

DBCapabilityResource declare 库基本信息 + DataRequirement 占位(纯 core,无 serve)。
DBExecutor(连 serve spec_service)已迁 serve 层,相关测试在 serve 测试目录。
facade 回填用 mock executor(不依赖真实 DBExecutor)。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot
from derisk.core.interface.resource.data_requirement import (
    DataRequirement,
    InjectionMode,
    injection_mode_for_table_count,
)
from derisk_serve.agent.capabilities.db.resource import DBCapabilityResource
from derisk.agent.capabilities.facade import ResourceFacade


def _make_legacy_db(db_name="paydb", db_type="mysql", datasource_id=42):
    legacy = SimpleNamespace(
        _db_name=db_name, db_name=db_name, _db_type=db_type,
        _dialect="mysql", _datasource_id=datasource_id,
        _connector=MagicMock(),
    )
    legacy._resolve_datasource_id = lambda: datasource_id
    legacy._connector.get_table_names.return_value = ["t1", "t2"]
    return legacy


def test_db_declares_basic_info_and_data_requirement():
    legacy = _make_legacy_db()
    res = DBCapabilityResource(legacy_instance=legacy)
    contribs = res.declare_db()
    assert len(contribs) == 2
    basic, table_placeholder = contribs
    assert basic.slot == Slot.SYSTEM
    assert "paydb" in basic.content
    assert "mysql" in basic.content
    assert isinstance(table_placeholder.content, DataRequirement)
    assert table_placeholder.content.kind == "db_prompt"
    assert table_placeholder.content.executor_id == "db:42"


def test_db_requires_executor():
    legacy = _make_legacy_db()
    res = DBCapabilityResource(legacy_instance=legacy)
    assert res.requires() == ["db:42"]


def test_db_declare_empty_without_legacy():
    res = DBCapabilityResource()
    assert res.declare_db() == []


def test_db_capability_id_is_db():
    res = DBCapabilityResource()
    assert res.capability_id == "db"


def test_large_db_not_injects_table_list():
    """大库分级纯函数:>=500 → LARGE(不注入表列表,发工具指引)。"""
    mode = injection_mode_for_table_count(800)
    assert mode == InjectionMode.LARGE
    assert mode != InjectionMode.SMALL


def test_facade_wraps_legacy_db():
    facade = ResourceFacade()
    from derisk_serve.agent.capabilities.db import register_wrappers
    register_wrappers(facade)
    facade.register_legacy_wrapper(object, lambda x: DBCapabilityResource(legacy_instance=x))
    legacy = _make_legacy_db()
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, DBCapabilityResource)
    contribs = wrapped.declare_db()
    assert any("paydb" in c.content for c in contribs if isinstance(c.content, str))