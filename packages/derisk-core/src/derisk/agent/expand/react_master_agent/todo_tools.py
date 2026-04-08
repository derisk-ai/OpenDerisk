"""
Todo 工具 - 参考 opencode 的 todowrite/todoread 设计

简洁的任务列表管理，LLM 自主决策何时使用。

工具列表：
- todowrite: 创建/更新任务列表
- todoread: 读取任务列表状态

功能：
- 可视化推送：使用 d-todo-list 组件
- 跨会话分析：统计常见任务模式
- 与 ReportGenerator 集成
"""

import json
import logging
import uuid
from typing import List, Dict, Any, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk.agent.core.system_tool_registry import system_tool
from derisk.agent.core.memory.gpts import TodoItem, TodoStatus, TodoPriority

logger = logging.getLogger(__name__)


# ============================================================================
# 可视化推送相关
# ============================================================================

def _get_render_protocol(agent):
    """获取渲染协议实例."""
    if hasattr(agent, "not_null_agent_context"):
        ctx = agent.not_null_agent_context
        if ctx and hasattr(ctx, "render_protocol"):
            return ctx.render_protocol
    return None


async def _push_todolist_vis(agent, todos: List[TodoItem], mission: str = "") -> None:
    """推送 TodoList 可视化到前端.

    Args:
        agent: Agent 实例
        todos: 任务列表
        mission: 任务描述
    """
    render_protocol = _get_render_protocol(agent)
    if not render_protocol:
        logger.debug("render_protocol not available, skip vis push")
        return

    try:
        # 获取当前进行中的任务索引
        current_index = 0
        for i, todo in enumerate(todos):
            if todo.status == TodoStatus.IN_PROGRESS.value:
                current_index = i
                break

        # 构建 TodoList 可视化内容
        todo_items = []
        for i, todo in enumerate(todos):
            todo_items.append({
                "id": todo.id,
                "title": todo.content,
                "status": todo.status,
                "index": i,
            })

        vis_content = {
            "uid": f"todo_list_{_get_conv_id(agent)}",
            "type": "all",
            "mission": mission,
            "items": todo_items,
            "current_index": current_index,
            "total_count": len(todos),
        }

        # 推送可视化
        render_protocol.sync_display(content=vis_content, vis_tag="d-todo-list")
        logger.debug(f"Pushed todolist vis with {len(todos)} items")

    except Exception as e:
        logger.error(f"Failed to push todolist vis: {e}")


# ============================================================================
# todowrite 工具
# ============================================================================

TODOWRITER_DESCRIPTION = """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

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
todowrite({
    "todos": [
        {"content": "分析项目结构", "status": "completed"},
        {"content": "定位问题代码", "status": "in_progress"},
        {"content": "实现修复", "status": "pending"},
        {"content": "验证修复效果", "status": "pending"}
    ]
})
```"""


def _get_todo_storage(agent):
    """获取 TodoStorage 实例."""
    if hasattr(agent, "memory") and hasattr(agent.memory, "gpts_memory"):
        return agent.memory.gpts_memory
    return None


def _get_conv_id(agent) -> str:
    """获取当前会话 ID."""
    if hasattr(agent, "not_null_agent_context"):
        ctx = agent.not_null_agent_context
        if ctx:
            return ctx.conv_id or ctx.conv_session_id or "default"
    return "default"


