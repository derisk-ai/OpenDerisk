"""Delivery entity."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Index, desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import DeliveryListFilter, DeliveryRequest, DeliveryResponse
from ..config import SERVER_APP_TABLE_NAME

DELIVERY_TABLE_NAME = SERVER_APP_TABLE_NAME


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


class DeliveryEntity(Model):
    __tablename__ = DELIVERY_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_id = Column(Integer, nullable=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    category = Column(String(32), nullable=False, default="notify")
    channel = Column(String(32), nullable=False)
    target = Column(String(512), nullable=False)
    title = Column(String(256), nullable=True)
    message = Column(Text, nullable=True)
    format = Column(String(32), nullable=False, default="message_card")
    status = Column(String(32), nullable=False, default="pending")
    require_intervention = Column(String(32), nullable=False, default="none")
    intervention_id = Column(Integer, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    result_json = Column(Text, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DeliveryDao(BaseDao[DeliveryEntity, DeliveryRequest, DeliveryResponse]):
    def from_request(self, request: Union[DeliveryRequest, Dict[str, Any]]) -> DeliveryEntity:
        data = request.dict() if isinstance(request, DeliveryRequest) else dict(request)
        data.pop("id", None)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("status", None)
        data.pop("intervention_id", None)
        data.pop("sent_at", None)
        data.pop("result_json", None)
        scheduled_at = data.pop("scheduled_at", None)
        entity = DeliveryEntity(**data)
        if scheduled_at:
            try:
                entity.scheduled_at = datetime.fromisoformat(scheduled_at)
            except Exception:
                entity.scheduled_at = None
        return entity

    def to_request(self, entity: DeliveryEntity) -> DeliveryRequest:
        return DeliveryRequest(
            id=entity.id,
            artifact_id=entity.artifact_id,
            task_id=entity.task_id,
            workspace_id=entity.workspace_id,
            category=entity.category,
            channel=entity.channel,
            target=entity.target,
            title=entity.title,
            message=entity.message,
            format=entity.format,
            require_intervention=entity.require_intervention,
            scheduled_at=entity.scheduled_at.isoformat() if entity.scheduled_at else None,
        )

    def to_response(self, entity: DeliveryEntity) -> DeliveryResponse:
        return DeliveryResponse(
            id=entity.id,
            artifact_id=entity.artifact_id,
            task_id=entity.task_id,
            workspace_id=entity.workspace_id,
            category=entity.category,
            channel=entity.channel,
            target=entity.target,
            title=entity.title,
            message=entity.message,
            format=entity.format,
            status=entity.status,
            require_intervention=entity.require_intervention,
            intervention_id=entity.intervention_id,
            scheduled_at=entity.scheduled_at.isoformat() if entity.scheduled_at else None,
            sent_at=entity.sent_at.isoformat() if entity.sent_at else None,
            result_json=_load_json(entity.result_json),
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: DeliveryListFilter) -> List[DeliveryResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(DeliveryEntity).filter(
                DeliveryEntity.workspace_id == f.workspace_id
            )
            if f.task_id:
                query = query.filter(DeliveryEntity.task_id == f.task_id)
            if f.status:
                query = query.filter(DeliveryEntity.status == f.status)
            if f.channel:
                query = query.filter(DeliveryEntity.channel == f.channel)
            entities = query.order_by(desc(DeliveryEntity.gmt_modified)).limit(f.limit).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()
