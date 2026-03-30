"""
Schedule tools - 调度工具模块

提供定时任务管理功能：
- CreateCronJobTool: 创建定时任务
- ListCronJobsTool: 列出定时任务
- DeleteCronJobTool: 删除定时任务
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...registry import ToolRegistry


def register_schedule_tools(registry: "ToolRegistry") -> None:
    """注册调度工具"""
    from .create_cron_job import CreateCronJobTool
    from .list_cron_jobs import ListCronJobsTool
    from .delete_cron_job import DeleteCronJobTool

    registry.register(CreateCronJobTool())
    registry.register(ListCronJobsTool())
    registry.register(DeleteCronJobTool())


__all__ = [
    "register_schedule_tools",
    "CreateCronJobTool",
    "ListCronJobsTool",
    "DeleteCronJobTool",
]
