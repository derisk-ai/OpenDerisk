"""DB capability 自管工具(RFC-005,serve 层)。

DB 工具(execute_sql/get_table_spec/list_tables/search_tables)连 serve 的
spec_service/connector,故放 serve 层(避免 core→serve 反向依赖)。

工具实现在此目录 _db_tools_impl.py(@tool 装饰器实例化),
本模块职责:导入 _db_tools_impl 触发 @tool 注册 + 重设 4 个工具的
metadata.capability_id="db",使其归 DB capability(供 facade 按 capability
归类 + ToolDispatcher 路由)。归属逻辑在此收口,不改 _db_tools_impl 实现。
"""

import logging

logger = logging.getLogger(__name__)

DB_TOOL_NAMES = ["get_table_spec", "execute_sql", "list_tables", "search_tables"]


def register_db_tools_capability(registry=None) -> int:
    """导入 db_tools 触发 @tool 注册,并把 4 个工具 metadata.capability_id 设 "db"。

    Args:
        registry: ToolRegistry(可选;默认用全局 tool_registry)。

    Returns:
        成功设 capability_id 的工具数。
    """
    # 导入 db 工具实现触发 @tool 装饰器自动注册到 tool_registry
    # (实现从 derisk_serve.agent.resource.db_tools 迁移到本目录 _db_tools_impl)
    try:
        import derisk_serve.agent.capabilities.db.tools._db_tools_impl  # noqa: F401
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[db.tools] import _db_tools_impl failed: {e}")
        return 0

    if registry is None:
        try:
            from derisk.agent.tools.registry import tool_registry
            registry = tool_registry
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db.tools] get tool_registry failed: {e}")
            return 0

    count = 0
    for name in DB_TOOL_NAMES:
        tool = registry.get(name)
        if tool is None:
            logger.debug(f"[db.tools] tool {name} not in registry, skip")
            continue
        try:
            tool.metadata.capability_id = "db"
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db.tools] set capability_id for {name} failed: {e}")
    return count


def register(registry) -> None:
    """被 CapabilityRegistry.discover 调用的统一注册入口。"""
    register_db_tools_capability(registry)