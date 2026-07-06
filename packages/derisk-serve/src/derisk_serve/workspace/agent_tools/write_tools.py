"""Layer 2 (空间操作) write tools — Lobby only. start_task creates a real Task; other tools create interventions."""
from typing import Callable, List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.intervention.api.schemas import InterventionRequest
from derisk_serve.workspace.agent_tools._task_creator import create_task_from_tool
from derisk_serve.workspace.agent_tools.read_tools import get_intervention_service

WorkspaceEventCallback = Callable[[str, dict], None]


def _make_intervention(
    system_app,
    *,
    tool_name: str,
    args: dict,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int],
) -> dict:
    svc = get_intervention_service(system_app)
    request = InterventionRequest(
        workspace_id=workspace_id,
        task_id=task_id,
        conv_uid=conv_uid,
        requested_by=user_id if user_id is not None else "system",
        question={"tool": tool_name, "args": args},
    )
    entity = svc.create(request=request)
    return {"intervention_id": entity.id, "status": "awaiting_human"}


def build_write_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
    on_event: Optional[WorkspaceEventCallback] = None,
) -> List[FunctionTool]:
    def start_task(**kwargs):
        playbook_id = kwargs.get("playbook_id")
        title = kwargs.get("title")
        description = kwargs.get("description")
        result = create_task_from_tool(
            system_app,
            workspace_id=workspace_id,
            user_id=user_id,
            playbook_id=playbook_id,
            title=title,
            description=description,
        )
        if on_event:
            on_event("task_created", {
                "task_id": result["task_id"],
                "title": result["title"],
                "status": result["status"],
                "playbook_id": result["playbook_id"],
                "playbook_name": result["playbook_name"],
                "triggered_by": result["triggered_by"],
                "workspace_id": workspace_id,
            })
        return result

    def _make_close_task_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="close_task",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
        )

    def _make_publish_asset_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="publish_asset",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
        )

    def _make_create_delivery_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="create_delivery",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
        )

    def _make_update_workspace_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="update_workspace",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
        )

    specs = [
        ("start_task", "在当前空间下发起一个任务", start_task),
        ("close_task", "关闭指定任务", _make_close_task_tool),
        ("publish_asset", "将一个交付物沉淀为空间级 Asset", _make_publish_asset_tool),
        ("create_delivery", "创建一条投递记录", _make_create_delivery_tool),
        ("update_workspace", "更新空间基本信息", _make_update_workspace_tool),
    ]
    tools: List[FunctionTool] = []
    for name, desc, fn in specs:
        tools.append(FunctionTool(name=name, description=desc, func=fn, args_schema=None))
    return tools
