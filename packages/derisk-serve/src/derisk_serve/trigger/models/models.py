"""TriggerSource entity."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    TriggerListFilter, TriggerSourceRequest, TriggerSourceResponse,
)
from ..config import SERVER_APP_TABLE_NAME

TRIGGER_TABLE_NAME = SERVER_APP_TABLE_NAME


def _dump_json(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _load_json(v):
    if not v:
        return {}
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}


class TriggerSourceEntity(Model):
    __tablename__ = TRIGGER_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    type = Column(String(32), nullable=False)
    name = Column(String(256), nullable=False)
    config_json = Column(Text, nullable=True)
    target_playbook_id = Column(Integer, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_fired_at = Column(DateTime, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TriggerSourceDao(BaseDao[TriggerSourceEntity, TriggerSourceRequest, TriggerSourceResponse]):
    def from_request(self, request: Union[TriggerSourceRequest, Dict[str, Any]]) -> TriggerSourceEntity:
        data = request.dict() if isinstance(request, TriggerSourceRequest) else dict(request)
        data.pop("id", None)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("last_fired_at", None)
        config = data.pop("config", None) or {}
        entity = TriggerSourceEntity(**data)
        entity.config_json = _dump_json(config)
        return entity

    def to_request(self, entity: TriggerSourceEntity) -> TriggerSourceRequest:
        return TriggerSourceRequest(
            id=entity.id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            name=entity.name,
            config=_load_json(entity.config_json),
            target_playbook_id=entity.target_playbook_id,
            is_active=entity.is_active,
        )

    def to_response(self, entity: TriggerSourceEntity) -> TriggerSourceResponse:
        return TriggerSourceResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            name=entity.name,
            config=_load_json(entity.config_json),
            target_playbook_id=entity.target_playbook_id,
            is_active=entity.is_active,
            last_fired_at=entity.last_fired_at.isoformat() if entity.last_fired_at else None,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: TriggerListFilter) -> List[TriggerSourceResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.workspace_id == f.workspace_id
            )
            if f.type:
                query = query.filter(TriggerSourceEntity.type == f.type)
            if f.is_active is not None:
                query = query.filter(TriggerSourceEntity.is_active == f.is_active)
            entities = query.order_by(desc(TriggerSourceEntity.gmt_modified)).limit(f.limit).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()
