"""
工具迁移模块

提供从旧工具体系到新框架的迁移功能：
- LocalTool迁移
- MCP工具迁移
- API工具迁移
"""

from .local_tool_adapter import (
    LocalToolWrapper,
    LocalToolMigrator,
    migrate_local_tools,
    local_tool_migrator,
)

__all__ = [
    "LocalToolWrapper",
    "LocalToolMigrator",
    "migrate_local_tools",
    "local_tool_migrator",
]