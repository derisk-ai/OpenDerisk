"""Intervention entity."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Index, desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    InterventionListFilter, InterventionRequest, InterventionResponse,
)
from ..config import SERVER_APP_TABLE_NAME

INTERVENTION_TABLE_NAME = SERVER_APP_TABLE_NAME


def _dump_json(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _load_json(v):
    if not v:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


class InterventionEntity(Model):
    __tablename__ = INTERVENTION_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    type = Column(String(32), nullable=False, default="review")
    status = Column(String(32), nullable=False, default="requested")
    requested_by = Column(String(32), nullable=False, default="system")
    requested_at = Column(DateTime, default=datetime.now)
    question_json = Column(Text, nullable=True)
    context_json = Column(Text, nullable=True)
    resolved_by_user_id = Column(Integer, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    decision_json = Column(Text, nullable=True)
    distillation_json = Column(Text, nullable=True)
    linked_asset_id = Column(Integer, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class InterventionDao(BaseDao[InterventionEntity, InterventionRequest, InterventionResponse]):
    def from_request(self, request: Union[InterventionRequest, Dict[str, Any]]) -> InterventionEntity:
        data = request.dict() if isinstance(request, InterventionRequest) else dict(request)
        data.pop("id", None)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        question = data.pop("question", None)
        context = data.pop("context", None)
        entity = InterventionEntity(**data)
        entity.question_json = _dump_json(question)
        entity.context_json = _dump_json(context)
        return entity

    def to_request(self, entity: InterventionEntity) -> InterventionRequest:
        return InterventionRequest(
            id=entity.id,
            task_id=entity.task_id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            requested_by=entity.requested_by,
            question=_load_json(entity.question_json),
            context=_load_json(entity.context_json),
        )

    def to_response(self, entity: InterventionEntity) -> InterventionResponse:
        return InterventionResponse(
            id=entity.id,
            task_id=entity.task_id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            status=entity.status,
            requested_by=entity.requested_by,
            requested_at=entity.requested_at.isoformat() if entity.requested_at else "",
            question=_load_json(entity.question_json),
            context=_load_json(entity.context_json),
            resolved_by_user_id=entity.resolved_by_user_id,
            resolved_at=entity.resolved_at.isoformat() if entity.resolved_at else None,
            decision=_load_json(entity.decision_json),
            distillation=_load_json(entity.distillation_json),
            linked_asset_id=entity.linked_asset_id,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: InterventionListFilter) -> List[InterventionResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(InterventionEntity).filter(
                InterventionEntity.workspace_id == f.workspace_id
            )
            if f.task_id:
                query = query.filter(InterventionEntity.task_id == f.task_id)
            if f.status:
                query = query.filter(InterventionEntity.status == f.status)
            entities = query.order_by(desc(InterventionEntity.gmt_modified)).limit(f.limit).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()
