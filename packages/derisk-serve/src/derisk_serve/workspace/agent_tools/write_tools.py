"""Layer 2 (空间操作) write tools — Lobby only. Each creates an intervention, does NOT execute."""
from typing import List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.intervention.api.schemas import InterventionRequest
from derisk_serve.workspace.agent_tools.read_tools import get_intervention_service


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
) -> List[FunctionTool]:
    specs = [
        ("start_task", "在当前空间下发起一个任务"),
        ("close_task", "关闭指定任务"),
        ("publish_asset", "将一个交付物沉淀为空间级 Asset"),
        ("create_delivery", "创建一条投递记录"),
        ("update_workspace", "更新空间基本信息"),
    ]
    tools: List[FunctionTool] = []
    for name, desc in specs:

        def make_tool(name=name, desc=desc):
            def _wrapped(**kwargs):
                return _make_intervention(
                    system_app,
                    tool_name=name,
                    args=kwargs,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    conv_uid=conv_uid,
                    task_id=task_id,
                )

            _wrapped.__name__ = name
            return FunctionTool(
                name=name, description=desc, func=_wrapped, args_schema=None
            )

        tools.append(make_tool())
    return tools
