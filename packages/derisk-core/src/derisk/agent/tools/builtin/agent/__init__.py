"""Agent工具模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_agent_tools(registry: 'ToolRegistry') -> None:
    """注册Agent相关工具"""
    from .agent_tools import (
        KnowledgeTool,
    )
    from ...base import ToolSource

    registry.register(KnowledgeTool(), source=ToolSource.CORE)
