"""
异步任务工具模块

提供后台 Agent 任务的管理能力：
- spawn_agent_task: 启动后台 Agent 任务
- check_tasks: 查看任务状态
- wait_tasks: 等待任务完成
- cancel_task: 取消任务

@see docs/ASYNC_TASK_SYSTEM.md
"""

from typing import Any, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ...registry import ToolRegistry

logger = logging.getLogger(__name__)


def register_async_task_tools(
    registry: "ToolRegistry",
    async_task_manager: Optional[Any] = None,
) -> None:
    """
    注册异步任务工具到 ToolRegistry。

    Args:
        registry: 工具注册表
        async_task_manager: AsyncTaskManager 实例（可选，Tool 也可从 ToolContext 获取）
    """
    from .async_task_tools import (
        SpawnAgentTaskTool,
        CheckTasksTool,
        WaitTasksTool,
        CancelTaskTool,
    )
    from ...base import ToolSource

    registry.register(
        SpawnAgentTaskTool(async_task_manager=async_task_manager),
        source=ToolSource.SYSTEM,
    )
    registry.register(
        CheckTasksTool(async_task_manager=async_task_manager),
        source=ToolSource.SYSTEM,
    )
    registry.register(
        WaitTasksTool(async_task_manager=async_task_manager),
        source=ToolSource.SYSTEM,
    )
    registry.register(
        CancelTaskTool(async_task_manager=async_task_manager),
        source=ToolSource.SYSTEM,
    )

    logger.info("[AsyncTaskTools] 4 个异步任务工具已注册")


__all__ = [
    "register_async_task_tools",
]
