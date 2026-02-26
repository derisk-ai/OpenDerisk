"""Channel service implementation.

This module provides the main service for channel management.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

from derisk.component import SystemApp
from derisk.storage.metadata._base_dao import REQ, RES
from derisk_serve.core import BaseService

from ..api.schemas import ChannelRequest, ChannelResponse, ChannelTestResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import ChannelDao, ChannelEntity

logger = logging.getLogger(__name__)


class Service(BaseService[ChannelEntity, ChannelRequest, ChannelResponse]):
    """Channel management service.

    This service manages channel configurations and provides
    methods for channel CRUD operations and connection testing.
    """

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[ChannelDao] = None,
    ):
        """Initialize the channel service.

        Args:
            system_app: The system application instance.
            config: The service configuration.
            dao: Optional DAO instance for database operations.
        """
        super().__init__(system_app)
        self._config = config
        self._dao = dao

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service.

        Args:
            system_app: The system application instance.
        """
        super().init_app(system_app)
        self._dao = self._dao or ChannelDao(self._config)

    @property
    def dao(self) -> ChannelDao:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._config

    def create(self, request: REQ) -> RES:
        """Create a new entity."""
        raise NotImplementedError("Use create_channel instead")

    async def create_channel(self, request: Union[ChannelRequest, Dict]) -> ChannelResponse:
        """Create a new channel.

        Args:
            request: The channel creation request.

        Returns:
            The created channel response.
        """
        entity = self.dao.from_request(request)

        with self.dao.session() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)

        return self.dao.to_response(entity)

    async def update_channel(
        self, channel_id: str, request: Union[ChannelRequest, Dict]
    ) -> ChannelResponse:
        """Update an existing channel.

        Args:
            channel_id: The channel ID to update.
            request: The update request.

        Returns:
            The updated channel response.

        Raises:
            ValueError: If the channel does not exist.
        """
        with self.dao.session() as session:
            entity = session.query(ChannelEntity).filter(
                ChannelEntity.id == channel_id
            ).first()
            if not entity:
                raise ValueError(f"Channel not found: {channel_id}")

            entity = self.dao.update_entity_from_request(entity, request)
            session.commit()
            session.refresh(entity)

            return self.dao.to_response(entity)

    async def delete_channel(self, channel_id: str) -> bool:
        """Delete a channel.

        Args:
            channel_id: The channel ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self.dao.session() as session:
            result = session.query(ChannelEntity).filter(
                ChannelEntity.id == channel_id
            ).delete()
            session.commit()
            return result > 0

    async def get_channel(self, channel_id: str) -> Optional[ChannelResponse]:
        """Get a specific channel by ID.

        Args:
            channel_id: The channel ID.

        Returns:
            The channel response if found, None otherwise.
        """
        with self.dao.session() as session:
            entity = session.query(ChannelEntity).filter(
                ChannelEntity.id == channel_id
            ).first()
            if entity:
                return self.dao.to_response(entity)
            return None

    async def list_channels(self, include_disabled: bool = False) -> List[ChannelResponse]:
        """List all channels.

        Args:
            include_disabled: Whether to include disabled channels.

        Returns:
            List of channel responses.
        """
        with self.dao.session() as session:
            query = session.query(ChannelEntity)
            if not include_disabled:
                query = query.filter(ChannelEntity.enabled == 1)
            entities = query.all()
            return [self.dao.to_response(e) for e in entities]

    async def test_connection(self, channel_id: str) -> ChannelTestResponse:
        """Test the connection to a channel.

        This is a placeholder that returns success. The actual implementation
        should be provided by the channel handler in derisk-ext.

        Args:
            channel_id: The channel ID to test.

        Returns:
            The test result.
        """
        channel = await self.get_channel(channel_id)
        if not channel:
            return ChannelTestResponse(
                success=False,
                message=f"Channel not found: {channel_id}",
            )

        # Placeholder: actual implementation should be in derisk-ext
        # The channel handler should be invoked here to test the connection
        logger.info(f"Testing connection for channel {channel_id}")

        return ChannelTestResponse(
            success=True,
            message="Connection test successful (placeholder)",
            details={"channel_type": channel.channel_type},
        )

    async def enable_channel(self, channel_id: str) -> ChannelResponse:
        """Enable a channel.

        Args:
            channel_id: The channel ID to enable.

        Returns:
            The updated channel response.

        Raises:
            ValueError: If the channel does not exist.
        """
        return await self.update_channel(
            channel_id, {"enabled": True}
        )

    async def disable_channel(self, channel_id: str) -> ChannelResponse:
        """Disable a channel.

        Args:
            channel_id: The channel ID to disable.

        Returns:
            The updated channel response.

        Raises:
            ValueError: If the channel does not exist.
        """
        return await self.update_channel(
            channel_id, {"enabled": False}
        )

    async def update_channel_status(
        self,
        channel_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update channel connection status.

        Args:
            channel_id: The channel ID.
            status: The new status.
            error: Optional error message.
        """
        with self.dao.session() as session:
            entity = session.query(ChannelEntity).filter(
                ChannelEntity.id == channel_id
            ).first()
            if entity:
                entity.status = status
                if status == "connected":
                    entity.last_connected = datetime.now()
                if error:
                    entity.last_error = error
                entity.gmt_modified = datetime.now()
                session.commit()

    def get_enabled_channels(self) -> List[ChannelEntity]:
        """Get all enabled channels.

        Returns:
            List of enabled channel entities.
        """
        return self.dao.get_enabled_channels()