"""
Todowrite Tool - 创建/更新任务列表工具

简洁的任务列表管理，LLM 自主决策何时使用。
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


TODOWRITE_DESCRIPTION = """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multistep tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos. Feel free to edit the todo list based on new information.
6. After completing a task - Mark it complete and add any new follow-up tasks
7. When you start working on a new task, mark the todo as in_progress. Ideally you should only have one todo as in_progress at a time. Complete existing tasks before starting new ones.

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

## Task States

Use these states to track progress:
- pending: Task not yet started
- in_progress: Currently working on (limit to ONE task at a time)
- completed: Task finished successfully
- cancelled: Task no longer needed

## Example

```json
{
    "todos": [
        {"content": "分析项目结构", "status": "completed"},
        {"content": "定位问题代码", "status": "in_progress"},
        {"content": "实现修复", "status": "pending"},
        {"content": "验证修复效果", "status": "pending"}
    ]
}
```"""


class TodowriteTool(ToolBase):
    """
    创建或更新任务列表工具
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="todowrite",
            display_name="Write Todo List",
            description=TODOWRITE_DESCRIPTION,
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            requires_permission=False,
            tags=["todo", "task", "tracking", "progress"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "任务列表，每项包含 content, status, priority(可选)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "任务内容描述",
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "cancelled",
                                ],
                                "description": "任务状态",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "任务优先级（可选，默认 medium）",
                            },
                            "id": {
                                "type": "string",
                                "description": "任务 ID（可选，不提供则自动生成）",
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
            "required": ["todos"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """执行任务列表更新"""
        todos = args.get("todos", [])

        if not todos:
            return ToolResult.fail(
                error="任务列表不能为空",
                tool_name=self.name,
            )

        try:
            # 获取存储和会话信息
            storage, conv_id = self._get_storage_and_conv_id(context)
            if not storage:
                return ToolResult.fail(
                    error="Todo 存储不可用",
                    tool_name=self.name,
                )

            # 获取现有任务列表以保留 ID
            existing_todos = await storage.read_todos(conv_id)
            existing_map = {t.content: t.id for t in existing_todos}

            # 构建新的任务列表
            from derisk.agent.core.memory.gpts import TodoItem, TodoStatus, TodoPriority

            new_todos = []
            for todo_data in todos:
                content = todo_data.get("content", "")
                if not content:
                    continue

                # 尝试复用现有 ID 或生成新 ID
                todo_id = (
                    todo_data.get("id")
                    or existing_map.get(content)
                    or str(uuid.uuid4())[:8]
                )
                status = todo_data.get("status", TodoStatus.PENDING.value)
                priority = todo_data.get("priority", TodoPriority.MEDIUM.value)

                todo_item = TodoItem(
                    id=todo_id,
                    content=content,
                    status=status,
                    priority=priority,
                )
                new_todos.append(todo_item)

            # 写入存储
            await storage.write_todos(conv_id, new_todos)

            # 推送可视化
            await self._push_todolist_vis(context, new_todos)

            # 统计
            pending_count = sum(
                1 for t in new_todos if t.status == TodoStatus.PENDING.value
            )
            in_progress_count = sum(
                1 for t in new_todos if t.status == TodoStatus.IN_PROGRESS.value
            )
            completed_count = sum(
                1 for t in new_todos if t.status == TodoStatus.COMPLETED.value
            )

            result = {
                "success": True,
                "message": "已更新任务列表",
                "stats": {
                    "total": len(new_todos),
                    "pending": pending_count,
                    "in_progress": in_progress_count,
                    "completed": completed_count,
                },
                "todos": [t.to_dict() for t in new_todos],
            }

            return ToolResult.ok(
                output=json.dumps(result, ensure_ascii=False, indent=2),
                tool_name=self.name,
                metadata={"total": len(new_todos)},
            )

        except Exception as e:
            logger.exception(f"Failed to write todos: {e}")
            return ToolResult.fail(
                error=f"更新任务列表失败: {str(e)}",
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

    async def _push_todolist_vis(
        self, context: Optional[Any], todos: List[Any]
    ) -> None:
        """推送 TodoList 可视化到前端"""
        try:
            agent = getattr(context, "agent", None) or context
            if not agent:
                return

            render_protocol = None
            if hasattr(agent, "not_null_agent_context"):
                ctx = agent.not_null_agent_context
                if ctx and hasattr(ctx, "render_protocol"):
                    render_protocol = ctx.render_protocol

            if not render_protocol:
                return

            from derisk.agent.core.memory.gpts import TodoStatus

            # 获取当前进行中的任务索引
            current_index = 0
            for i, todo in enumerate(todos):
                if todo.status == TodoStatus.IN_PROGRESS.value:
                    current_index = i
                    break

            # 获取 conv_id
            conv_id = "default"
            if hasattr(agent, "not_null_agent_context"):
                ctx = agent.not_null_agent_context
                if ctx:
                    conv_id = ctx.conv_id or "default"

            # 构建可视化内容
            todo_items = []
            for i, todo in enumerate(todos):
                todo_items.append(
                    {
                        "id": todo.id,
                        "title": todo.content,
                        "status": todo.status,
                        "index": i,
                    }
                )

            vis_content = {
                "uid": f"todo_list_{conv_id}",
                "type": "all",
                "mission": "",
                "items": todo_items,
                "current_index": current_index,
                "total_count": len(todos),
            }

            render_protocol.sync_display(content=vis_content, vis_tag="d-todo-list")
            logger.debug(f"Pushed todolist vis with {len(todos)} items")

        except Exception as e:
            logger.warning(f"Failed to push todolist vis: {e}")
