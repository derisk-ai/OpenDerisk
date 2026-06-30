"""WorkspaceAsset + AssetVersion + TaskAssetLink entities."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, Index, desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    AssetListFilter, AssetRequest, AssetResponse, AssetSearchRequest,
    AssetVersionResponse, TaskAssetLinkResponse,
)
from ..config import SERVER_APP_TABLE_NAME

ASSET_TABLE_NAME = SERVER_APP_TABLE_NAME
ASSET_VERSION_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_version"
TASK_ASSET_LINK_TABLE_NAME = "server_app_task_asset_link"


def _dump_json(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _load_json(v):
    if not v:
        return [] if v == [] else None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


class AssetEntity(Model):
    __tablename__ = ASSET_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    type = Column(String(32), nullable=False)
    name = Column(String(256), nullable=False)
    description = Column(String(1024), nullable=True)
    scope = Column(String(32), nullable=False, default="workspace")
    content_ref = Column(String(512), nullable=True)
    content_text = Column(Text, nullable=True)
    current_version = Column(Integer, nullable=False, default=1)
    source_task_id = Column(Integer, nullable=True, index=True)
    source_artifact_id = Column(Integer, nullable=True)
    tags_json = Column(Text, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(128), nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AssetVersionEntity(Model):
    __tablename__ = ASSET_VERSION_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_ref = Column(String(512), nullable=True)
    diff_summary = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)

    __table_args__ = (
        Index("uk_workspace_asset_version", "asset_id", "version", unique=True),
    )


class TaskAssetLinkEntity(Model):
    __tablename__ = TASK_ASSET_LINK_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    asset_id = Column(Integer, nullable=False, index=True)
    link_type = Column(String(32), nullable=False)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)

    __table_args__ = (
        Index("uk_task_asset_link", "task_id", "asset_id", "link_type", unique=True),
    )


class AssetDao(BaseDao[AssetEntity, AssetRequest, AssetResponse]):
    def from_request(self, request: Union[AssetRequest, Dict[str, Any]]) -> AssetEntity:
        data = request.dict() if isinstance(request, AssetRequest) else dict(request)
        data.pop("id", None)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("current_version", None)
        tags = data.pop("tags", None) or []
        source_artifact_id = data.pop("source_artifact_id", None)
        entity = AssetEntity(**data)
        entity.tags_json = _dump_json(tags)
        entity.source_artifact_id = source_artifact_id
        return entity

    def to_request(self, entity: AssetEntity) -> AssetRequest:
        return AssetRequest(
            id=entity.id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            name=entity.name,
            description=entity.description,
            scope=entity.scope,
            content_ref=entity.content_ref,
            content_text=entity.content_text,
            source_task_id=entity.source_task_id,
            source_artifact_id=entity.source_artifact_id,
            tags=_load_json(entity.tags_json) or [],
            is_published=entity.is_published,
            created_by=entity.created_by,
        )

    def to_response(self, entity: AssetEntity) -> AssetResponse:
        return AssetResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            name=entity.name,
            description=entity.description,
            scope=entity.scope,
            content_ref=entity.content_ref,
            content_text=entity.content_text,
            current_version=entity.current_version,
            source_task_id=entity.source_task_id,
            source_artifact_id=entity.source_artifact_id,
            tags=_load_json(entity.tags_json) or [],
            is_published=entity.is_published,
            created_by=entity.created_by,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_filter(self, f: AssetListFilter) -> List[AssetResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(AssetEntity).filter(
                AssetEntity.workspace_id == f.workspace_id
            )
            if f.type:
                query = query.filter(AssetEntity.type == f.type)
            if f.source_task_id:
                query = query.filter(AssetEntity.source_task_id == f.source_task_id)
            if f.is_published is not None:
                query = query.filter(AssetEntity.is_published == f.is_published)
            entities = query.order_by(desc(AssetEntity.gmt_modified)).limit(f.limit).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()

    def search(self, req: AssetSearchRequest) -> List[AssetResponse]:
        session = self.get_raw_session()
        try:
            query = session.query(AssetEntity).filter(
                AssetEntity.workspace_id == req.workspace_id
            )
            if req.type:
                query = query.filter(AssetEntity.type == req.type)
            if req.query:
                like = f"%{req.query}%"
                query = query.filter(
                    (AssetEntity.name.like(like))
                    | (AssetEntity.description.like(like))
                    | (AssetEntity.content_text.like(like))
                )
            entities = query.order_by(desc(AssetEntity.gmt_modified)).limit(req.limit).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()


class AssetVersionDao(BaseDao[AssetVersionEntity, Dict[str, Any], AssetVersionResponse]):
    def from_request(self, request):
        raise NotImplementedError

    def to_request(self, entity):
        raise NotImplementedError

    def to_response(self, entity: AssetVersionEntity) -> AssetVersionResponse:
        return AssetVersionResponse(
            id=entity.id,
            asset_id=entity.asset_id,
            version=entity.version,
            content_ref=entity.content_ref,
            diff_summary=entity.diff_summary,
            created_by=entity.created_by,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
        )

    def create_version(
        self, asset_id: int, version: int, content_ref: Optional[str] = None,
        diff_summary: Optional[str] = None, created_by: Optional[str] = None,
    ) -> AssetVersionEntity:
        session = self.get_raw_session()
        try:
            entity = AssetVersionEntity(
                asset_id=asset_id, version=version,
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

    def list_versions(self, asset_id: int) -> List[AssetVersionResponse]:
        session = self.get_raw_session()
        try:
            rows = (
                session.query(AssetVersionEntity)
                .filter(AssetVersionEntity.asset_id == asset_id)
                .order_by(desc(AssetVersionEntity.version))
                .all()
            )
            return [self.to_response(r) for r in rows]
        finally:
            session.close()


class TaskAssetLinkDao(BaseDao[TaskAssetLinkEntity, Dict[str, Any], TaskAssetLinkResponse]):
    def from_request(self, request):
        raise NotImplementedError

    def to_request(self, entity):
        raise NotImplementedError

    def to_response(self, entity: TaskAssetLinkEntity) -> TaskAssetLinkResponse:
        return TaskAssetLinkResponse(
            id=entity.id,
            task_id=entity.task_id,
            asset_id=entity.asset_id,
            link_type=entity.link_type,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
        )

    def link(self, task_id: int, asset_id: int, link_type: str) -> TaskAssetLinkEntity:
        session = self.get_raw_session()
        try:
            existing = session.query(TaskAssetLinkEntity).filter(
                TaskAssetLinkEntity.task_id == task_id,
                TaskAssetLinkEntity.asset_id == asset_id,
                TaskAssetLinkEntity.link_type == link_type,
            ).first()
            if existing:
                return existing
            entity = TaskAssetLinkEntity(
                task_id=task_id, asset_id=asset_id, link_type=link_type,
            )
            session.add(entity)
            session.commit()
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_by_task(self, task_id: int) -> List[TaskAssetLinkResponse]:
        session = self.get_raw_session()
        try:
            rows = (
                session.query(TaskAssetLinkEntity)
                .filter(TaskAssetLinkEntity.task_id == task_id)
                .all()
            )
            return [self.to_response(r) for r in rows]
        finally:
            session.close()
