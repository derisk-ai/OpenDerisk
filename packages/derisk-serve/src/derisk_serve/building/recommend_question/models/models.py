"""This is an auto-generated model file
You can define your own models and DAOs here
"""
import json
from datetime import datetime
from typing import Any, Dict, Union

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


def _is_true(valid) -> bool:
    if isinstance(valid, str):
        return valid and valid.lower() in {"1", "true"}

    return True if valid else False

class ServeEntity(Model):
    __tablename__ = SERVER_APP_TABLE_NAME
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    app_code = Column(String(255), nullable=False, comment="Current AI assistant code")
    user_code = Column(String(255), nullable=True, comment="user code")
    sys_code = Column(String(255), nullable=True, comment="system app code")
    gmt_create = Column(DateTime, default=datetime.utcnow, comment="create time")
    gmt_modified = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )
    question = Column(Text, default=None, comment="question")
    valid = Column(String(31), default=True, comment="is valid")
    params = Column(Text, nullable=True, comment="is valid")
    chat_mode = Column(
        String(31),
        nullable=True,
        comment="chat_mode, such as chat_knowledge, chat_normal",
    )
    is_hot_question = Column(
        String(10),
        default=False,
        comment="hot question would be displayed on the main page.",
    )
    __table_args__ = (Index("idx_rec_q_app_code", "app_code"),)


    def __repr__(self):
        return (
            f"ServeEntity(id={self.id}, gmt_created='{self.gmt_created}', "
            f"gmt_modified='{self.gmt_modified}')"
        )


class ServeDao(BaseDao[ServeEntity, ServeRequest, ServerResponse]):
    """The DAO class for Building/recommendQuestion"""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[ServeRequest, Dict[str, Any]]) -> ServeEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        request_dict = (
            request.to_dict() if isinstance(request, ServeRequest) else request
        )
        entity = ServeEntity(**request_dict)
        # TODO implement your own logic here, transfer the request_dict to an entity
        return entity

    def to_request(self, entity: ServeEntity) -> ServeRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return ServeRequest.from_dict(
            {
                "id": entity.id,
                "app_code": entity.app_code,
                "question": entity.question,
                "user_code": entity.user_code,
                "sys_code": entity.sys_code,
                "gmt_create": entity.gmt_create,
                "gmt_modified": entity.gmt_modified,
                "params": json.loads(entity.params),
                "valid": _is_true(entity.valid),
                "chat_mode": entity.chat_mode,
                "is_hot_question": entity.is_hot_question,
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


    def delete_by_app_code(self, app_code: str):
        """Delete by app code

        Args:
            app_code (str): The app code

        Returns:
        """
        with self.session() as session:
            qry = session.query(ServeEntity)
            qry = qry.filter(ServeEntity.app_code == app_code)
            qry.delete()
