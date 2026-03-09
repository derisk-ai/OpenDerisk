"""
Tools Module - 兼容层重定向

此模块已迁移到统一工具框架 `derisk.agent.tools`。

旧的导入路径:
    from derisk.core.tools import ToolBase, tool, ToolRegistry, ...
    
新的导入路径 (推荐):
    from derisk.agent.tools import ToolBase, tool, tool_registry, ...

此文件仅作为向后兼容层存在，新代码请使用统一框架。
"""

import warnings

warnings.warn(
    "derisk.core.tools 已迁移到 derisk.agent.tools，"
    "此兼容层将在未来版本移除",
    DeprecationWarning,
    stacklevel=2
)

# 从统一框架重新导出所有内容
from derisk.agent.tools.base import (
    ToolBase,
    ToolCategory,
    ToolRiskLevel as RiskLevel,
    ToolSource,
)

from derisk.agent.tools.metadata import (
    ToolMetadata,
    ToolDependency,
)

from derisk.agent.tools.result import ToolResult

from derisk.agent.tools.registry import (
    ToolRegistry,
    tool_registry,
    register_builtin_tools,
)

from derisk.agent.tools.decorators import (
    tool,
    shell_tool,
    file_read_tool,
    file_write_tool,
    network_tool,
    agent_tool,
    interaction_tool,
)

# 兼容旧版名称
RiskCategory = ToolCategory
AuthorizationRequirement = type('AuthorizationRequirement', (), {})
ToolParameter = type('ToolParameter', (), {})

# 兼容旧版 data_tool
data_tool = tool

__all__ = [
    # Metadata
    "ToolCategory",
    "RiskLevel",
    "RiskCategory",
    "AuthorizationRequirement",
    "ToolParameter",
    "ToolMetadata",
    # Base
    "ToolResult",
    "ToolBase",
    "ToolRegistry",
    "tool_registry",
    # Decorators
    "tool",
    "shell_tool",
    "file_read_tool",
    "file_write_tool",
    "network_tool",
    "data_tool",
    "agent_tool",
    "interaction_tool",
    # Builtin
    "register_builtin_tools",
]