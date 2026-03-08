"""
Tool Decorators - 兼容层重定向

此模块已迁移到统一工具框架。
所有装饰器现在从 derisk.agent.tools.decorators 导入。

旧的导入路径:
    from derisk.core.tools.decorators import tool, shell_tool, ...

新的导入路径 (推荐):
    from derisk.agent.tools import tool, shell_tool, ...

此文件仅作为向后兼容层存在，新代码请使用统一框架。
"""

# 从统一框架重新导出所有装饰器
from derisk.agent.tools.decorators import (
    tool,
    derisk_tool,
    system_tool,
    sandbox_tool,
    shell_tool,
    file_read_tool,
    file_write_tool,
    network_tool,
    agent_tool,
    interaction_tool,
)

# 为了向后兼容，也导出旧的名称
__all__ = [
    "tool",
    "derisk_tool",
    "system_tool",
    "sandbox_tool",
    "shell_tool",
    "file_read_tool",
    "file_write_tool",
    "network_tool",
    "agent_tool",
    "interaction_tool",
]

# 弃用警告
import warnings

warnings.warn(
    "derisk.core.tools.decorators 已弃用，请使用 derisk.agent.tools.decorators",
    DeprecationWarning,
    stacklevel=2,
)
