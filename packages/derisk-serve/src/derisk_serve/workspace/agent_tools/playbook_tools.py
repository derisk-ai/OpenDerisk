"""Layer 3 (剧本能力) write tools — Workbench only. Each creates an intervention, does NOT execute."""
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


def build_playbook_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
) -> List[FunctionTool]:
    specs = [
        ("launch_playbook", "基于剧本发起新任务"),
        ("update_playbook", "更新剧本声明 DSL"),
        ("archive_playbook", "归档剧本"),
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
