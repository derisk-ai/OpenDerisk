"""Capabilities —— 资源能力编排层 + capability 自管目录(RFC-005)。

组织原则：一个资源一个扩展目录，自管协议+工具+executor。
Agent 不强引用任何具体 capability 类型,只依赖协议接口,扫描注册即用。

分层:
- core 层(capabilities/{sandbox,memory,mock}):纯 core,不连 serve 服务。
- serve 层(derisk_serve.agent.capabilities.{db,knowledge,app,skill,mcp,playbook}):
  连 serve 服务(spec_service/PlaybookService/SkillService 等)。
- facade 动态发现两层 capabilities 包目录,调用各 register_wrappers 注册。
"""

from derisk.core.interface.resource.capability import Capability  # noqa: F401
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
from .registry import (  # noqa: F401
    CapabilityRegistry,
    get_default_registry,
)

__all__ = [
    "Capability",
    "ConsumerRegistry",
    "ResourceProtocol",
    "apply_consumption",
    "AgentInputsSnapshot",
    "ResourceFacade",
    "compute_config_hash",
    "CapabilityRegistry",
    "get_default_registry",
]