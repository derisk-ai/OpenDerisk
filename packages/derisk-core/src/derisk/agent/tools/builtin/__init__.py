"""
内置工具模块

提供核心工具：
- 文件系统工具 (read, write, edit, glob, grep)
- Shell工具 (bash, python)
- 搜索工具 (search, find)
- 交互工具 (question, confirm)
- 工具函数 (calculate, datetime)
- Agent工具 (browser, sandbox, terminate, knowledge, kanban, todo)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..registry import ToolRegistry


def register_all(registry: 'ToolRegistry') -> None:
    """注册所有内置工具"""
    from .file_system import register_file_tools
    from .shell import register_shell_tools
    from .search import register_search_tools
    from .interaction import register_interaction_tools
    from .utility import register_utility_tools
    from .agent import register_agent_tools
    
register_file_tools(registry)
    register_shell_tools(registry)
    register_search_tools(registry)
    register_interaction_tools(registry)
    register_utility_tools(registry)
    register_agent_tools(registry)