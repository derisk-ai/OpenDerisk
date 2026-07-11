"""DBExecutor —— 数据库执行投影(RFC-005 Step C)。

包装 connector + spec_service,提供:
- prepare:确保 connector 就绪(已由 build_resource 构造,轻量 no-op)。
- fetch(DataRequirement):据 kind 预取 declare 所需数据。
  - "db_prompt":get_db_stats→table_count→injection_mode 分级,返回分级后的表列表
    文本(SMALL/MEDIUM 注入 spec、LARGE 不注入发工具指引)。下沉旧
    resource_injector._get_database_table_list 的分级逻辑。
- execute(ExecutorCall):路由 DB 工具(execute_sql/get_table_spec/list_tables/
  search_tables)。当前工具体在 db_tools.py(系统注入路径),本 executor 先留
  execute 骨架,真正收编工具体为后续(本轮选B 工具仍走 builtin,executor 提供
  fetch + 数据访问底座)。

spec_service/DbSpecService 在 derisk-serve,本类用延迟导入,derisk-core 侧可定义。
"""

from __future__ import annotations

import logging
from typing import Any

from derisk.core.interface.resource.executor import (
    Executor,
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)
from derisk.core.interface.resource.data_requirement import (
    DataRequirement,
    InjectionMode,
    injection_mode_for_table_count,
)

logger = logging.getLogger(__name__)


class DBExecutor(Executor):
    """数据库执行投影:包装 connector,提供 fetch(分级 spec)+ execute(工具路由)。"""

    def __init__(self, connector: Any = None, datasource_id: Any = None, db_name: str = ""):
        self._connector = connector
        self._datasource_id = datasource_id
        self._db_name = db_name
        self.status = ExecutorStatus.UNINITIALIZED

    @property
    def executor_id(self) -> str:
        return f"db:{self._datasource_id}"

    async def prepare(self) -> None:
        # connector 由 build_resource 已构造;仅校验可访问
        self.status = ExecutorStatus.READY

    async def fetch(self, requirement: DataRequirement) -> Any:
        """预取 declare 所需数据。kind="db_prompt" 返回分级后表列表文本。"""
        if requirement.kind == "db_prompt":
            return await self._fetch_db_prompt(requirement)
        if requirement.kind == "db_stats":
            return await self._fetch_db_stats(requirement)
        raise NotImplementedError(f"unsupported fetch kind: {requirement.kind}")

    async def _fetch_db_prompt(self, requirement: DataRequirement) -> str:
        """据 table_count 分级返回表列表文本(下沉旧 injector 分级逻辑)。

        同步 I/O(spec_service/connector)一律经 asyncio.to_thread 异步化,不阻塞事件循环。
        """
        import asyncio

        ds_id = requirement.params.get("datasource_id", self._datasource_id)
        spec_service = self._get_spec_service()
        if spec_service is None or ds_id is None:
            # 无 spec_service(derisk-serve 不可用或无 spec),回退 connector 实时表名(异步)
            return await asyncio.to_thread(self._legacy_table_list_text)

        try:
            stats = await asyncio.to_thread(spec_service.get_db_stats, ds_id)
            table_count = stats.get("total_tables", 0)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db] get_db_stats failed: {e}")
            return await asyncio.to_thread(self._legacy_table_list_text)

        mode = injection_mode_for_table_count(table_count)
        if mode == InjectionMode.LARGE:
            # 大库:不注入表列表,发工具指引(对齐 LARGE_DB_GUIDANCE_TEMPLATE)
            return self._large_db_guidance(table_count, ds_id)
        # SMALL/MEDIUM:注入 spec(紧凑或全量),异步化
        try:
            spec_mode = "small" if mode == InjectionMode.SMALL else "medium"
            return await asyncio.to_thread(
                spec_service.format_db_spec_for_prompt, ds_id, mode=spec_mode
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db] format_db_spec failed: {e}")
            return await asyncio.to_thread(self._legacy_table_list_text)

    async def _fetch_db_stats(self, requirement: DataRequirement) -> dict:
        import asyncio
        spec_service = self._get_spec_service()
        if spec_service is None:
            return {"total_tables": 0}
        ds_id = requirement.params.get("datasource_id", self._datasource_id)
        try:
            return await asyncio.to_thread(spec_service.get_db_stats, ds_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db] get_db_stats failed: {e}")
            return {"total_tables": 0}

    def _large_db_guidance(self, table_count: int, ds_id: Any) -> str:
        return (
            f"<database-tables>\n该库规模较大(共 {table_count} 张表),未全量注入表列表。\n"
            f"请按需使用工具:get_table_spec(查表结构)、search_tables(按问题推荐相关表)、"
            f"list_tables(列全部表名)。\n</database-tables>"
        )

    def _legacy_table_list_text(self) -> str:
        """无 spec_service 时回退 connector 实时表名(对齐旧 _get_database_table_list_legacy)。"""
        if self._connector is None:
            return "<database-tables>(无法获取表列表)</database-tables>"
        try:
            names = self._connector.get_table_names()
            return "\n".join(f"- {t}" for t in (names or []))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db] connector.get_table_names failed: {e}")
            return "<database-tables>(无法获取表列表)</database-tables>"

    def _get_spec_service(self):
        """延迟加载 DbSpecService(derisk-serve)。core 测试环境不可用时返 None。"""
        try:
            from derisk_serve.datasource.service.spec_service import DbSpecService
            return DbSpecService()
        except Exception:  # noqa: BLE001
            return None

    async def execute(self, call: ExecutorCall) -> Any:
        """路由 DB 工具。本轮选B:工具仍走 builtin(系统注入),executor 留骨架。

        真正收编(execute_sql/get_table_spec/list_tables/search_tables 调用体)
        为后续任务;当前 executor 主要提供 fetch(declare 数据预取)。
        """
        raise NotImplementedError(
            f"DBExecutor.execute({call.tool_name}) 待收编(本轮工具走 builtin)"
        )

    async def release(self, reason: ReleaseReason) -> None:
        # connector 由 db_manager 管理生命周期,此处不关闭共享 connector
        self.status = ExecutorStatus.RELEASED