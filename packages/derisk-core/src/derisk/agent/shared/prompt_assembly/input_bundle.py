"""输入载体契约——向后兼容重导出。

协议契约已迁移至 ``derisk.core.interface.input``(与 llm.py 同级,符合
RFC-005「协议接口在 core」的分层要求)。本模块保留以兼容现有导入路径。
"""

from derisk.core.interface.input import (  # noqa: F401
    SCOPE_PRIORITY,
    CacheControlPoint,
    CacheScope,
    Contribution,
    FrozenBundle,
    InputBundle,
    Lifetime,
    Slot,
    SystemBlock,
    is_valid_lifetime_cache_scope,
)

__all__ = [
    "SCOPE_PRIORITY",
    "CacheControlPoint",
    "CacheScope",
    "Contribution",
    "FrozenBundle",
    "InputBundle",
    "Lifetime",
    "Slot",
    "SystemBlock",
    "is_valid_lifetime_cache_scope",
]