"""DB capability —— 数据库能力自管目录(RFC-005 / RFC-006 Stage 6,serve 层)。

DB 资源连 serve 服务(spec_service/connector),整体在 serve 层自管:
- resource.py: DBCapabilityResource(declare 库基本信息 + DataRequirement 占位)[旧 wrapper]
- capability.py: DBCapability(自管理 prepare/fetch/declare/release)[RFC-006]
- executor.py: DBExecutor(fetch 分级 spec,连 serve spec_service,异步)[旧,Stage 9 删]
- tools/: execute_sql/get_table_spec/list_tables/search_tables(capability_id="db")

register_wrappers: 纯属性谓词(无 serve 类型 import),注册旧 DB Resource → DBCapabilityResource[旧]。
register_capability(RFC-006 Stage 6):注册旧 DB Resource → DBCapability(自管理)过渡 provider,
使 facade 遍历旧 ResourcePack 时翻成 DBCapability(prepare 建连接 + fetch 填 spec + declare
注入库信息)。工具暂走 Route A builtin,运行时从 DBCapability 实例取 connector(折中,见
capability.py docstring)。
"""

def register(registry) -> None:
    pass


def _is_db_legacy(sub) -> bool:
    """纯谓词:识别 DB 资源(鸭式属性)。"""
    return hasattr(sub, "_db_name") and hasattr(sub, "_connector")


def register_wrappers(facade) -> None:
    """注册 db capability 双轨 wrapper 到 facade(旧路径,RFC-005)。"""
    from .resource import DBCapabilityResource
    facade.register_legacy_wrapper(
        _is_db_legacy,
        lambda legacy: DBCapabilityResource(legacy_instance=legacy),
    )


def build_capability(value, system_app=None):
    """RFC-006 Stage 6:从 AgentResource.value dict 构造 DBCapability(不建连接;prepare 时建)。"""
    from .capability import DBCapability
    return DBCapability.from_config(value, system_app)


def register_capability(facade) -> None:
    """RFC-006 Stage 6:注册 db config factory + 旧实例→DBCapability 过渡 provider。

    旧 DatasourceResource 实例(已建 connector)经 provider 翻成 DBCapability(from_legacy
    复用其 connector),declare 出库基本信息 + DataRequirement,facade fetch 回填分级 spec。
    type_key="datasource"(AgentResource.type 别名)。
    """
    from .capability import DBCapability
    facade.register_capability_factory("datasource", build_capability)
    facade.register_legacy_capability_provider(_is_db_legacy, DBCapability.from_legacy)


# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "datasource"


def register_capability_to(registry) -> None:
    """注册 build_capability 到 CapabilityFactoryRegistry(构造期产 CapabilityPack)。"""
    registry.register(CAPABILITY_TYPE_KEY, build_capability)
