"""
Prompt Assembly Module - 通用 Prompt 组装模块

提供分层 Prompt 组装能力。

核心组件：
1. PromptRegistry - 模板注册表（支持文件加载和内存注册）
2. PromptAssembler - 身份层 + 控制层 + 用户 prompt 组装器

注:资源层(sandbox/db/skill/knowledge 声明)已迁移至 RFC-005 ResourceFacade
(derisk.agent.capabilities.facade)。ResourceInjector / LegacyResourceAdapter
(存量桥接)随全量迁移已删除。

设计原则：
- 通用性：内容各自定义
- 兼容性：身份/控制层仍可独立组装，资源层经 facade
- 可扩展：支持自定义模板目录
"""

from .prompt_registry import (
    PromptRegistry,
    PromptTemplate,
    get_registry,
    register_template,
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

__all__ = [
    # Registry
    "PromptRegistry",
    "PromptTemplate",
    "get_registry",
    "register_template",
    # Assembler
    "PromptAssembler",
    "PromptAssemblyConfig",
    "create_prompt_assembler",
    # InputBundle (RFC-005,向后兼容 re-export)
    "CacheControlPoint",
    "CacheScope",
    "Contribution",
    "FrozenBundle",
    "InputBundle",
    "Lifetime",
    "Slot",
    "SystemBlock",
]