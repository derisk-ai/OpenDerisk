"""Agent工具模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_agent_tools(registry: 'ToolRegistry') -> None:
    """注册Agent相关工具"""
    from .agent_tools import (
        BrowserTool,
        SandboxTool,
        TerminateTool,
        KnowledgeTool,
        KanbanTool,
        TodoTool,
    )
    from ...base import ToolSource
    
    registry.register(BrowserTool(), source=ToolSource.CORE)
    registry.register(SandboxTool(), source=ToolSource.CORE)
    registry.register(TerminateTool(), source=ToolSource.CORE)
    registry.register(KnowledgeTool(), source=ToolSource.CORE)
    registry.register(KanbanTool(), source=ToolSource.CORE)
    registry.register(TodoTool(), source=ToolSource.CORE)