"""
Todoread Tool - 读取任务列表工具

读取当前任务列表状态。
"""

import json
import logging
from typing import Any, Dict, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


TODOREAD_DESCRIPTION = """Use this tool to read your todo list.

Returns the current todo list with status information."""


class TodoreadTool(ToolBase):
    """
    读取任务列表工具
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="todoread",
            display_name="Read Todo List",
            description=TODOREAD_DESCRIPTION,
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            requires_permission=False,
            tags=["todo", "task", "tracking", "progress"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """执行任务列表读取"""
        try:
            # 获取存储和会话信息
            storage, conv_id = self._get_storage_and_conv_id(context)
            if not storage:
                return ToolResult.fail(
                    error="Todo 存储不可用",
                    tool_name=self.name,
                )

            # 读取任务列表
            todos = await storage.read_todos(conv_id)

            if not todos:
                result = {
                    "message": "暂无任务列表",
                    "todos": [],
                    "stats": {
                        "total": 0,
                        "pending": 0,
                        "in_progress": 0,
                        "completed": 0,
                    },
                }
                return ToolResult.ok(
                    output=json.dumps(result, ensure_ascii=False, indent=2),
                    tool_name=self.name,
                )

            # 统计
            from derisk.agent.core.memory.gpts import TodoStatus

            pending_count = sum(
                1 for t in todos if t.status == TodoStatus.PENDING.value
            )
            in_progress_count = sum(
                1 for t in todos if t.status == TodoStatus.IN_PROGRESS.value
            )
            completed_count = sum(
                1 for t in todos if t.status == TodoStatus.COMPLETED.value
            )
            cancelled_count = sum(
                1 for t in todos if t.status == TodoStatus.CANCELLED.value
            )

            result = {
                "message": f"当前任务列表 ({len(todos)} 个任务)",
                "stats": {
                    "total": len(todos),
                    "pending": pending_count,
                    "in_progress": in_progress_count,
                    "completed": completed_count,
                    "cancelled": cancelled_count,
                },
                "todos": [t.to_dict() for t in todos],
            }

            return ToolResult.ok(
                output=json.dumps(result, ensure_ascii=False, indent=2),
                tool_name=self.name,
                metadata={"total": len(todos)},
            )

        except Exception as e:
            logger.exception(f"Failed to read todos: {e}")
            return ToolResult.fail(
                error=f"读取任务列表失败: {str(e)}",
                tool_name=self.name,
            )

    def _get_storage_and_conv_id(self, context: Optional[Any]):
        """获取 TodoStorage 和 conv_id"""
        if not context:
            return None, None

        # 尝试从 context 获取 agent
        agent = getattr(context, "agent", None) or context

        # 获取存储
        storage = None
        if hasattr(agent, "memory") and hasattr(agent.memory, "gpts_memory"):
            storage = agent.memory.gpts_memory

        # 获取 conv_id
        conv_id = "default"
        if hasattr(agent, "not_null_agent_context"):
            ctx = agent.not_null_agent_context
            if ctx:
                conv_id = ctx.conv_id or ctx.conv_session_id or "default"

        return storage, conv_id
