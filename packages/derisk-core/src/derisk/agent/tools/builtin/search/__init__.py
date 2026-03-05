"""搜索工具模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_search_tools(registry: 'ToolRegistry') -> None:
    """注册搜索工具"""
    pass