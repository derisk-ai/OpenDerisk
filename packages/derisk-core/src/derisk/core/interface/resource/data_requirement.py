"""data_requirement 契约与大库降级(RFC-005 S7)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class InjectionMode(str, Enum):
    """DB 表列表注入模式(对齐现 datasource/service/injection_config)。"""

    SMALL = "small"    # <SMALL_THRESHOLD:完整列表(含摘要)注入 system
    MEDIUM = "medium"  # 中规模:紧凑列表(仅名称)注入 system
    LARGE = "large"    # >=MEDIUM_THRESHOLD:不注入表列表,仅统计 + 工具指引
    # LARGE 模式下,表列表改为 data_requirement,由执行投影按需拉取(get_table_spec)

# 阈值(对齐 injection_config 默认值;可由接入层按 env 覆盖)
SMALL_DB_THRESHOLD = 100
MEDIUM_DB_THRESHOLD = 500


def injection_mode_for_table_count(
    table_count: int,
    *,
    small_threshold: int = SMALL_DB_THRESHOLD,
    medium_threshold: int = MEDIUM_DB_THRESHOLD,
) -> InjectionMode:
    """据表数量决定注入模式(S7)。

    <small_threshold → SMALL(全量注入 system)
    <medium_threshold → MEDIUM(紧凑注入)
    >=medium_threshold → LARGE(不注入,按需拉取)

    纯函数,可被 declare 内部调用决定 Contribution 内容。
    """
    if table_count < small_threshold:
        return InjectionMode.SMALL
    if table_count < medium_threshold:
        return InjectionMode.MEDIUM
    return InjectionMode.LARGE


@dataclass(frozen=True)
class DataRequirement:
    """declare 声明的数据需求(S7):由执行投影层预取后回填declare。

    declare 是纯函数无 I/O;需外部数据(如 DB schema)时,declare 产出
    DataRequirement,执行投影层据此预取并回填,declare 再据回填数据
    决定注入模式(LARGE 则不塞表列表)。
    """

    executor_id: str              # 数据来源 executor(如 DB 连接器)
    capability_id: str
    kind: str                     # 需求数据类型,如 "db_table_spec"
    params: Dict[str, Any] = field(default_factory=dict)
    # 如 db: {"datasource_id": "...", "mode_hint": "auto"}