"""向后兼容重导出——协议本体已迁移至 ``derisk.core.interface.resource.protocol``,
LegacyResourceAdapter 迁移至 ``derisk.agent.capabilities.legacy_adapter``。

本模块保留以兼容现有 ``from derisk.agent.shared.prompt_assembly.resource_protocol import X``
导入路径。新代码:
- 协议本体(ResourceProtocol/ConsumerRegistry/apply_consumption)→ derisk.core.interface.resource.protocol
- 桥接(LegacyResourceAdapter)→ derisk.agent.capabilities.legacy_adapter
"""

from derisk.core.interface.resource.protocol import (  # noqa: F401
    ConsumerRegistry,
    ResourceProtocol,
    apply_consumption,
)
from derisk.agent.capabilities.legacy_adapter import (  # noqa: F401
    LegacyResourceAdapter,
)