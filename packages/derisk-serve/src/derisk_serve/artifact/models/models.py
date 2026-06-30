"""Artifact + ArtifactVersion entities."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, Index, desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    ArtifactListFilter, ArtifactRequest, ArtifactResponse, ArtifactVersionResponse,
)
from ..config import SERVER_APP_TABLE_NAME

ARTIFACT_TABLE_NAME = SERVER_APP_TABLE_NAME
ARTIFACT_VERSION_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_version"


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


class ArtifactEntity(Model):
    __tablename__ = ARTIFACT_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    type = Column(String(32), nullable=False)
    title = Column(String(256), nullable=False)
    content_ref = Column(String(512), nullable=True)
    content_text = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    provenance_json = Column(Text, nullable=True)
    is_shared = Column(Boolean, nullable=False, default=False)
    created_by_agent = Column(String(128), nullable=True)
    created_by_user = Column(Integer, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ArtifactVersionEntity(Model):
    __tablename__ = ARTIFACT_VERSION_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_id = Column(Integer, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_ref = Column(String(512), nullable=True)
    diff_summary = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)

    __table_args__ = (
        Index("uk_artifact_version", "artifact_id", "version", unique=True),
    )


class ArtifactDao(BaseDao[ArtifactEntity, ArtifactRequest, ArtifactResponse]):
    def from_request(self, request: Union[ArtifactRequest, Dict[str, Any]]) -> ArtifactEntity:
        data = request.dict() if isinstance(request, ArtifactRequest) else dict(request)
        data.pop("id", None)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("current_version", None)
        prov = data.pop("provenance", None) or {}
        entity = ArtifactEntity(**data)
        entity.provenance_json = _dump_json(prov)
        return entity

    def to_request(self, entity: ArtifactEntity) -> ArtifactRequest:
        return ArtifactRequest(
            id=entity.id,
            task_id=entity.task_id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            title=entity.title,
            content_ref=entity.content_ref,
            content_text=entity.content_text,
            provenance=_load_json(entity.provenance_json),
            is_shared=entity.is_shared,
            created_by_agent=entity.created_by_agent,
            created_by_user=entity.created_by_user,
        )

    def to_response(self, entity: ArtifactEntity) -> ArtifactResponse:
        return ArtifactResponse(
            id=entity.id,
            task_id=entity.task_id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            title=entity.title,
            content_ref=entity.content_ref,
            content_text=entity.content_text,
            current_version=entity.current_version,
            provenance=_load_json(entity.provenance_json),
            is_shared=entity.is_shared,
            created_by_agent=entity.created_by_agent,
            created_by_user=entity.created_by_user,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: ArtifactListFilter) -> List[ArtifactResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(ArtifactEntity).filter(
                ArtifactEntity.workspace_id == f.workspace_id
            )
            if f.task_id:
                query = query.filter(ArtifactEntity.task_id == f.task_id)
            if f.type:
                query = query.filter(ArtifactEntity.type == f.type)
            entities = query.order_by(desc(ArtifactEntity.gmt_modified)).limit(f.limit).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()


class ArtifactVersionDao(BaseDao[ArtifactVersionEntity, Dict[str, Any], ArtifactVersionResponse]):
    def from_request(self, request):
        raise NotImplementedError

    def to_request(self, entity):
        raise NotImplementedError

    def to_response(self, entity: ArtifactVersionEntity) -> ArtifactVersionResponse:
        return ArtifactVersionResponse(
            id=entity.id,
            artifact_id=entity.artifact_id,
            version=entity.version,
            content_ref=entity.content_ref,
            diff_summary=entity.diff_summary,
            created_by=entity.created_by,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
        )

    def create_version(
        self, artifact_id: int, version: int, content_ref: Optional[str] = None,
        diff_summary: Optional[str] = None, created_by: Optional[str] = None,
    ) -> ArtifactVersionEntity:
        session = self.get_raw_session()
        try:
            entity = ArtifactVersionEntity(
                artifact_id=artifact_id, version=version,
                content_ref=content_ref, diff_summary=diff_summary,
                created_by=created_by,
            )
            session.add(entity)
            session.commit()
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_versions(self, artifact_id: int) -> List[ArtifactVersionResponse]:
        session = self.get_raw_session()
        try:
            rows = (
                session.query(ArtifactVersionEntity)
                .filter(ArtifactVersionEntity.artifact_id == artifact_id)
                .order_by(desc(ArtifactVersionEntity.version))
                .all()
            )
            return [self.to_response(r) for r in rows]
        finally:
            session.close()
