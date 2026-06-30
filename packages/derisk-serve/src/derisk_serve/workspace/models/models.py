"""Workspace / WorkspaceMember / WorkspaceResource entities + DAOs."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    desc,
    or_,
)

from derisk.storage.metadata import BaseDao, Model
from derisk.util import PaginationResult

from ..api.schemas import (
    WorkspaceListFilter,
    WorkspaceMemberRequest,
    WorkspaceMemberResponse,
    WorkspaceRequest,
    WorkspaceResourceListRequest,
    WorkspaceResourceRequest,
    WorkspaceResourceResponse,
    WorkspaceResponse,
)
from ..config import SERVER_APP_TABLE_NAME

WORKSPACE_TABLE_NAME = SERVER_APP_TABLE_NAME
WORKSPACE_MEMBER_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_member"
WORKSPACE_RESOURCE_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_resource"
WORKSPACE_CONV_LINK_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_conv_link"


def _dump_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: Any) -> Any:
    if not value:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


class WorkspaceEntity(Model):
    __tablename__ = WORKSPACE_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_code = Column(String(64), nullable=False, unique=True, comment="unique workspace code")
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(32), nullable=False, default="scenario", comment="scenario / team")
    scenario_type = Column(String(64), nullable=True, comment="sre / data_ops / ...")
    owner_user_id = Column(Integer, nullable=False)
    default_agent_app_code = Column(String(255), nullable=True)
    settings_json = Column(Text, nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WorkspaceMemberEntity(Model):
    __tablename__ = WORKSPACE_MEMBER_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    role = Column(String(32), nullable=False, default="contributor")

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uk_workspace_member"),
    )


class WorkspaceResourceEntity(Model):
    __tablename__ = WORKSPACE_RESOURCE_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    type = Column(String(32), nullable=False, comment="data_source/knowledge_space/environment/mcp/skill/llm_model")
    name = Column(String(128), nullable=False)
    category = Column(String(16), nullable=False, default="scenario_bound")
    physical_ref = Column(String(255), nullable=True)
    config_json = Column(Text, nullable=True)
    access_mode = Column(String(16), nullable=False, default="read")
    is_active = Column(Boolean, nullable=False, default=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("workspace_id", "type", "name", name="uk_workspace_resource"),
    )


class WorkspaceConversationLinkEntity(Model):
    """Links chat_history.conv_uid to a workspace (and optionally a Task).
    Avoids modifying the canonical chat_history table.
    """

    __tablename__ = WORKSPACE_CONV_LINK_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    conv_uid = Column(String(255), nullable=False, unique=True, index=True)
    task_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    is_current = Column(Boolean, nullable=False, default=False, index=True)
    title = Column(String(255), nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WorkspaceConversationLinkDao(
    BaseDao[
        WorkspaceConversationLinkEntity,
        Dict[str, Any],
        Dict[str, Any],
    ]
):
    """DAO for WorkspaceConversationLink — uses raw session for simplicity."""

    def from_request(self, request):
        raise NotImplementedError

    def to_request(self, entity):
        raise NotImplementedError

    def to_response(self, entity):
        return {
            "id": entity.id,
            "workspace_id": entity.workspace_id,
            "conv_uid": entity.conv_uid,
            "task_id": entity.task_id,
            "user_id": entity.user_id,
            "title": entity.title,
            "is_current": entity.is_current,
            "gmt_created": entity.gmt_created.isoformat() if entity.gmt_created else "",
            "gmt_modified": entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        }

    def link(
        self,
        workspace_id: int,
        conv_uid: str,
        task_id: Optional[int] = None,
        user_id: Optional[int] = None,
        title: Optional[str] = None,
        set_current: bool = False,
    ) -> WorkspaceConversationLinkEntity:
        session = self.get_raw_session()
        try:
            existing = (
                session.query(WorkspaceConversationLinkEntity)
                .filter(WorkspaceConversationLinkEntity.conv_uid == conv_uid)
                .first()
            )
            if existing:
                existing.workspace_id = workspace_id
                if task_id is not None:
                    existing.task_id = task_id
                if user_id is not None:
                    existing.user_id = user_id
                if title is not None:
                    existing.title = title
                session.commit()
                if set_current:
                    self._set_current_internal(workspace_id, user_id, conv_uid)
                return existing
            row = WorkspaceConversationLinkEntity(
                workspace_id=workspace_id,
                conv_uid=conv_uid,
                task_id=task_id,
                user_id=user_id,
                title=title,
                is_current=False,
            )
            session.add(row)
            session.commit()
            if set_current:
                self._set_current_internal(workspace_id, user_id, conv_uid)
            return row
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _set_current_internal(
        self,
        workspace_id: int,
        user_id: Optional[int],
        conv_uid: str,
    ) -> None:
        session = self.get_raw_session()
        try:
            session.query(WorkspaceConversationLinkEntity).filter(
                WorkspaceConversationLinkEntity.workspace_id == workspace_id,
                WorkspaceConversationLinkEntity.user_id == user_id,
                WorkspaceConversationLinkEntity.conv_uid != conv_uid,
            ).update(
                {WorkspaceConversationLinkEntity.is_current: False},
                synchronize_session=False,
            )
            session.query(WorkspaceConversationLinkEntity).filter(
                WorkspaceConversationLinkEntity.workspace_id == workspace_id,
                WorkspaceConversationLinkEntity.user_id == user_id,
                WorkspaceConversationLinkEntity.conv_uid == conv_uid,
            ).update(
                {WorkspaceConversationLinkEntity.is_current: True},
                synchronize_session=False,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_current(
        self, workspace_id: int, user_id: Optional[int]
    ) -> Optional[WorkspaceConversationLinkEntity]:
        session = self.get_raw_session()
        try:
            return (
                session.query(WorkspaceConversationLinkEntity)
                .filter(
                    WorkspaceConversationLinkEntity.workspace_id == workspace_id,
                    WorkspaceConversationLinkEntity.user_id == user_id,
                    WorkspaceConversationLinkEntity.is_current.is_(True),
                )
                .order_by(WorkspaceConversationLinkEntity.gmt_modified.desc())
                .first()
            )
        finally:
            session.close()

    def rename(
        self, conv_uid: str, title: str
    ) -> Optional[WorkspaceConversationLinkEntity]:
        session = self.get_raw_session()
        try:
            entity = (
                session.query(WorkspaceConversationLinkEntity)
                .filter(WorkspaceConversationLinkEntity.conv_uid == conv_uid)
                .first()
            )
            if entity is None:
                return None
            entity.title = title
            session.commit()
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_by_conv(self, conv_uid: str) -> Optional[WorkspaceConversationLinkEntity]:
        session = self.get_raw_session()
        try:
            return (
                session.query(WorkspaceConversationLinkEntity)
                .filter(WorkspaceConversationLinkEntity.conv_uid == conv_uid)
                .first()
            )
        finally:
            session.close()

    def list_by_workspace(
        self, workspace_id: int, user_id: Optional[int] = None, limit: int = 100
    ) -> List[WorkspaceConversationLinkEntity]:
        session = self.get_raw_session()
        try:
            query = session.query(WorkspaceConversationLinkEntity).filter(
                WorkspaceConversationLinkEntity.workspace_id == workspace_id
            )
            if user_id is not None:
                query = query.filter(WorkspaceConversationLinkEntity.user_id == user_id)
            return (
                query.order_by(WorkspaceConversationLinkEntity.gmt_modified.desc())
                .limit(limit)
                .all()
            )
        finally:
            session.close()


# ----------------------------- DAOs -----------------------------
class WorkspaceDao(BaseDao[WorkspaceEntity, WorkspaceRequest, WorkspaceResponse]):
    def from_request(self, request: Union[WorkspaceRequest, Dict[str, Any]]) -> WorkspaceEntity:
        data = request.dict() if isinstance(request, WorkspaceRequest) else dict(request)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("member_count", None)
        settings = data.pop("settings", None) or {}
        entity = WorkspaceEntity(**data)
        entity.settings_json = _dump_json(settings)
        if not entity.workspace_code:
            import uuid as _uuid
            entity.workspace_code = f"ws_{_uuid.uuid4().hex[:12]}"
        return entity

    def to_request(self, entity: WorkspaceEntity) -> WorkspaceRequest:
        return WorkspaceRequest(
            workspace_code=entity.workspace_code,
            name=entity.name,
            description=entity.description,
            type=entity.type,
            scenario_type=entity.scenario_type,
            owner_user_id=entity.owner_user_id,
            default_agent_app_code=entity.default_agent_app_code,
            settings=_load_json(entity.settings_json),
            is_archived=entity.is_archived,
        )

    def to_response(self, entity: WorkspaceEntity, member_count: int = 0) -> WorkspaceResponse:
        return WorkspaceResponse(
            id=entity.id,
            workspace_code=entity.workspace_code,
            name=entity.name,
            description=entity.description,
            type=entity.type,
            scenario_type=entity.scenario_type,
            owner_user_id=entity.owner_user_id,
            default_agent_app_code=entity.default_agent_app_code,
            settings=_load_json(entity.settings_json),
            is_archived=entity.is_archived,
            member_count=member_count,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def filter_list(
        self, filter_request: WorkspaceListFilter
    ) -> List[WorkspaceResponse]:
        """List workspaces. If user_id is provided, only workspaces where the user is a member."""
        session = self.get_raw_session()
        try:
            query = session.query(WorkspaceEntity)
            if not filter_request.include_archived:
                query = query.filter(WorkspaceEntity.is_archived == False)
            if filter_request.scenario_type:
                query = query.filter(WorkspaceEntity.scenario_type == filter_request.scenario_type)
            if filter_request.user_id is not None:
                member_subq = (
                    session.query(WorkspaceMemberEntity.workspace_id)
                    .filter(WorkspaceMemberEntity.user_id == filter_request.user_id)
                    .subquery()
                )
                query = query.filter(or_(
                    WorkspaceEntity.id.in_(member_subq),
                    WorkspaceEntity.owner_user_id == filter_request.user_id,
                ))
            entities = query.order_by(desc(WorkspaceEntity.gmt_modified)).all()
            return [self.to_response(e) for e in entities]
        finally:
            session.close()


class WorkspaceMemberDao(BaseDao[WorkspaceMemberEntity, WorkspaceMemberRequest, WorkspaceMemberResponse]):
    def from_request(self, request: Union[WorkspaceMemberRequest, Dict[str, Any]]) -> WorkspaceMemberEntity:
        data = request.dict() if isinstance(request, WorkspaceMemberRequest) else dict(request)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        data.pop("user_name", None)
        return WorkspaceMemberEntity(**data)

    def to_request(self, entity: WorkspaceMemberEntity) -> WorkspaceMemberRequest:
        return WorkspaceMemberRequest(
            workspace_id=entity.workspace_id,
            user_id=entity.user_id,
            role=entity.role,
        )

    def to_response(self, entity: WorkspaceMemberEntity, user_name: Optional[str] = None) -> WorkspaceMemberResponse:
        return WorkspaceMemberResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            user_id=entity.user_id,
            user_name=user_name,
            role=entity.role,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_workspace(self, workspace_id: int) -> List[WorkspaceMemberEntity]:
        session = self.get_raw_session()
        try:
            return (
                session.query(WorkspaceMemberEntity)
                .filter(WorkspaceMemberEntity.workspace_id == workspace_id)
                .all()
            )
        finally:
            session.close()

    def count_by_workspace(self, workspace_id: int) -> int:
        session = self.get_raw_session()
        try:
            return (
                session.query(WorkspaceMemberEntity)
                .filter(WorkspaceMemberEntity.workspace_id == workspace_id)
                .count()
            )
        finally:
            session.close()

    def get_role(self, workspace_id: int, user_id: int) -> Optional[str]:
        session = self.get_raw_session()
        try:
            row = (
                session.query(WorkspaceMemberEntity)
                .filter(
                    and_(
                        WorkspaceMemberEntity.workspace_id == workspace_id,
                        WorkspaceMemberEntity.user_id == user_id,
                    )
                )
                .first()
            )
            return row.role if row else None
        finally:
            session.close()


class WorkspaceResourceDao(BaseDao[WorkspaceResourceEntity, WorkspaceResourceRequest, WorkspaceResourceResponse]):
    def from_request(self, request: Union[WorkspaceResourceRequest, Dict[str, Any]]) -> WorkspaceResourceEntity:
        data = request.dict() if isinstance(request, WorkspaceResourceRequest) else dict(request)
        data.pop("gmt_created", None)
        data.pop("gmt_modified", None)
        config = data.pop("config", None) or {}
        entity = WorkspaceResourceEntity(**data)
        entity.config_json = _dump_json(config)
        return entity

    def to_request(self, entity: WorkspaceResourceEntity) -> WorkspaceResourceRequest:
        return WorkspaceResourceRequest(
            workspace_id=entity.workspace_id,
            type=entity.type,
            name=entity.name,
            category=entity.category,
            physical_ref=entity.physical_ref,
            config=_load_json(entity.config_json),
            access_mode=entity.access_mode,
            is_active=entity.is_active,
        )

    def to_response(self, entity: WorkspaceResourceEntity) -> WorkspaceResourceResponse:
        return WorkspaceResourceResponse(
            id=entity.id,
            workspace_id=entity.workspace_id,
            type=entity.type,
            name=entity.name,
            category=entity.category,
            physical_ref=entity.physical_ref,
            config=_load_json(entity.config_json),
            access_mode=entity.access_mode,
            is_active=entity.is_active,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )

    def list_by_workspace(
        self, workspace_id: int, type_filter: Optional[str] = None
    ) -> List[WorkspaceResourceEntity]:
        session = self.get_raw_session()
        try:
            query = session.query(WorkspaceResourceEntity).filter(
                WorkspaceResourceEntity.workspace_id == workspace_id
            )
            if type_filter:
                query = query.filter(WorkspaceResourceEntity.type == type_filter)
            return query.order_by(desc(WorkspaceResourceEntity.gmt_modified)).all()
        finally:
            session.close()
