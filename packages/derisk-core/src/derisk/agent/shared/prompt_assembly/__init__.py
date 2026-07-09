"""
Prompt Assembly Module - 通用 Prompt 组装模块

提供分层 Prompt 组装能力。

核心组件：
1. PromptRegistry - 模板注册表（支持文件加载和内存注册）
2. ResourceInjector - 资源注入器（通用接口）
3. PromptAssembler - 分层组装器（含新旧兼容）

设计原则：
- 通用性：内容各自定义
- 兼容性：智能检测新旧模式，自动适配
- 可扩展：支持自定义模板目录和注入逻辑
"""

from .prompt_registry import (
    PromptRegistry,
    PromptTemplate,
    get_registry,
    register_template,
)
from .resource_injector import (
    ResourceInjector,
    ResourceContext,
    ResourceType,
    create_resource_injector,
)
from .prompt_assembler import (
    PromptAssembler,
    PromptAssemblyConfig,
    create_prompt_assembler,
)
from .input_bundle import (  # noqa: E402
    CacheControlPoint,
    CacheScope,
    Contribution,
    FrozenBundle,
    InputBundle,
    Lifetime,
    Slot,
    SystemBlock,
)
from .resource_protocol import (  # noqa: E402
    LegacyResourceAdapter,
    ResourceProtocol,
)
from .resource_facade import (  # noqa: E402
    AgentInputsSnapshot,
    ResourceFacade,
    compute_config_hash,
)
from .sandbox_resource import SandboxResource  # noqa: E402
from .resource_protocol import ConsumerRegistry, apply_consumption  # noqa: E402

__all__ = [
    # Registry
    "PromptRegistry",
    "PromptTemplate",
    "get_registry",
    "register_template",
    # Resource Injector
    "ResourceInjector",
    "ResourceContext",
    "ResourceType",
    "create_resource_injector",
    # Assembler
    "PromptAssembler",
    "PromptAssemblyConfig",
    "create_prompt_assembler",
    # InputBundle (RFC-005)
    "CacheControlPoint",
    "CacheScope",
    "Contribution",
    "FrozenBundle",
    "InputBundle",
    "Lifetime",
    "Slot",
    "SystemBlock",
    # ResourceProtocol (RFC-005 §3.3 / S2)
    "LegacyResourceAdapter",
    "ResourceProtocol",
    # ResourceFacade (RFC-005 §3.6 / S9)
    "AgentInputsSnapshot",
    "ResourceFacade",
    "compute_config_hash",
]
