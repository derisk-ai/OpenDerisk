"""
Todo tools - 任务列表工具模块

提供任务列表管理功能：
- TodowriteTool: 创建/更新任务列表
- TodoreadTool: 读取任务列表状态
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_todo_tools(registry: "ToolRegistry") -> None:
    """注册 Todo 工具"""
    from .todowrite import TodowriteTool
    from .todoread import TodoreadTool

    registry.register(TodowriteTool())
    registry.register(TodoreadTool())


__all__ = ["register_todo_tools", "TodowriteTool", "TodoreadTool"]
