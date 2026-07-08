from typing import Any, List

from derisk_serve.workspace.agent_tools.context_builder import (
    WorkspaceContextSnapshot,
    render_workspace_context_summary,
)

SCENE_AGENT_STATIC_PROMPT = """\
你是 OpenDerisk 场景空间助手（Scene Workspace Agent），当前工作空间的协作者。
你不是通用聊天助手；你的目标是理解用户在该场景空间中的工作目标，调用合适的工具推进任务，并把结果沉淀为可复用的资产或报告。
"""

_LOBBY_TOOLS = [
    "list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets",
    "get_workspace_memory", "list_workspace_members", "list_playbooks", "get_playbook_detail",
    "start_task", "close_task", "publish_asset", "create_delivery", "update_workspace",
]

_WORKBENCH_TOOLS = [
    "list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets",
    "list_playbooks", "get_playbook_detail", "list_interventions",
    "start_task", "close_task", "publish_asset", "create_delivery", "update_workspace",
    "launch_playbook", "update_playbook", "archive_playbook",
]


def render_scene_dynamic_context(ctx: WorkspaceContextSnapshot, mode: str = "lobby") -> str:
    """Render the dynamic workspace/playbook/task/tools block for the scene agent."""
    lines: List[str] = []

    # Layer 1: workspace identity and existing summary
    summary = render_workspace_context_summary(ctx, mode=mode)
    if summary:
        lines.append(summary)

    # Layer 2: active tasks (lobby only)
    if mode == "lobby" and ctx.active_tasks:
        lines.append("## 进行中任务")
        for t in ctx.active_tasks:
            tid = getattr(t, "id", "")
            title = getattr(t, "title", "")
            status = getattr(t, "status", "")
            lines.append(f"- id={tid} 标题：{title} 状态：{status}")

    # Layer 3: current task detail (workbench only)
    if mode == "workbench" and ctx.task:
        lines.append("## 当前任务详情")
        task = ctx.task
        lines.append(f"- id={getattr(task, 'id', '')} 标题：{getattr(task, 'title', '')}")
        if getattr(task, "description", None):
            lines.append(f"- 描述：{task.description}")
        if getattr(task, "status", None):
            lines.append(f"- 状态：{task.status}")

    # Layer 4: available tools
    tool_names = _LOBBY_TOOLS if mode == "lobby" else _WORKBENCH_TOOLS
    lines.append("## 当前可用工具")
    lines.append(
        "当前模式下实际挂载的工具：" + ", ".join(f"`{n}`" for n in tool_names)
    )

    return "\n\n".join(lines)