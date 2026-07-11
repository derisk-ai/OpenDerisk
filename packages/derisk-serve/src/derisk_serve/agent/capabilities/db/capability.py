"""DBCapability —— 数据库自管理资源能力(RFC-006 Stage 6,折中方案)。

DB 体现自管理 prepare(建连接)+ fetch(填 spec)+ declare(注入库信息)+ release:
- **prepare**:把 `DatasourceResource.__init__:134` 的 `CFG.local_db_manager.get_connector`
  建连接逻辑挪来,存 self._connector/_datasource_id/_db_type/_dialect。懒 resolve ds_id
  (缺则查 ConnectConfigDao)。同步 I/O 经 asyncio.to_thread 异步化。
- **declare**:库基本信息(纯配置态文本)+ 表列表占位(DataRequirement,由 fetch 回填)。
  复用 db/resource.py 的 _build_basic_info / declare_db 形态。
- **fetch**:复刻 DBExecutor._fetch_db_prompt 分级(据 table_count:SMALL/MEDIUM 注入 spec、
  LARGE 发工具指引;无 spec_service 回退 connector 表名)。异步化。
- **release**:no-op(connector 由 db_manager 管生命周期)。

**折中(经用户确认)**:DB execute 不走 Route B。原因:DB 工具是无状态多库设计
(`execute_sql(db_name, sql, ...)` 靠 db_name 参数选库,工具名跨库共享),与 Route B
"tool_name→静态 executor_id"模型冲突(多库时一个 tool_name 要对应多 executor)。
故 DBCapability 自管 prepare/fetch/declare/release,工具暂留 Route A(builtin),
但运行时从 agent 持有的 DBCapability 实例取 connector(取代 _resolve_db_from_agent
扫 resource_map)——接入见 DBCapability.get_connector + _resolve_db_from_agent 增配。
execute() 抛 NotImplementedError(占位)。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.data_requirement import (
    DataRequirement,
    InjectionMode,
    injection_mode_for_table_count,
)
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

logger = logging.getLogger(__name__)


class DBCapability(Capability):
    """数据库自管理能力:持有 live connector,管生命周期 + declare + fetch。

    capability_id="db:{datasource_id}";executor_id 同。一个 agent 绑多库 →
    多个 DBCapability 实例(各持各连接)。
    """

    def __init__(
        self,
        db_name: str,
        db_id: Any = None,
        db_type: str = "",
        dialect: str = "",
    ):
        self._db_name = db_name
        self._db_id = db_id
        self._datasource_id: Any = db_id
        self._db_type = db_type
        self._dialect = dialect or db_type
        self._connector: Any = None
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "DBCapability":
        """从 AgentResource.value dict 构造(不建连接;prepare 时建)。

        value 形如 {"db_name":..., "db_id":...}。无 I/O。
        """
        value = value or {}
        return cls(
            db_name=value.get("db_name") or value.get("name") or "",
            db_id=value.get("db_id") or value.get("id"),
        )

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "DBCapability":
        """从旧 DatasourceResource/RDBMSConnectorResource 实例构造(过渡期,Stage 4.5/6)。

        读旧实例属性(db_name/_db_type/_dialect/_datasource_id);连接器若旧实例已建
        则直接复用(避免重复建连接),否则 prepare 时建。无新增 I/O。
        """
        db_name = (
            getattr(legacy_instance, "_db_name", None)
            or getattr(legacy_instance, "db_name", None)
            or ""
        )
        db_id = getattr(legacy_instance, "_datasource_id", None) or getattr(
            legacy_instance, "_db_id", None
        )
        cap = cls(
            db_name=db_name,
            db_id=db_id,
            db_type=getattr(legacy_instance, "_db_type", "") or "",
            dialect=getattr(legacy_instance, "_dialect", "") or "",
        )
        # 复用旧实例已建的 connector(过渡期:旧 DatasourceResource.__init__ 已建好)
        conn = getattr(legacy_instance, "_connector", None) or getattr(
            legacy_instance, "connector", None
        )
        if conn is not None:
            cap._connector = conn
            cap._status = ExecutorStatus.READY  # 已就绪,prepare 将幂等
        return cap

    @property
    def capability_id(self) -> str:
        return f"db:{self._datasource_id}" if self._datasource_id is not None else "db"

    @property
    def executor_id(self) -> str:
        return self.capability_id

    # ----------------------------- 给 Route A 工具取连接(折中接入) ---------- #
    def get_connector(self) -> Any:
        """供 Route A DB 工具取 live connector(取代 _resolve_db_from_agent 扫 resource_map)。

        DBCapability 经 facade legacy provider 翻转后,工具按 db_name 从 agent 持有的
        DBCapability 实例取 connector。需 agent 把 DBCapability 实例登记到可查处
        (接入见 react_master/facade;本方法提供取连接口)。
        """
        return self._connector

    @property
    def db_name(self) -> str:
        return self._db_name

    @property
    def datasource_id(self) -> Any:
        return self._datasource_id

    # ----------------------------- 输入投影(declare 纯 + 占位) ------------- #
    def declare(self, config: Any = None) -> List[Contribution]:
        """库基本信息(纯文本)+ 表列表占位(DataRequirement,fetch 回填)。"""
        contribs: List[Contribution] = []
        basic_text = self._build_basic_info()
        if basic_text:
            contribs.append(
                Contribution(
                    capability_id=self.capability_id,
                    slot=Slot.SYSTEM,
                    content=basic_text,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.ENV,
                    order=40,
                )
            )
        ds_id = self._datasource_id
        if ds_id is not None:
            req = DataRequirement(
                executor_id=self.executor_id,
                capability_id=self.capability_id,
                kind="db_prompt",
                params={
                    "datasource_id": ds_id,
                    "db_name": self._db_name,
                    "mode_hint": "auto",
                },
            )
            contribs.append(
                Contribution(
                    capability_id=self.capability_id,
                    slot=Slot.SYSTEM,
                    content=req,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.ENV,
                    order=41,
                )
            )
        return contribs

    def _build_basic_info(self) -> str:
        if not self._db_name:
            return ""
        lines = [f"<database>", f"  <name>{self._db_name}</name>"]
        if self._db_type:
            lines.append(f"  <db_type>{self._db_type}</db_type>")
        if self._dialect and self._dialect != self._db_type:
            lines.append(f"  <dialect>{self._dialect}</dialect>")
        lines.append("</database>")
        return "\n".join(lines)

    # ----------------------------- 生命周期(prepare 建连接,I/O) ---------- #
    async def prepare(self) -> None:
        """建 live connector(挪自 DatasourceResource.__init__:134)。幂等。

        同步建连接经 asyncio.to_thread 异步化;懒 resolve datasource_id(缺则查
        ConnectConfigDao)。from_legacy 复用了旧实例 connector 时直接就绪。
        """
        if self._connector is not None:
            self._status = ExecutorStatus.READY
            return
        if not self._db_name:
            self._status = ExecutorStatus.READY
            return
        try:
            self._connector = await asyncio.to_thread(self._build_connector)
            # 从 connector 回取 db_type/dialect(若 config 未提供)
            if not self._db_type:
                self._db_type = getattr(self._connector, "db_type", "") or ""
            if not self._dialect:
                self._dialect = getattr(self._connector, "dialect", "") or self._db_type
            if self._datasource_id is None:
                await asyncio.to_thread(self._lazy_resolve_datasource_id)
            self._status = ExecutorStatus.READY
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db-capability] prepare connector for {self._db_name} failed: {e}")
            self._status = ExecutorStatus.FAILED

    def _build_connector(self):
        from derisk._private.config import Config

        return Config().local_db_manager.get_connector(self._db_name, db_id=self._db_id)

    def _lazy_resolve_datasource_id(self) -> None:
        """若无 db_id,查 ConnectConfigDao.get_by_names(db_name) 补 datasource_id。"""
        try:
            from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao

            entity = ConnectConfigDao().get_by_names(self._db_name)
            if entity:
                self._datasource_id = entity.id
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[db-capability] lazy resolve datasource_id failed: {e}")

    # ----------------------------- fetch(填 DataRequirement,异步) -------- #
    async def fetch(self, requirement: DataRequirement) -> Any:
        if requirement.kind == "db_prompt":
            return await self._fetch_db_prompt(requirement)
        raise NotImplementedError(f"[db-capability] unsupported fetch kind: {requirement.kind}")

    async def _fetch_db_prompt(self, requirement: DataRequirement) -> str:
        """据 table_count 分级返回表列表文本(复刻 DBExecutor._fetch_db_prompt)。"""
        ds_id = requirement.params.get("datasource_id", self._datasource_id)
        spec_service = self._get_spec_service()
        if spec_service is None or ds_id is None:
            return await asyncio.to_thread(self._legacy_table_list_text)
        try:
            stats = await asyncio.to_thread(spec_service.get_db_stats, ds_id)
            table_count = stats.get("total_tables", 0)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db-capability] get_db_stats failed: {e}")
            return await asyncio.to_thread(self._legacy_table_list_text)
        mode = injection_mode_for_table_count(table_count)
        if mode == InjectionMode.LARGE:
            return self._large_db_guidance(table_count, ds_id)
        try:
            spec_mode = "small" if mode == InjectionMode.SMALL else "medium"
            return await asyncio.to_thread(
                spec_service.format_db_spec_for_prompt, ds_id, mode=spec_mode
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db-capability] format_db_spec failed: {e}")
            return await asyncio.to_thread(self._legacy_table_list_text)

    def _get_spec_service(self):
        try:
            from derisk_serve.datasource.service.spec_service import DbSpecService

            return DbSpecService()
        except Exception:  # noqa: BLE001
            return None

    def _large_db_guidance(self, table_count: int, ds_id: Any) -> str:
        return (
            f"<database-tables>\n该库规模较大(共 {table_count} 张表),未全量注入表列表。\n"
            f"请按需使用工具:get_table_spec(查表结构)、search_tables(按问题推荐相关表)、"
            f"list_tables(列全部表名)。\n</database-tables>"
        )

    def _legacy_table_list_text(self) -> str:
        if self._connector is None:
            return "<database-tables>(无法获取表列表)</database-tables>"
        try:
            names = self._connector.get_table_names()
            return "\n".join(f"- {t}" for t in (names or []))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db-capability] connector.get_table_names failed: {e}")
            return "<database-tables>(无法获取表列表)</database-tables>"

    # ----------------------------- execute(折中:不走 Route B) ------------ #
    async def execute(self, call: ExecutorCall) -> Any:
        # DB 工具无状态多库(靠 db_name 参数选库),与 Route B 静态 executor 绑定冲突。
        # 工具暂走 Route A builtin,运行时从 DBCapability.get_connector() 取连接。
        raise NotImplementedError(
            "DBCapability.execute 不走 Route B —— DB 工具无状态多库,暂走 builtin Route A"
        )

    async def release(self, reason: ReleaseReason) -> None:
        # connector 由 db_manager 管生命周期,不在此关闭共享 connector。
        self._status = ExecutorStatus.RELEASED