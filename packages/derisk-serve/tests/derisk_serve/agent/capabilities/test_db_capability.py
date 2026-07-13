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


# =========================================================================== #
# RFC-006 Stage 6:DBCapability 自管理(prepare/fetch/declare/release + 取连接)
# =========================================================================== #
def test_db_capability_from_config():
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    cap = DBCapability.from_config({"db_name": "paydb", "db_id": 42})
    assert isinstance(cap, DBCapability)
    assert cap.db_name == "paydb"
    assert cap.capability_id == "db:42"
    assert cap.executor_id == "db:42"


def test_db_capability_from_legacy_reuses_connector():
    """from_legacy 复用旧实例已建的 connector(不重复建连接),状态 READY。"""
    from derisk.core.interface.resource.executor import ExecutorStatus
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    legacy = _make_legacy_db()
    cap = DBCapability.from_legacy(legacy)
    assert cap.get_connector() is legacy._connector  # 复用,未重建
    assert cap._status == ExecutorStatus.READY
    assert cap.capability_id == "db:42"


def test_db_capability_declare_basic_and_placeholder():
    from derisk.core.interface.resource.data_requirement import DataRequirement
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    cap = DBCapability(db_name="paydb", db_id=42, db_type="mysql", dialect="mysql")
    contribs = cap.declare()
    assert len(contribs) == 2
    basic, placeholder = contribs
    assert "paydb" in basic.content and "mysql" in basic.content
    assert isinstance(placeholder.content, DataRequirement)
    assert placeholder.content.kind == "db_prompt"
    assert placeholder.content.executor_id == "db:42"


async def test_db_capability_fetch_uses_connector_when_no_spec_service(monkeypatch):
    """无 spec_service 时 fetch 回退 connector.get_table_names(异步)。"""
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    cap = DBCapability(db_name="paydb", db_id=42)
    cap._connector = MagicMock()
    cap._connector.get_table_names.return_value = ["orders", "users"]
    # _get_spec_service 返 None(serve 不可用)
    monkeypatch.setattr(DBCapability, "_get_spec_service", lambda self: None)
    req = DataRequirement(
        executor_id="db:42", capability_id="db:42", kind="db_prompt",
        params={"datasource_id": 42, "db_name": "paydb"},
    )
    text = await cap.fetch(req)
    assert "orders" in text and "users" in text


async def test_db_capability_prepare_builds_connector(monkeypatch):
    """prepare 经 local_db_manager.get_connector 建连接(异步),状态 READY。"""
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    fake_conn = MagicMock()
    fake_conn.db_type = "sqlite"
    fake_conn.dialect = "sqlite"
    fake_mgr = MagicMock()
    fake_mgr.get_connector.return_value = fake_conn
    fake_cfg = MagicMock()
    fake_cfg.local_db_manager = fake_mgr
    monkeypatch.setattr("derisk._private.config.Config", lambda: fake_cfg)

    cap = DBCapability(db_name="paydb", db_id=42)
    await cap.prepare()
    assert cap._status.value == "ready"
    assert cap.get_connector() is fake_conn
    assert cap._db_type == "sqlite"


def test_db_capability_get_connector_for_route_a_tools():
    """折中:Route A DB 工具从 DBCapability.get_connector() 取连接(取代扫 resource_map)。"""
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    legacy = _make_legacy_db()
    cap = DBCapability.from_legacy(legacy)
    assert cap.get_connector() is legacy._connector


async def test_facade_flips_legacy_db_to_capability():
    """旧 DatasourceResource 实例 → facade 翻成 DBCapability(经 provider),declare 出库信息。"""
    from derisk.agent.capabilities.facade import _CapabilityDeclareAdapter
    from derisk_serve.agent.capabilities.db import register_capability

    facade = ResourceFacade()
    register_capability(facade)
    legacy = _make_legacy_db()
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, _CapabilityDeclareAdapter)
    contribs = wrapped.declare()
    assert any("paydb" in c.content for c in contribs if isinstance(c.content, str))
    assert "db:42" in facade.executor_provider

# =========================================================================== #
# RFC-006 Phase B3: _resolve_db_from_agent 优先从 CapabilityPack 取连接
# =========================================================================== #
async def test_resolve_db_from_agent_prefers_capability_pack():
    """agent 有 capability_pack 含 DBCapability(db_name 匹配)→ 从其取 connector。"""
    from types import SimpleNamespace
    from derisk_serve.agent.capabilities.db.capability import DBCapability

    cap = DBCapability(db_name="paydb", db_id=42)
    cap._status = __import__("derisk.core.interface.resource.executor", fromlist=["ExecutorStatus"]).ExecutorStatus.READY
    fake_conn = MagicMock()
    cap._connector = fake_conn
    pack = SimpleNamespace(sub_resources=[cap])
    agent = SimpleNamespace(capability_pack=pack, resource_map={})

    from derisk_serve.agent.capabilities.db.tools._db_tools_impl import _resolve_db_from_agent
    conn, ds_id = _resolve_db_from_agent("paydb", {"agent": agent})
    assert conn is fake_conn
    assert ds_id == 42


async def test_resolve_db_from_agent_falls_back_to_resource_map():
    """capability_pack 无 db_name 匹配 → 回退旧 resource_map find DBResource。"""
    from types import SimpleNamespace
    from derisk.agent.resource.database import DBResource  # noqa: F401  (isinstance 用)

    # capability_pack 空或无 db 匹配
    pack = SimpleNamespace(sub_resources=[])
    agent = SimpleNamespace(capability_pack=pack, resource_map={})
    from derisk_serve.agent.capabilities.db.tools._db_tools_impl import _resolve_db_from_agent
    conn, ds_id = _resolve_db_from_agent("paydb", {"agent": agent})
    assert conn is None
    assert ds_id is None
