"""Capabilities —— 资源能力编排层 + capability 自管目录(RFC-005)。

组织原则:**一个资源一个扩展目录,自管协议+工具+executor**。
- 协议契约在 ``derisk.core.interface.resource``。
- 本包是编排层:facade(产快照)、registry(capability 发现)、legacy_adapter(过渡)。
- 每个 capability 一个自管子目录(如 ``sandbox/``),内含 declare + 自有工具 + executor。

新增 capability = 新建一个目录 + 实现 register(),零改其它。
"""

from derisk.core.interface.resource.protocol import (  # noqa: F401
    ConsumerRegistry,
    ResourceProtocol,
    apply_consumption,
)
from .facade import (  # noqa: F401
    AgentInputsSnapshot,
    ResourceFacade,
    compute_config_hash,
)
from .legacy_adapter import LegacyResourceAdapter  # noqa: F401
from .registry import (  # noqa: F401
    CapabilityRegistry,
    get_default_registry,
)

__all__ = [
    "ConsumerRegistry",
    "ResourceProtocol",
    "apply_consumption",
    "AgentInputsSnapshot",
    "ResourceFacade",
    "compute_config_hash",
    "LegacyResourceAdapter",
    "CapabilityRegistry",
    "get_default_registry",
]