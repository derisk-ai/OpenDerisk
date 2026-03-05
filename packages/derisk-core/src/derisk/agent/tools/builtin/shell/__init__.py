"""Shell工具模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_shell_tools(registry: 'ToolRegistry') -> None:
    """注册Shell工具"""
    from .bash import BashTool
    from ...base import ToolSource
    
    registry.register(BashTool(), source=ToolSource.CORE)