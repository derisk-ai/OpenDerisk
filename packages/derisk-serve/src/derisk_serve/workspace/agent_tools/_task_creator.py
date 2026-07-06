"""Helper to create a real Task from tool invocation (non-intervention path)."""
from typing import Any, Dict, Optional


def create_task_from_tool(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    playbook_id: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a real Task via TaskService, return task metadata."""
    from derisk_serve.task.api.schemas import TaskRequest
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME,
        TaskService,
    )
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )

    task_service: TaskService = system_app.get_component(
        TASK_SERVICE_COMPONENT_NAME, TaskService
    )
    playbook_service: PlaybookService = system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
    )

    playbook = None
    if playbook_id:
        playbook = playbook_service.get_by_id(playbook_id)

    request = TaskRequest(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        title=title or (playbook.name if playbook else "手动创建任务"),
        description=description or "",
        type="adhoc",
        triggered_by="manual",
        created_by_user_id=int(user_id) if user_id and user_id.isdigit() else None,
    )
    entity = task_service.create(request)
    return {
        "task_id": entity.id,
        "title": entity.title,
        "status": entity.status,
        "playbook_id": entity.playbook_id,
        "playbook_name": playbook.name if playbook else None,
        "triggered_by": entity.triggered_by,
    }
