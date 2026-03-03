"""This is an auto-generated model file
You can define your own models and DAOs here
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Union
from derisk.storage.metadata._base_dao import REQ, RES

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    or_,
)

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import ServeRequest, ServerResponse
from ..config import SERVER_APP_TABLE_NAME, ServeConfig


class ServeEntity(Model):
    __tablename__ = SERVER_APP_TABLE_NAME
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    app_code = Column(String(255), nullable=False, comment="Current AI assistant code")
    app_name = Column(String(255), nullable=False, comment="Current AI assistant name")
    app_hub_code = Column(String(255), nullable=True, comment="app hub code")
    icon = Column(String(1024), nullable=True, comment="app icon, url")
    app_describe = Column(
        String(2255), nullable=False, comment="Current AI assistant describe"
    )
    language = Column(String(100), nullable=False, comment="gpts language")
    team_mode = Column(String(255), nullable=False, comment="Team work mode")
    team_context = Column(
        Text,
        nullable=True,
        comment="The execution logic and team member content that teams with different"
                " working modes rely on",
    )
    config_code = Column(String(255), nullable=True, comment="app config code")
    config_version = Column(String(255), nullable=True, comment="app config version")
    user_code = Column(String(255), nullable=True, comment="user code")
    sys_code = Column(String(255), nullable=True, comment="system app code")
    published = Column(String(64), nullable=True, comment="published")

    param_need = Column(
        Text,
        nullable=True,
        comment="Parameters required for application",
    )

    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )
    admins = Column(Text, nullable=True, comment="administrators")
    agent_version = Column(String(32), nullable=True, default="v1", comment="agent version: v1 or v2")

    __table_args__ = (UniqueConstraint("app_name", name="uk_gpts_app"),)

    def __repr__(self):
        return (
            f"ServeEntity(id={self.id},app_code={self.app_code},app_name={self.app_name},config_code={self.config_code} gmt_created='{self.created_at}', "
            f"gmt_modified='{self.updated_at}')"
        )


class ServeDao(BaseDao[ServeEntity, ServeRequest, ServerResponse]):
    """The DAO class for App"""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def create(self, request: REQ) -> RES:
        entry = self.from_request(request)
        with self.session(commit=False) as session:
            session.add(entry)
            session.commit()
            res = self.get_one({"app_code": entry.app_code})
            return res  # type: ignore


    def from_request(self, request: Union[ServeRequest, Dict[str, Any]]) -> ServeEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """


        if isinstance(request, ServeRequest):
            entity = ServeEntity(  # type: ignore
                app_code=request.app_code if request.app_code else uuid.uuid4().hex,  # type: ignore
                app_name=request.app_name,
                app_hub_code=request.app_hub_code,
                team_mode=request.team_mode,
                app_describe=request.app_describe,
                config_code=request.config_code,
                language=request.language,
                user_code=request.user_code,
                sys_code=request.sys_code,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                icon=request.icon,
                published=request.published,
                agent_version=getattr(request, 'agent_version', 'v1') or 'v1',

            )  # type: ignore
        else:
            request_dict = {
                "app_code": request.get("app_code") or uuid.uuid4().hex,
                "app_name": request.get('app_name'),
                "app_hub_code": request.get('app_hub_code'),
                "team_mode": request.get('team_mode'),
                "app_describe": request.get('app_describe'),
                "config_code": request.get('config_code'),
                "language": request.get('language', "zh"),
                "user_code": request.get('user_code'),
                "sys_code": request.get('sys_code'),
                "created_at": request.get('created_at'),
                "updated_at": request.get('updated_at'),
                "icon": request.get('icon'),
                "published": request.get("published", False),
                "agent_version": request.get('agent_version', 'v1'),

            }
            entity = ServeEntity(**request_dict)
        return entity

    def to_request(self, entity: ServeEntity) -> ServeRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        gmt_created_str = entity.created_at.strftime("%Y-%m-%d %H:%M:%S")
        gmt_modified_str = entity.updated_at.strftime("%Y-%m-%d %H:%M:%S")

        from derisk_serve.building.config.models.models import _load_team_context
        return ServeRequest.from_dict(
            {
                "app_code": entity.app_code,
                "app_name": entity.app_name,
                "app_hub_code": entity.app_hub_code,
                "language": entity.language,
                "app_describe": entity.app_describe,
                "team_mode": entity.team_mode,
                "config_code": entity.config_code,
                "config_version": entity.config_version,
                "team_context": _load_team_context(
                    entity.team_mode, entity.team_context, getattr(entity, 'agent_version', 'v1')       # type: ignore
                ),
                "user_code": entity.user_code,
                "icon": entity.icon,
                "sys_code": entity.sys_code,
                "is_collected":  "false",
                "created_at": entity.created_at,
                "updated_at": entity.updated_at,
                "details": [],
                "published": entity.published,
                "param_need": (
                    json.loads(entity.param_need) if entity.param_need else None    # type: ignore
                ),
                "hot_value": 0,
                "owner_name": entity.user_code,

                "admins": [],
                "agent_version": getattr(entity, 'agent_version', 'v1') or 'v1',

                # "keep_start_rounds": app_info.keep_start_rounds,
                # "keep_end_rounds": app_info.keep_end_rounds,
            }
        )

    def to_response(self, entity: ServeEntity) -> ServerResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            RES: The response
        """

        return self.to_request(entity)
