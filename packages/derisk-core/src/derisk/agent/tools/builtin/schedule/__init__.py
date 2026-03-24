"""
Schedule tools - 调度工具模块

提供定时任务创建功能：
- CreateCronJobTool: 创建定时任务
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_schedule_tools(registry: "ToolRegistry") -> None:
    """注册调度工具"""
    from .create_cron_job import CreateCronJobTool

    registry.register(CreateCronJobTool())


__all__ = ["register_schedule_tools", "CreateCronJobTool"]
