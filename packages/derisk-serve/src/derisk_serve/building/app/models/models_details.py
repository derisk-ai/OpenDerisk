"""This is an auto-generated model file
You can define your own models and DAOs here
"""

from datetime import datetime
from typing import Any, Dict, Union, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from derisk.agent import AgentResource
from derisk.storage.metadata import BaseDao, Model

from ..api.schema_app_detail import AppDetailServeRequest, AppDetailServerResponse
from ..config import ServeConfig, SERVER_APP_DETAIL_TABLE_NAME


class AppDetailServeEntity(Model):
    __tablename__ = SERVER_APP_DETAIL_TABLE_NAME
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    app_code = Column(String(255), nullable=False, comment="Current AI assistant code")
    app_name = Column(String(255), nullable=False, comment="Current AI assistant name")
    type = Column(
        String(255),
        nullable=False,
        comment="bind detail agent type. 'app' or 'agent', default 'agent'",
    )
    agent_name = Column(String(255), nullable=False, comment=" Agent name")
    agent_role = Column(String(255), nullable=False, comment=" Agent role")
    agent_describe = Column(Text, nullable=True, comment=" Agent describe")
    node_id = Column(
        String(255), nullable=False, comment="Current AI assistant Agent Node id"
    )
    resources = Column(Text, nullable=True, comment="Agent bind  resource")
    prompt_template = Column(Text, nullable=True, comment="Agent bind  template")
    llm_strategy = Column(String(25), nullable=True, comment="Agent use llm strategy")
    llm_strategy_value = Column(
        Text, nullable=True, comment="Agent use llm strategy value"
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

    __table_args__ = (
        UniqueConstraint(
            "app_name", "agent_name", "node_id", name="uk_gpts_app_agent_node"
        ),
    )

    def __repr__(self):
        return (
            f"ServeEntity(id={self.id},app_code={self.app_code},app_name={self.app_name},agent_role={self.agent_role} gmt_created='{self.created_at}', "
            f"gmt_modified='{self.updated_at}')"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "app_code": self.app_code,
            "app_name": self.app_name,
            "type": self.type,
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_describe": self.agent_describe,
            "node_id": self.node_id,
            "resources": AgentResource.from_json_list_str(self.resources),
            "prompt_template": self.prompt_template,
            "llm_strategy": self.llm_strategy,
            "llm_strategy_value": self.llm_strategy_value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AppDetailServeDao(BaseDao[AppDetailServeEntity, AppDetailServeRequest, AppDetailServerResponse]):
    """The DAO class for App"""

    def __init__(self, serve_config: Optional[ServeConfig] = None):
        super().__init__()
        self._serve_config = serve_config if serve_config else None

    def from_request(self, request: Union[AppDetailServeRequest, Dict[str, Any]]) -> AppDetailServeEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        request_dict = (
            request.to_dict() if isinstance(request, AppDetailServeRequest) else request
        )
        entity = AppDetailServeEntity(**request_dict)
        return entity

    def to_request(self, entity: AppDetailServeEntity) -> AppDetailServeRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        gmt_created_str = entity.created_at.strftime("%Y-%m-%d %H:%M:%S")
        gmt_modified_str = entity.updated_at.strftime("%Y-%m-%d %H:%M:%S")

        return AppDetailServeRequest.from_dict(
            {
                "app_code": entity.app_code,
                "app_name": entity.app_name,
                "type": entity.type,
                "agent_name": entity.agent_name,
                "agent_role": entity.agent_role,
                "agent_describe": entity.agent_describe,
                "node_id": entity.node_id,
                "resources": AgentResource.from_json_list_str(entity.resources),
                "prompt_template": entity.prompt_template,
                "llm_strategy": entity.llm_strategy,
                "llm_strategy_value": entity.llm_strategy_value,
                "created_at": entity.created_at,
                "updated_at": entity.updated_at,
            }
        )

    def to_response(self, entity: AppDetailServeEntity) -> AppDetailServerResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            RES: The response
        """

        return self.to_request(entity)
