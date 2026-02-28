"""工具函数模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_utility_tools(registry: 'ToolRegistry') -> None:
    """注册工具函数"""
    pass