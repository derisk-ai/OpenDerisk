"""Read-only FunctionTools for the workspace control Agent.

Layer 1 (空间基线, both Lobby + Workbench): list_tasks, get_task_info,
list_artifacts, list_deliveries, list_assets.
Layer 2 (空间操作, Lobby only): get_workspace_memory, list_workspace_members.
Layer 3 (剧本能力, Workbench only): list_playbooks, get_playbook_detail,
list_interventions.
"""
from typing import Any, List

from derisk._private.pydantic import BaseModel
from derisk.agent.resource.tool.base import FunctionTool


def get_task_service(system_app):
    """Resolve the task service from ``system_app``."""
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME,
        TaskService,
    )

    return system_app.get_component(TASK_SERVICE_COMPONENT_NAME, TaskService)


def get_artifact_service(system_app):
    """Resolve the artifact service from ``system_app``."""
    from derisk_serve.artifact.service.service import (
        ARTIFACT_SERVICE_COMPONENT_NAME,
        ArtifactService,
    )

    return system_app.get_component(
        ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService
    )


def get_delivery_service(system_app):
    """Resolve the delivery service from ``system_app``."""
    from derisk_serve.delivery.service.service import (
        DELIVERY_SERVICE_COMPONENT_NAME,
        DeliveryService,
    )

    return system_app.get_component(
        DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService
    )


def get_asset_service(system_app):
    """Resolve the workspace asset service from ``system_app``."""
    from derisk_serve.workspace_asset.service.service import (
        ASSET_SERVICE_COMPONENT_NAME,
        AssetService,
    )

    return system_app.get_component(ASSET_SERVICE_COMPONENT_NAME, AssetService)


def get_playbook_service(system_app):
    """Resolve the playbook service from ``system_app``."""
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )

    return system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
    )


def get_intervention_service(system_app):
    """Resolve the intervention service from ``system_app``."""
    from derisk_serve.intervention.service.service import (
        INTERVENTION_SERVICE_COMPONENT_NAME,
        InterventionService,
    )

    return system_app.get_component(
        INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService
    )


def get_workspace_memory_service(system_app):
    """Return WorkspaceMemoryService if registered, else None."""
    try:
        from derisk_serve.workspace.memory.service import (
            WORKSPACE_MEMORY_SERVICE_COMPONENT_NAME,
            WorkspaceMemoryService,
        )

        return system_app.get_component(
            WORKSPACE_MEMORY_SERVICE_COMPONENT_NAME, WorkspaceMemoryService
        )
    except Exception:
        return None


def get_workspace_member_service(system_app):
    """Return WorkspaceMemberService if registered, else None."""
    try:
        from derisk_serve.workspace.member.service import (
            WORKSPACE_MEMBER_SERVICE_COMPONENT_NAME,
            WorkspaceMemberService,
        )

        return system_app.get_component(
            WORKSPACE_MEMBER_SERVICE_COMPONENT_NAME, WorkspaceMemberService
        )
    except Exception:
        return None