@system_tool(
    name="todowrite",
    description=TODOWRITER_DESCRIPTION,
    ask_user=False,
)
async def todowrite(
    todos: List[Dict[str, Any]],
    agent: Any = None,
) -> str:
    """
    创建或更新任务列表.

    Args:
        todos: 任务列表，每项包含:
            - content: 任务内容
            - status: pending | in_progress | completed | cancelled
            - priority: high | medium | low (可选，默认 medium)
            - id: 任务 ID (可选，不提供则自动生成)

    Returns:
        操作结果
    """
    if not todos:
        return "错误: 任务列表不能为空"

    storage = _get_todo_storage(agent)
    if not storage:
        return "错误: Todo 存储不可用"

    conv_id = _get_conv_id(agent)

    # 获取现有任务列表以保留 ID
    existing_todos = await storage.read_todos(conv_id)
    existing_map = {t.content: t.id for t in existing_todos}

    # 构建新的任务列表
    new_todos = []
    for i, todo_data in enumerate(todos):
        content = todo_data.get("content", "")
        if not content:
            continue

        # 尝试复用现有 ID 或生成新 ID
        todo_id = todo_data.get("id") or existing_map.get(content) or str(uuid.uuid4())[:8]

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
    mission = getattr(agent.not_null_agent_context, "query", "") if hasattr(agent, "not_null_agent_context") else ""
    await _push_todolist_vis(agent, new_todos, mission)

    # 统计
    pending_count = sum(1 for t in new_todos if t.status == TodoStatus.PENDING.value)
    in_progress_count = sum(1 for t in new_todos if t.status == TodoStatus.IN_PROGRESS.value)
    completed_count = sum(1 for t in new_todos if t.status == TodoStatus.COMPLETED.value)

    result = {
        "success": True,
        "message": f"已更新任务列表",
        "stats": {
            "total": len(new_todos),
            "pending": pending_count,
            "in_progress": in_progress_count,
            "completed": completed_count,
        },
        "todos": [t.to_dict() for t in new_todos],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================================
# todoread 工具
# ============================================================================

TODOREAD_DESCRIPTION = """Use this tool to read your todo list.

Returns the current todo list with status information."""


@system_tool(
    name="todoread",
    description=TODOREAD_DESCRIPTION,
    ask_user=False,
)
async def todoread(
    agent: Any = None,
) -> str:
    """
    读取任务列表.

    Returns:
        任务列表和状态统计
    """
    storage = _get_todo_storage(agent)
    if not storage:
        return json.dumps({"error": "Todo 存储不可用"}, ensure_ascii=False)

    conv_id = _get_conv_id(agent)
    todos = await storage.read_todos(conv_id)

    if not todos:
        return json.dumps({
            "message": "暂无任务列表",
            "todos": [],
            "stats": {"total": 0, "pending": 0, "in_progress": 0, "completed": 0}
        }, ensure_ascii=False, indent=2)

    # 统计
    pending_count = sum(1 for t in todos if t.status == TodoStatus.PENDING.value)
    in_progress_count = sum(1 for t in todos if t.status == TodoStatus.IN_PROGRESS.value)
    completed_count = sum(1 for t in todos if t.status == TodoStatus.COMPLETED.value)
    cancelled_count = sum(1 for t in todos if t.status == TodoStatus.CANCELLED.value)

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

    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================================
# 工具注册
# ============================================================================

def get_todo_tools() -> Dict[str, FunctionTool]:
    """获取 Todo 工具列表."""
    from derisk.agent.core.system_tool_registry import system_tool_dict
    tools = {}
    if "todowrite" in system_tool_dict:
        tools["todowrite"] = system_tool_dict["todowrite"]
    if "todoread" in system_tool_dict:
        tools["todoread"] = system_tool_dict["todoread"]
    return tools


# ============================================================================
# 跨会话 Todo 分析功能
# ============================================================================

class TodoAnalytics:
    """Todo 分析器 - 统计常见任务模式."""

    def __init__(self):
        self._session_stats: Dict[str, Dict[str, Any]] = {}

    def record_session(self, conv_id: str, todos: List[TodoItem]) -> None:
        """记录会话的 Todo 统计."""
        self._session_stats[conv_id] = {
            "total": len(todos),
            "completed": sum(1 for t in todos if t.status == TodoStatus.COMPLETED.value),
            "cancelled": sum(1 for t in todos if t.status == TodoStatus.CANCELLED.value),
            "high_priority": sum(1 for t in todos if t.priority == TodoPriority.HIGH.value),
            "contents": [t.content for t in todos],
        }

    def get_common_patterns(self, limit: int = 10) -> Dict[str, Any]:
        """分析常见任务模式.

        Returns:
            包含常见任务模式、完成率等的统计信息
        """
        if not self._session_stats:
            return {"patterns": [], "stats": {}}

        # 统计任务关键词
        keyword_counts: Dict[str, int] = {}
        for stats in self._session_stats.values():
            for content in stats.get("contents", []):
                keywords = self._extract_keywords(content)
                for kw in keywords:
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        # 排序获取最常见的模式
        sorted_patterns = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

        # 整体统计
        total_sessions = len(self._session_stats)
        total_todos = sum(s["total"] for s in self._session_stats.values())
        total_completed = sum(s["completed"] for s in self._session_stats.values())

        return {
            "patterns": [{"keyword": k, "count": c} for k, c in sorted_patterns],
            "stats": {
                "total_sessions": total_sessions,
                "total_todos": total_todos,
                "total_completed": total_completed,
                "completion_rate": total_completed / total_todos if total_todos > 0 else 0,
            },
        }

    def _extract_keywords(self, content: str) -> List[str]:
        """提取任务关键词."""
        import re
        keywords = []
        patterns = [
            r"分析|分析.*",
            r"实现|实现.*",
            r"修复|修复.*",
            r"优化|优化.*",
            r"测试|测试.*",
            r"编写|编写.*",
            r"重构|重构.*",
            r"设计|设计.*",
            r"部署|部署.*",
            r"调试|调试.*",
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                keywords.append(match.group())
        return keywords


# 全局分析器实例
_todo_analytics = TodoAnalytics()


async def get_todo_analytics() -> TodoAnalytics:
    """获取 Todo 分析器实例."""
    return _todo_analytics


# ============================================================================
# ReportGenerator 集成
# ============================================================================

async def generate_todo_report(
    conv_id: str,
    todos: List[TodoItem],
    include_analytics: bool = True,
) -> str:
    """生成 Todo 报告（Markdown 格式）.

    Args:
        conv_id: 会话 ID
        todos: 任务列表
        include_analytics: 是否包含跨会话分析

    Returns:
        Markdown 格式的报告
    """
    lines = [
        "# 任务完成报告",
        "",
        f"**会话ID**: {conv_id}",
        f"**总任务数**: {len(todos)}",
        "",
    ]

    # 统计
    completed = [t for t in todos if t.status == TodoStatus.COMPLETED.value]
    in_progress = [t for t in todos if t.status == TodoStatus.IN_PROGRESS.value]
    pending = [t for t in todos if t.status == TodoStatus.PENDING.value]
    cancelled = [t for t in todos if t.status == TodoStatus.CANCELLED.value]

    # 概览
    lines.extend([
        "## 📊 概览",
        "",
        f"| 状态 | 数量 | 占比 |",
        f"|------|------|------|",
        f"| ✅ 已完成 | {len(completed)} | {len(completed)/len(todos)*100:.1f}%" if todos else "| ✅ 已完成 | 0 | 0% |",
        f"| 🔄 进行中 | {len(in_progress)} | {len(in_progress)/len(todos)*100:.1f}%" if todos else "| 🔄 进行中 | 0 | 0% |",
        f"| ⏳ 待处理 | {len(pending)} | {len(pending)/len(todos)*100:.1f}%" if todos else "| ⏳ 待处理 | 0 | 0% |",
        f"| ❌ 已取消 | {len(cancelled)} | {len(cancelled)/len(todos)*100:.1f}%" if todos else "| ❌ 已取消 | 0 | 0% |",
        "",
    ])

    # 已完成任务
    if completed:
        lines.extend([
            "## ✅ 已完成任务",
            "",
        ])
        for t in completed:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "⚪")
            lines.append(f"- {priority_icon} {t.content}")
        lines.append("")

    # 进行中任务
    if in_progress:
        lines.extend([
            "## 🔄 进行中任务",
            "",
        ])
        for t in in_progress:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "⚪")
            lines.append(f"- {priority_icon} {t.content}")
        lines.append("")

    # 待处理任务
    if pending:
        lines.extend([
            "## ⏳ 待处理任务",
            "",
        ])
        for t in pending:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "⚪")
            lines.append(f"- {priority_icon} {t.content}")
        lines.append("")

    # 跨会话分析
    if include_analytics:
        analytics = await get_todo_analytics()
        analytics.record_session(conv_id, todos)
        patterns = analytics.get_common_patterns()

        if patterns["patterns"]:
            lines.extend([
                "## 📈 任务模式分析",
                "",
                "### 常见任务类型",
                "",
            ])
            for p in patterns["patterns"][:5]:
                lines.append(f"- **{p['keyword']}**: 出现 {p['count']} 次")
            lines.append("")

            if patterns["stats"]:
                stats = patterns["stats"]
                lines.extend([
                    "### 整体统计",
                    "",
                    f"- 总会话数: {stats['total_sessions']}",
                    f"- 总任务数: {stats['total_todos']}",
                    f"- 完成率: {stats['completion_rate']*100:.1f}%",
                    "",
                ])

    return "\n".join(lines)


async def get_todo_report_for_reportgenerator(conv_id: str, storage) -> Dict[str, Any]:
    """为 ReportGenerator 提供 Todo 报告数据.

    Args:
        conv_id: 会话 ID
        storage: TodoStorage 实例

    Returns:
        可用于 ReportGenerator 的数据字典
    """
    todos = await storage.read_todos(conv_id)
    report_markdown = await generate_todo_report(conv_id, todos)

    return {
        "type": "todo_report",
        "conv_id": conv_id,
        "content": report_markdown,
        "stats": {
            "total": len(todos),
            "completed": sum(1 for t in todos if t.status == TodoStatus.COMPLETED.value),
            "in_progress": sum(1 for t in todos if t.status == TodoStatus.IN_PROGRESS.value),
            "pending": sum(1 for t in todos if t.status == TodoStatus.PENDING.value),
        },
        "todos": [t.to_dict() for t in todos],
    }