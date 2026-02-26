"""Channel database models and DAO.

This module defines the database entity and data access object for channels.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import ChannelRequest, ChannelResponse
from ..config import SERVER_APP_TABLE_NAME, ServeConfig


class ChannelEntity(Model):
    """Database entity for channels."""

    __tablename__ = SERVER_APP_TABLE_NAME

    # Primary key
    id = Column(String(64), primary_key=True, comment="Channel unique identifier")

    # Basic info
    name = Column(String(255), nullable=False, comment="Channel display name")
    channel_type = Column(String(32), nullable=False, comment="Channel type (dingtalk/feishu)")
    enabled = Column(Integer, default=1, comment="Whether channel is enabled (1=yes, 0=no)")

    # Platform specific config stored as JSON
    config = Column(JSON, nullable=False, comment="Platform-specific configuration")

    # Status
    status = Column(String(32), default="disconnected", comment="Channel status")
    last_connected = Column(DateTime, nullable=True, comment="Last successful connection time")
    last_error = Column(Text, nullable=True, comment="Last error message")

    # Timestamps
    gmt_created = Column(
        DateTime,
        name="gmt_create",
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )
    gmt_modified = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="Record update time",
    )

    def __repr__(self):
        return (
            f"ChannelEntity(id={self.id}, name='{self.name}', "
            f"channel_type='{self.channel_type}', enabled={self.enabled})"
        )


class ChannelDao(BaseDao[ChannelEntity, ChannelRequest, ChannelResponse]):
    """Data Access Object for channels."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[ChannelRequest, Dict[str, Any]]) -> ChannelEntity:
        """Convert a request to an entity.

        Args:
            request: The request object or dictionary.

        Returns:
            A ChannelEntity instance.
        """
        if isinstance(request, dict):
            request = ChannelRequest(**request)

        entity = ChannelEntity()

        # Generate ID if not provided
        entity.id = request.id or uuid.uuid4().hex[:16]

        # Basic fields
        entity.name = request.name
        entity.channel_type = request.channel_type
        entity.enabled = 1 if request.enabled else 0
        entity.config = request.config

        # Timestamps
        entity.gmt_created = datetime.now()
        entity.gmt_modified = datetime.now()

        return entity

    def to_request(self, entity: ChannelEntity) -> ChannelRequest:
        """Convert an entity to a request.

        Args:
            entity: The entity to convert.

        Returns:
            A ChannelRequest instance.
        """
        return ChannelRequest(
            id=entity.id,
            name=entity.name,
            channel_type=entity.channel_type,
            enabled=bool(entity.enabled),
            config=entity.config or {},
        )

    def to_response(self, entity: ChannelEntity) -> ChannelResponse:
        """Convert an entity to a response.

        Args:
            entity: The entity to convert.

        Returns:
            A ChannelResponse instance.
        """
        gmt_created_str = (
            entity.gmt_created.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_created
            else None
        )
        gmt_modified_str = (
            entity.gmt_modified.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_modified
            else None
        )
        last_connected_str = (
            entity.last_connected.strftime("%Y-%m-%d %H:%M:%S")
            if entity.last_connected
            else None
        )

        return ChannelResponse(
            id=entity.id,
            name=entity.name,
            channel_type=entity.channel_type,
            enabled=bool(entity.enabled),
            config=entity.config or {},
            status=entity.status or "disconnected",
            last_connected=last_connected_str,
            last_error=entity.last_error,
            gmt_created=gmt_created_str,
            gmt_modified=gmt_modified_str,
        )

    def update_entity_from_request(
        self, entity: ChannelEntity, request: Union[ChannelRequest, Dict[str, Any]]
    ) -> ChannelEntity:
        """Update an entity from a request.

        Args:
            entity: The entity to update.
            request: The request with updated values.

        Returns:
            The updated entity.
        """
        if isinstance(request, dict):
            request = ChannelRequest(**request)

        if request.name is not None:
            entity.name = request.name
        if request.channel_type is not None:
            entity.channel_type = request.channel_type
        if request.enabled is not None:
            entity.enabled = 1 if request.enabled else 0
        if request.config is not None:
            entity.config = request.config

        entity.gmt_modified = datetime.now()
        return entity

    def get_enabled_channels(self) -> list[ChannelEntity]:
        """Get all enabled channels.

        Returns:
            List of enabled channel entities.
        """
        with self.session() as session:
            return session.query(ChannelEntity).filter(ChannelEntity.enabled == 1).all()