"""输入载体契约——向后兼容重导出。

协议契约已迁移至 ``derisk.core.interface.resource.bundle``。本模块保留以兼容
现有 ``from derisk.agent.shared.prompt_assembly.input_bundle import X`` 导入路径。
"""

from derisk.core.interface.resource.bundle import (  # noqa: F401
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