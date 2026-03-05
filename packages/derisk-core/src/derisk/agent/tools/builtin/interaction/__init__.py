"""交互工具模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_interaction_tools(registry: 'ToolRegistry') -> None:
    """注册交互工具"""
    pass