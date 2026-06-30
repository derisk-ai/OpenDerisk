"""Playbook + PlaybookVersion entities."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, Index, desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    PlaybookListFilter, PlaybookRequest, PlaybookResponse, PlaybookVersionResponse,
)
from ..config import SERVER_APP_TABLE_NAME

PLAYBOOK_TABLE_NAME = SERVER_APP_TABLE_NAME
PLAYBOOK_VERSION_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_version"


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


class PlaybookEntity(Model):
    __tablename__ = PLAYBOOK_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    scenario_type = Column(String(64), nullable=True)
    task_type = Column(String(32), nullable=False, default="routine")
    trigger_json = Column(Text, nullable=True)
    declaration_dsl_json = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(Integer, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PlaybookVersionEntity(Model):
    __tablename__ = PLAYBOOK_VERSION_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    playbook_id = Column(Integer, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    declaration_dsl_json = Column(Text, nullable=True)
    changelog = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)

    __table_args__ = (
        Index("uk_playbook_version", "playbook_id", "version", unique=True),
    )


class PlaybookDao(BaseDao[PlaybookEntity, PlaybookRequest, PlaybookResponse]):
    def from_request(self, request: Union[PlaybookRequest, Dict[str, Any]]) -> PlaybookEntity:
        data = request.dict() if isinstance(request, PlaybookRequest) else dict(request)
        data.pop("id", None)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("current_version", None)
        data.pop("created_by_user_id", None)
        trigger = data.pop("trigger", None) or {}
        declaration = data.pop("declaration", None) or {}
        entity = PlaybookEntity(**data)
        entity.trigger_json = _dump_json(trigger)
        entity.declaration_dsl_json = _dump_json(declaration)
        return entity

    def to_request(self, entity: PlaybookEntity) -> PlaybookRequest:
        return PlaybookRequest(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            scenario_type=entity.scenario_type,
            task_type=entity.task_type,
            trigger=_load_json(entity.trigger_json),
            declaration=_load_json(entity.declaration_dsl_json),
            is_active=entity.is_active,
        )

    def to_response(self, entity: PlaybookEntity) -> PlaybookResponse:
        return PlaybookResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            scenario_type=entity.scenario_type,
            task_type=entity.task_type,
            trigger=_load_json(entity.trigger_json),
            declaration=_load_json(entity.declaration_dsl_json),
            current_version=entity.current_version,
            is_active=entity.is_active,
            created_by_user_id=entity.created_by_user_id,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: PlaybookListFilter) -> List[PlaybookResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(PlaybookEntity).filter(
                PlaybookEntity.workspace_id == f.workspace_id
            )
            if f.scenario_type:
                query = query.filter(PlaybookEntity.scenario_type == f.scenario_type)
            if f.task_type:
                query = query.filter(PlaybookEntity.task_type == f.task_type)
            if f.is_active is not None:
                query = query.filter(PlaybookEntity.is_active == f.is_active)
            entities = query.order_by(desc(PlaybookEntity.gmt_modified)).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()


class PlaybookVersionDao(BaseDao[PlaybookVersionEntity, Dict[str, Any], PlaybookVersionResponse]):
    def from_request(self, request):
        raise NotImplementedError

    def to_request(self, entity):
        raise NotImplementedError

    def to_response(self, entity: PlaybookVersionEntity) -> PlaybookVersionResponse:
        return PlaybookVersionResponse(
            id=entity.id,
            playbook_id=entity.playbook_id,
            version=entity.version,
            declaration=_load_json(entity.declaration_dsl_json),
            changelog=entity.changelog,
            created_by_user_id=entity.created_by_user_id,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
        )

    def create_version(
        self, playbook_id: int, version: int, declaration: Dict[str, Any],
        changelog: Optional[str] = None, created_by_user_id: Optional[int] = None,
    ) -> PlaybookVersionEntity:
        session = self.get_raw_session()
        try:
            entity = PlaybookVersionEntity(
                playbook_id=playbook_id, version=version,
                declaration_dsl_json=_dump_json(declaration),
                changelog=changelog, created_by_user_id=created_by_user_id,
            )
            session.add(entity)
            session.commit()
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_versions(self, playbook_id: int) -> List[PlaybookVersionResponse]:
        session = self.get_raw_session()
        try:
            rows = (
                session.query(PlaybookVersionEntity)
                .filter(PlaybookVersionEntity.playbook_id == playbook_id)
                .order_by(desc(PlaybookVersionEntity.version))
                .all()
            )
            return [self.to_response(r) for r in rows]
        finally:
            session.close()
