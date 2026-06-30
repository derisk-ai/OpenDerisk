"""Task service: lifecycle + state machine + distill enforcement."""
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    TaskCloseRequest, TaskListFilter, TaskRelationRequest, TaskRequest, TaskResponse,
)
from ..config import ServeConfig
from ..models.models import TaskDao, TaskEntity, TaskRelationEntity

TASK_SERVICE_COMPONENT_NAME = "serve_task_service"
logger = logging.getLogger(__name__)

# Allowed state transitions
VALID_TRANSITIONS = {
    "draft": {"pending_trigger", "running", "archived"},
    "pending_trigger": {"running", "archived"},
    "running": {"awaiting_human", "blocked", "delivered", "failed", "closed"},
    "awaiting_human": {"running", "blocked", "closed"},
    "blocked": {"running", "archived"},
    "delivered": {"closed", "archived"},
    "failed": {"running", "archived"},
    "closed": {"archived"},
    "archived": set(),
}


class TaskService(BaseService[TaskEntity, TaskRequest, TaskResponse]):
    name = TASK_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[TaskDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: TaskDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or TaskDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: TaskRequest) -> TaskResponse:
        # Ensure each task owns a unique conversation session.
        if not request.conv_session_id:
            request.conv_session_id = uuid.uuid1().hex
        response = self._dao.create(request)
        # Link the conversation session to workspace/task.
        try:
            from derisk_serve.workspace.service.service import (
                WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
            )
            ws_service: WorkspaceService = self._system_app.get_component(
                WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
            )
            ws_service.link_conversation(
                workspace_id=response.workspace_id,
                conv_uid=response.conv_session_id,
                task_id=response.id,
                user_id=response.created_by_user_id,
            )
        except Exception as e:
            logger.warning(f"failed to link task conversation: {e}")
        return response

    def update(self, request: TaskRequest) -> TaskResponse:
        if not request.id:
            raise ValueError("task id required for update")
        update_dict = request.dict(exclude_unset=True)
        update_dict.pop("id", None)
        if "assigned_agents" in update_dict:
            update_dict["assigned_agents_json"] = json.dumps(
                update_dict.pop("assigned_agents") or [], ensure_ascii=False
            )
        if "context" in update_dict:
            update_dict["context_json"] = json.dumps(
                update_dict.pop("context") or {}, ensure_ascii=False
            )
        self._dao.update({"id": request.id}, update_dict, force_update=True)
        return self.get_by_id(request.id)

    def get_by_id(self, task_id: int) -> Optional[TaskResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TaskEntity).filter(
                TaskEntity.id == task_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()

    def list_tasks(self, f: TaskListFilter) -> List[TaskResponse]:
        return self._dao.list_by_filter(f)

    def transition(self, task_id: int, new_status: str) -> TaskResponse:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TaskEntity).filter(
                TaskEntity.id == task_id
            ).with_for_update().first()
            if not entity:
                raise ValueError(f"task {task_id} not found")
            current = entity.status
            if new_status not in VALID_TRANSITIONS.get(current, set()):
                raise ValueError(
                    f"invalid transition {current} -> {new_status}"
                )
            entity.status = new_status
            if new_status == "running" and not entity.started_at:
                entity.started_at = datetime.now()
            if new_status == "closed":
                entity.closed_at = datetime.now()
            session.commit()
            # Refresh to detach safely before closing the session
            session.refresh(entity)
            response = self._dao.to_response(entity)
            return response
        finally:
            session.close()

    def start(self, task_id: int) -> TaskResponse:
        return self.transition(task_id, "running")

    def close(self, request: TaskCloseRequest) -> TaskResponse:
        """Close a task. Server enforces distill completion."""
        if not request.distill_completed:
            raise ValueError(
                "distill not completed — Task cannot be closed until "
                "intervention distillation and asset sinking are done"
            )
        # additional server-side check: ensure at least one asset produced
        # (delegated to caller / context_builder in real flow)
        return self.transition(request.task_id, "closed")

    def archive(self, task_id: int) -> TaskResponse:
        return self.transition(task_id, "archived")

    def spawn(
        self, parent_task_id: int, child_request: TaskRequest,
        relation_type: str = "spawned_by",
    ) -> TaskResponse:
        child_request.parent_task_id = parent_task_id
        child = self._dao.create(child_request)
        # record relation
        session = self._dao.get_raw_session()
        try:
            rel = TaskRelationEntity(
                parent_task_id=parent_task_id,
                child_task_id=child.id,
                relation_type=relation_type,
            )
            session.add(rel)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return child
