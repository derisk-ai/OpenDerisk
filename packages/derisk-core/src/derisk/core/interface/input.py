"""向后兼容重导出——协议契约已迁移至 ``derisk.core.interface.resource`` 子包。

RFC-005 协议契约按职责拆分到 resource/{bundle,tool_entry,data_requirement}.py。
本模块保留以兼容现有 ``from derisk.core.interface.input import X`` 导入路径。
新代码请直接从 ``derisk.core.interface.resource.*`` 导入。
"""

from derisk.core.interface.resource.bundle import (  # noqa: F401
    SCOPE_PRIORITY,
    AnthropicSystemBlock,
    CacheControlPoint,
    CacheScope,
    Contribution,
    FrozenBundle,
    InputBundle,
    Lifetime,
    Slot,
    SystemBlock,
    is_valid_lifetime_cache_scope,
    to_anthropic_system,
    to_legacy_system_message,
)
from derisk.core.interface.resource.data_requirement import (  # noqa: F401
    DataRequirement,
    InjectionMode,
    MEDIUM_DB_THRESHOLD,
    SMALL_DB_THRESHOLD,
    injection_mode_for_table_count,
)
from derisk.core.interface.resource.tool_entry import (  # noqa: F401
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)