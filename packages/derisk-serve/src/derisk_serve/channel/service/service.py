"""Channel service implementation.

This module provides the main service for channel management.
"""
import base64
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

from derisk.channel import ChannelConfig, ChannelType
from derisk.channel.schemas import DingTalkConfig, FeishuConfig
from derisk.component import SystemApp
from derisk.storage.metadata._base_dao import REQ, RES
from derisk_serve.core import BaseService

from ..api.schemas import ChannelRequest, ChannelResponse, ChannelTestResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..connection import ChannelConnectionManager
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
        self._config = config
        self._dao = dao
        self._connection_manager: Optional[ChannelConnectionManager] = None
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service.

        Args:
            system_app: The system application instance.
        """
        super().init_app(system_app)
        self._dao = self._dao or ChannelDao(self._config)
        self._connection_manager = ChannelConnectionManager()

        # 设置默认消息处理器，带Agent集成
        from derisk.channel.router import AgentMessageHandler

        default_handler = AgentMessageHandler(
            agent_app_code="main-orchestrator",
            get_agent_response=self._get_agent_response_with_channel_context,
        )
        self._connection_manager.set_default_message_handler(default_handler)
        logger.info("Default message handler initialized with agent integration")

    async def _get_agent_response_with_channel_context(
        self,
        message,
        history,
        agent_app_code,
        channel_context=None,
    ):
        """Get agent response with channel context for cron message delivery.

        Args:
            message: The incoming channel message.
            history: Conversation history.
            agent_app_code: The agent app code.
            channel_context: Channel context including channel_id, receiver_id, etc.

        Returns:
            The agent's response content.
        """
        import uuid
        from derisk_serve.agent.agents.controller import multi_agents

        # Generate a conversation session ID based on the channel message
        channel_conv_id = message.conversation_id or message.sender.user_id
        conv_session_id = f"channel_{hashlib.md5(channel_conv_id.encode()).hexdigest()}"

        try:
            # Build ext_info with channel context for cron message delivery
            ext_info = {}
            if channel_context:
                ext_info["channel"] = channel_context

            # Create a callback to ensure final_report is populated
            # This is needed for channel message delivery to work correctly
            async def channel_callback(
                conv_session_id: str,
                agent_conv_id: str,
                final_message: str,
                final_report: str,
                err_msg: Optional[str],
                first_chunk_ms: Optional[int],
                post_action_reports: Optional[list] = None,
            ):
                """Callback to enable final_report population for channel delivery.

                The final_report is only populated when chat_call_back is callable,
                so we need to provide this callback even if we don't need to do
                anything special with the results.
                """
                if err_msg:
                    logger.error(f"Channel agent execution error: {err_msg}")
                else:
                    logger.info(f"Channel agent execution completed for session {conv_session_id}")

            # Call the agent chat with callback
            result, agent_conv_id = await multi_agents.app_chat_v3(
                conv_uid=conv_session_id,
                gpts_name=agent_app_code,
                user_query=message.content,
                stream=False,  # Non-streaming for channel messages
                background_tasks=None,
                chat_call_back=channel_callback,  # Add callback for final_report
                **ext_info,
            )

            return result or "处理完成"
        except Exception as e:
            logger.error(f"Error getting agent response: {e}")
            raise

    @property
    def dao(self) -> ChannelDao:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._config

    @property
    def connection_manager(self) -> Optional[ChannelConnectionManager]:
        """Returns the connection manager."""
        return self._connection_manager

    def create(self, request: REQ) -> RES:
        """Create a new entity."""
        raise NotImplementedError("Use create_channel instead")

    async def create_channel(
        self, request: Union[ChannelRequest, Dict]
    ) -> ChannelResponse:
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
            entity = (
                session.query(ChannelEntity)
                .filter(ChannelEntity.id == channel_id)
                .first()
            )
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
            result = (
                session.query(ChannelEntity)
                .filter(ChannelEntity.id == channel_id)
                .delete()
            )
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
            entity = (
                session.query(ChannelEntity)
                .filter(ChannelEntity.id == channel_id)
                .first()
            )
            if entity:
                return self.dao.to_response(entity)
            return None

    async def list_channels(
        self, include_disabled: bool = False
    ) -> List[ChannelResponse]:
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

        try:
            channel_type = ChannelType(channel.channel_type)
        except ValueError:
            return ChannelTestResponse(
                success=False,
                message=f"Invalid channel type: {channel.channel_type}",
            )

        config = ChannelConfig(
            name=channel.name,
            enabled=channel.enabled,
            platform_config=channel.config,
        )

        handler = self._connection_manager._registry.create_handler(
            channel_id, channel_type, config
        )

        if not handler:
            return ChannelTestResponse(
                success=False,
                message=f"Failed to create handler for channel type: {channel.channel_type}",
            )

        try:
            success = await handler.test_connection(channel_id)
            self._connection_manager._registry.remove_handler(channel_id)

            if success:
                return ChannelTestResponse(
                    success=True,
                    message="Connection test successful",
                    details={"channel_type": channel.channel_type},
                )
            else:
                return ChannelTestResponse(
                    success=False,
                    message="Connection test failed",
                    details={"channel_type": channel.channel_type},
                )
        except Exception as e:
            logger.error(f"Error testing connection: {e}")
            self._connection_manager._registry.remove_handler(channel_id)
            return ChannelTestResponse(
                success=False,
                message=f"Connection test error: {str(e)}",
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
        return await self.update_channel(channel_id, {"enabled": True})

    async def disable_channel(self, channel_id: str) -> ChannelResponse:
        """Disable a channel.

        Args:
            channel_id: The channel ID to disable.

        Returns:
            The updated channel response.

        Raises:
            ValueError: If the channel does not exist.
        """
        return await self.update_channel(channel_id, {"enabled": False})

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
            entity = (
                session.query(ChannelEntity)
                .filter(ChannelEntity.id == channel_id)
                .first()
            )
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

    async def start_channel(self, channel_id: str) -> bool:
        """Start a channel by ID.

        Args:
            channel_id: The channel ID to start.

        Returns:
            True if started successfully, False otherwise.
        """
        channel = await self.get_channel(channel_id)
        if not channel:
            logger.error(f"Channel not found: {channel_id}")
            return False

        if not channel.enabled:
            logger.warning(f"Channel {channel_id} is disabled")
            return False

        if not self._connection_manager:
            logger.error("Connection manager not initialized")
            return False

        try:
            channel_type = ChannelType(channel.channel_type)
        except ValueError:
            logger.error(f"Invalid channel type: {channel.channel_type}")
            return False

        config = ChannelConfig(
            name=channel.name,
            enabled=channel.enabled,
            platform_config=channel.config,
        )

        success = await self._connection_manager.start_channel(
            channel_id, channel_type, config
        )

        if success:
            await self.update_channel_status(channel_id, "connected")
        else:
            await self.update_channel_status(channel_id, "error", "Failed to start")

        return success

    async def stop_channel(self, channel_id: str) -> bool:
        """Stop a channel by ID.

        Args:
            channel_id: The channel ID to stop.

        Returns:
            True if stopped successfully, False otherwise.
        """
        if not self._connection_manager:
            logger.error("Connection manager not initialized")
            return False

        success = await self._connection_manager.stop_channel(channel_id)

        if success:
            await self.update_channel_status(channel_id, "disconnected")

        return success

    async def start_all_channels(self) -> Dict[str, bool]:
        """Start all enabled channels.

        Returns:
            Dictionary mapping channel IDs to success status.
        """
        if not self._connection_manager:
            logger.error("Connection manager not initialized")
            return {}

        enabled_channels = self.get_enabled_channels()
        channels_data = [
            {
                "id": ch.id,
                "name": ch.name,
                "channel_type": ch.channel_type,
                "config": ch.config,
                "enabled": bool(ch.enabled),
            }
            for ch in enabled_channels
        ]

        results = await self._connection_manager.start_all_channels(channels_data)

        for channel_id, success in results.items():
            if success:
                await self.update_channel_status(channel_id, "connected")
            else:
                await self.update_channel_status(channel_id, "error", "Failed to start")

        return results

    async def stop_all_channels(self) -> Dict[str, bool]:
        """Stop all running channels.

        Returns:
            Dictionary mapping channel IDs to success status.
        """
        if not self._connection_manager:
            logger.error("Connection manager not initialized")
            return {}

        results = await self._connection_manager.stop_all_channels()

        for channel_id in results:
            await self.update_channel_status(channel_id, "disconnected")

        return results

    def get_running_channels(self) -> List[str]:
        """Get list of running channel IDs.

        Returns:
            List of channel IDs that are currently running.
        """
        if not self._connection_manager:
            return []
        return self._connection_manager.get_running_channels()

    async def start_connection_manager(self) -> None:
        """Start the connection manager."""
        if self._connection_manager:
            await self._connection_manager.start()

    async def stop_connection_manager(self) -> None:
        """Stop the connection manager."""
        if self._connection_manager:
            await self._connection_manager.stop()
