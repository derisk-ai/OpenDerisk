"""DBCapabilityResource —— 数据库 capability 输入投影(RFC-005 Step C)。

DB 资源有 I/O(表列表来自 spec_service/connector),declare 纯函数化方案:
- declare 产【库基本信息】(纯,配置态 db_name/db_type/dialect)+ 【表列表占位】
  (DataRequirement,kind="db_prompt")。
- facade 经 Executor.fetch 预取回填:DBExecutor 内部 get_db_stats→injection_mode
  分级(SMALL/MEDIUM 注入 spec、LARGE 不注入发工具指引)→ 返回渲染好的文本,
  facade 替换占位 Contribution.content。
- 分级逻辑下沉到 executor(有 I/O),declare 仍纯(只声明需求 + 基本信息)。

双轨:包装旧 DatasourceResource(由 build_resource 构建进 ResourcePack),declare
委托旧实例属性 + 经 DataRequirement 触发 executor 预取。使 DB 脱离 legacy 桥接
+ resource_injector 类名硬匹配。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.data_requirement import DataRequirement
from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)


class DBCapabilityResource(ResourceProtocol):
    """数据库 capability:declare 库基本信息 + 表列表占位(DataRequirement)。

    capability_id="db"。executor_id 形如 "db:{datasource_id}",由 register_wrappers
    时据旧实例 _datasource_id 决定,DBExecutor 在 executor_provider 注册同 id。
    """

    capability_id = "db"
    protocol_version = 1

    def __init__(self, legacy_instance: Any = None):
        self._legacy = legacy_instance

    def declare(self, config: Any = None) -> List[Contribution]:
        """实例 declare:委托 declare_db 产库基本信息 + 表列表占位(DataRequirement)。"""
        return self.declare_db()

    def declare_db(self) -> List[Contribution]:
        """实例方法:产库基本信息 + 表列表占位(DataRequirement)。"""
        if self._legacy is None:
            return []
        contribs: List[Contribution] = []

        # 1. 库基本信息(纯,配置态属性)
        basic_text = self._build_basic_info()
        if basic_text:
            contribs.append(
                Contribution(
                    capability_id=self.capability_id,
                    slot=Slot.SYSTEM,
                    content=basic_text,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.ENV,  # 本会话 DB 环境
                    order=40,
                )
            )

        # 2. 表列表占位(DataRequirement,由 facade→DBExecutor.fetch 回填为分级后的文本)
        ds_id = self._resolve_datasource_id()
        if ds_id is not None:
            req = DataRequirement(
                executor_id=f"db:{ds_id}",
                capability_id=self.capability_id,
                kind="db_prompt",
                params={
                    "datasource_id": ds_id,
                    "db_name": self._legacy_db_name(),
                    "mode_hint": "auto",  # executor 据 table_count 自动分级
                },
            )
            contribs.append(
                Contribution(
                    capability_id=self.capability_id,
                    slot=Slot.SYSTEM,
                    content=req,  # 占位,facade 回填为分级后表列表/工具指引
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.ENV,
                    order=41,
                )
            )
        return contribs

    def _build_basic_info(self) -> str:
        """库基本信息文本(db_name/db_type/dialect),纯配置态。"""
        db_name = self._legacy_db_name()
        db_type = getattr(self._legacy, "_db_type", "") or ""
        dialect = getattr(self._legacy, "_dialect", "") or db_type
        if not db_name:
            return ""
        lines = [f"<database>", f"  <name>{db_name}</name>"]
        if db_type:
            lines.append(f"  <db_type>{db_type}</db_type>")
        if dialect and dialect != db_type:
            lines.append(f"  <dialect>{dialect}</dialect>")
        lines.append("</database>")
        return "\n".join(lines)

    def _legacy_db_name(self) -> str:
        return getattr(self._legacy, "_db_name", "") or getattr(self._legacy, "db_name", "") or ""

    def _resolve_datasource_id(self) -> Optional[Any]:
        try:
            return self._legacy._resolve_datasource_id()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[db] resolve datasource_id failed: {e}")
            return getattr(self._legacy, "_datasource_id", None)

    def requires(self, config: Any = None) -> List[str]:
        ds_id = self._resolve_datasource_id()
        return [f"db:{ds_id}"] if ds_id is not None else []