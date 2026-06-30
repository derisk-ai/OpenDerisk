"""Task entity + relation entity + DAOs."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, Index, desc, and_,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import TaskListFilter, TaskRequest, TaskResponse
from ..config import SERVER_APP_TABLE_NAME

TASK_TABLE_NAME = SERVER_APP_TABLE_NAME
TASK_RELATION_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_relation"


def _dump_json(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _load_json(v):
    if not v:
        return {} if isinstance(v, str) else (v if isinstance(v, (dict, list)) else {})
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}


class TaskEntity(Model):
    __tablename__ = TASK_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    parent_task_id = Column(Integer, nullable=True, index=True)
    type = Column(String(32), nullable=False, default="adhoc")
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    priority = Column(String(16), nullable=True)
    triggered_by = Column(String(32), nullable=False, default="manual")
    trigger_ref = Column(String(128), nullable=True)
    playbook_id = Column(Integer, nullable=True, index=True)
    playbook_version_id = Column(Integer, nullable=True)
    conv_session_id = Column(String(64), nullable=True, unique=True, index=True, comment="conversation session id bound to this task")
    created_by_user_id = Column(Integer, nullable=True, index=True)
    assigned_agents_json = Column(Text, nullable=True)
    context_json = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TaskRelationEntity(Model):
    __tablename__ = TASK_RELATION_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_task_id = Column(Integer, nullable=False, index=True)
    child_task_id = Column(Integer, nullable=False, index=True)
    relation_type = Column(String(32), nullable=False, default="spawned_by")

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)

    __table_args__ = (
        Index("idx_task_relation", "parent_task_id", "child_task_id"),
    )


class TaskDao(BaseDao[TaskEntity, TaskRequest, TaskResponse]):
    def from_request(self, request: Union[TaskRequest, Dict[str, Any]]) -> TaskEntity:
        data = request.dict() if isinstance(request, TaskRequest) else dict(request)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("id", None)
        agents = data.pop("assigned_agents", None) or []
        ctx = data.pop("context", None) or {}
        entity = TaskEntity(**data)
        entity.assigned_agents_json = _dump_json(agents)
        entity.context_json = _dump_json(ctx)
        return entity

    def to_request(self, entity: TaskEntity) -> TaskRequest:
        return TaskRequest(
            id=entity.id,
            workspace_id=entity.workspace_id,
            parent_task_id=entity.parent_task_id,
            type=entity.type,
            title=entity.title,
            description=entity.description,
            status=entity.status,
            priority=entity.priority,
            triggered_by=entity.triggered_by,
            trigger_ref=entity.trigger_ref,
            playbook_id=entity.playbook_id,
            playbook_version_id=entity.playbook_version_id,
            conv_session_id=entity.conv_session_id,
            created_by_user_id=entity.created_by_user_id,
            assigned_agents=_load_json(entity.assigned_agents_json) or [],
            context=_load_json(entity.context_json),
            due_at=entity.due_at,
        )

    def to_response(self, entity: TaskEntity) -> TaskResponse:
        return TaskResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            parent_task_id=entity.parent_task_id,
            type=entity.type,
            title=entity.title,
            description=entity.description,
            status=entity.status,
            priority=entity.priority,
            triggered_by=entity.triggered_by,
            trigger_ref=entity.trigger_ref,
            playbook_id=entity.playbook_id,
            playbook_version_id=entity.playbook_version_id,
            conv_session_id=entity.conv_session_id,
            created_by_user_id=entity.created_by_user_id,
            assigned_agents=_load_json(entity.assigned_agents_json) or [],
            context=_load_json(entity.context_json),
            due_at=entity.due_at.isoformat() if entity.due_at else None,
            started_at=entity.started_at.isoformat() if entity.started_at else None,
            closed_at=entity.closed_at.isoformat() if entity.closed_at else None,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: TaskListFilter) -> List[TaskResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(TaskEntity).filter(
                TaskEntity.workspace_id == f.workspace_id
            )
            if not f.include_archived:
                query = query.filter(TaskEntity.is_archived == False)
            if f.status:
                query = query.filter(TaskEntity.status == f.status)
            if f.type:
                query = query.filter(TaskEntity.type == f.type)
            if f.user_id is not None:
                query = query.filter(TaskEntity.created_by_user_id == f.user_id)
            entities = (
                query.order_by(desc(TaskEntity.gmt_modified)).limit(f.limit).all()
            )
            return [self.to_response(e) for e in entities]
        finally:
            session.close()