def _to_jsonable(obj: Any) -> Any:
    """Convert service responses / entities into JSON-serializable structures."""
    if obj is None:
        return None
    if hasattr(obj, "to_response") and callable(
        getattr(obj, "to_response", None)
    ):
        return _to_jsonable(obj.to_response())
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, BaseModel):
        return _to_jsonable(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return {
            k: _to_jsonable(v)
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }
    return obj


def _task_list_filter(workspace_id: int):
    """Build a TaskListFilter, falling back to a lightweight namespace in tests."""
    try:
        from derisk_serve.task.api.schemas import TaskListFilter

        return TaskListFilter(workspace_id=workspace_id)
    except Exception:
        from types import SimpleNamespace

        return SimpleNamespace(
            workspace_id=workspace_id,
            status=None,
            type=None,
            user_id=None,
            include_archived=False,
            limit=100,
        )


def _list_tasks(system_app, workspace_id: int):
    svc = get_task_service(system_app)
    items = svc.list_tasks(_task_list_filter(workspace_id)) or []
    return _to_jsonable(items)


def _get_task_info(system_app, workspace_id: int, task_id: int):
    svc = get_task_service(system_app)
    item = svc.get_by_id(task_id)
    return _to_jsonable(item) if item else {"error": "task not found"}


def _list_artifacts(system_app, workspace_id: int, task_id: int = None):
    from derisk_serve.artifact.api.schemas import ArtifactListFilter

    svc = get_artifact_service(system_app)
    items = svc.list_artifacts(
        ArtifactListFilter(workspace_id=workspace_id, task_id=task_id)
    ) or []
    return _to_jsonable(items)


def _list_deliveries(system_app, workspace_id: int):
    from derisk_serve.delivery.api.schemas import DeliveryListFilter

    svc = get_delivery_service(system_app)
    items = svc.list_deliveries(
        DeliveryListFilter(workspace_id=workspace_id)
    ) or []
    return _to_jsonable(items)


def _list_assets(system_app, workspace_id: int):
    from derisk_serve.workspace_asset.api.schemas import AssetListFilter

    svc = get_asset_service(system_app)
    items = svc.list_assets(
        AssetListFilter(workspace_id=workspace_id)
    ) or []
    return _to_jsonable(items)


def _list_playbooks(system_app, workspace_id: int):
    from derisk_serve.playbook.api.schemas import PlaybookListFilter

    svc = get_playbook_service(system_app)
    items = svc.list_playbooks(
        PlaybookListFilter(workspace_id=workspace_id)
    ) or []
    return _to_jsonable(items)


def _get_playbook_detail(system_app, workspace_id: int, playbook_id: int):
    svc = get_playbook_service(system_app)
    item = svc.get_by_id(playbook_id)
    return _to_jsonable(item) if item else {"error": "playbook not found"}


def _list_interventions(system_app, workspace_id: int, task_id: int = None):
    from derisk_serve.intervention.api.schemas import InterventionListFilter

    svc = get_intervention_service(system_app)
    items = svc.list_interventions(
        InterventionListFilter(workspace_id=workspace_id, task_id=task_id)
    ) or []
    return _to_jsonable(items)


def _get_workspace_memory(system_app, workspace_id: int):
    svc = get_workspace_memory_service(system_app)
    if svc is None:
        return {"memory": None, "note": "no workspace memory configured"}
    try:
        mem = svc.get(workspace_id=workspace_id)
        return {"memory": _to_jsonable(mem) if mem else None}
    except Exception as e:
        return {"memory": None, "error": str(e)}


def _list_workspace_members(system_app, workspace_id: int):
    svc = get_workspace_member_service(system_app)
    if svc is None:
        return {"members": [], "note": "no member service configured"}
    try:
        items = svc.list_members(workspace_id=workspace_id) or []
        return {"members": _to_jsonable(items)}
    except Exception as e:
        return {"members": [], "error": str(e)}


def build_read_tools(system_app, workspace_id: int) -> List[FunctionTool]:
    """Build all read tools (Layer 1 + Layer 2 + Layer 3).

    Caller decides which subset to register for a given agent mode.
    """
    specs = [
        ("list_tasks", "列出当前空间下的所有任务", _list_tasks),
        ("get_task_info", "查询指定任务的详情", _get_task_info),
        ("list_artifacts", "列出空间下（可选指定任务）的交付物", _list_artifacts),
        ("list_deliveries", "列出空间下最近的投递记录", _list_deliveries),
        ("list_assets", "列出空间下沉淀的 Asset", _list_assets),
        ("get_workspace_memory", "读取空间记忆", _get_workspace_memory),
        ("list_workspace_members", "列出空间成员", _list_workspace_members),
        ("list_playbooks", "列出空间下的剧本", _list_playbooks),
        ("get_playbook_detail", "查询剧本详情", _get_playbook_detail),
        ("list_interventions", "列出空间下（可选指定任务）的人工介入记录", _list_interventions),
    ]
    tools: List[FunctionTool] = []
    for name, desc, fn in specs:

        def make_tool(fn=fn, name=name, desc=desc):
            def _wrapped(**kwargs):
                kwargs["system_app"] = system_app
                return fn(**kwargs)

            _wrapped.__name__ = name
            return FunctionTool(name, _wrapped, description=desc)

        tools.append(make_tool())
    return tools
