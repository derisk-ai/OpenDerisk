"""Channel connection manager.

This module manages active channel connections, including:
- Starting/stopping channels
- Health monitoring
- Reconnection handling
- Message routing
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from derisk.channel import (
    ChannelConfig,
    ChannelHandler,
    ChannelHandlerRegistry,
    ChannelMessage,
    ChannelMessageRouter,
    ChannelType,
)
from derisk.channel.schemas import DingTalkConfig, FeishuConfig

logger = logging.getLogger(__name__)


class ChannelConnectionManager:
    """Manager for active channel connections.

    This manager handles:
    - Creating and managing channel handlers
    - Starting and stopping channels
    - Health monitoring
    - Message routing to agents
    """

    def __init__(self, message_router: Optional[ChannelMessageRouter] = None):
        """Initialize the connection manager.

        Args:
            message_router: Optional message router for routing messages to agents.
        """
        self._registry = ChannelHandlerRegistry.get_instance()
        self._message_router = message_router or ChannelMessageRouter()
        self._running_handlers: Set[str] = set()
        self._handler_tasks: Dict[str, asyncio.Task] = {}
        self._started = False

        self._register_channel_handlers()

    def _register_channel_handlers(self) -> None:
        """Register channel handler factories."""
        from derisk_ext.channels.dingtalk import DingTalkChannelHandler
        from derisk_ext.channels.feishu import FeishuChannelHandler

        def create_feishu_handler(
            channel_id: str, config: ChannelConfig
        ) -> ChannelHandler:
            platform_config = None
            if config.platform_config:
                platform_config = FeishuConfig(**config.platform_config)

            return FeishuChannelHandler(
                channel_id=channel_id,
                config=config,
                platform_config=platform_config,
                message_callback=self._create_message_callback(channel_id),
            )

        def create_dingtalk_handler(
            channel_id: str, config: ChannelConfig
        ) -> ChannelHandler:
            platform_config = None
            if config.platform_config:
                platform_config = DingTalkConfig(**config.platform_config)

            return DingTalkChannelHandler(
                channel_id=channel_id,
                config=config,
                platform_config=platform_config,
                message_callback=self._create_message_callback(channel_id),
            )

        self._registry.register_factory(ChannelType.FEISHU, create_feishu_handler)
        self._registry.register_factory(ChannelType.DINGTALK, create_dingtalk_handler)

        logger.info("Channel handlers registered")

    def _create_message_callback(self, channel_id: str):
        """Create a message callback for a channel.

        Args:
            channel_id: The channel ID.

        Returns:
            A callback function for handling messages.
        """
        # Capture the current event loop (main event loop)
        # This is called from an async context, so get_running_loop() works here
        loop = asyncio.get_running_loop()

        def callback(message: ChannelMessage) -> None:
            # Use run_coroutine_threadsafe to submit the coroutine to the main event loop
            # This is necessary because the callback may be called from a thread pool
            # thread (e.g., via asyncio.to_thread()), which doesn't have an event loop
            asyncio.run_coroutine_threadsafe(
                self._handle_message(channel_id, message),
                loop
            )

        return callback

    async def _handle_message(self, channel_id: str, message: ChannelMessage) -> None:
        """Handle an incoming message.

        Args:
            channel_id: The channel ID.
            message: The incoming message.
        """
        handler = self._registry.get_handler(channel_id)
        if handler and self._message_router:
            await self._message_router.route_message(channel_id, message, handler)

    def register_message_handler(self, channel_id: str, message_handler) -> None:
        """Register a message handler for a specific channel.

        Args:
            channel_id: The channel ID.
            message_handler: The message handler.
        """
        self._message_router.register_handler(channel_id, message_handler)

    def set_default_message_handler(self, message_handler) -> None:
        """Set the default message handler.

        Args:
            message_handler: The default message handler.
        """
        self._message_router.set_default_handler(message_handler)

    async def start_channel(
        self,
        channel_id: str,
        channel_type: ChannelType,
        config: ChannelConfig,
    ) -> bool:
        """Start a channel.

        Args:
            channel_id: The channel ID.
            channel_type: The channel type.
            config: The channel configuration.

        Returns:
            True if started successfully, False otherwise.
        """
        if channel_id in self._running_handlers:
            logger.warning(f"Channel {channel_id} is already running")
            return True

        handler = self._registry.create_handler(channel_id, channel_type, config)
        if not handler:
            logger.error(f"Failed to create handler for channel {channel_id}")
            return False

        try:
            await handler.start()
            self._running_handlers.add(channel_id)
            logger.info(f"Started channel: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start channel {channel_id}: {e}")
            self._registry.remove_handler(channel_id)
            return False

    async def stop_channel(self, channel_id: str) -> bool:
        """Stop a channel.

        Args:
            channel_id: The channel ID.

        Returns:
            True if stopped successfully, False otherwise.
        """
        if channel_id not in self._running_handlers:
            logger.warning(f"Channel {channel_id} is not running")
            return False

        try:
            await self._registry.stop_handler(channel_id)
            self._running_handlers.discard(channel_id)
            logger.info(f"Stopped channel: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop channel {channel_id}: {e}")
            return False

    async def start_all_channels(self, channels: List[dict]) -> Dict[str, bool]:
        """Start all enabled channels.

        Args:
            channels: List of channel configurations from database.

        Returns:
            Dictionary mapping channel IDs to success status.
        """
        results = {}
        for channel_data in channels:
            channel_id = channel_data.get("id")
            channel_type_str = channel_data.get("channel_type")
            config_dict = channel_data.get("config", {})
            enabled = channel_data.get("enabled", False)

            if not enabled:
                results[channel_id] = False
                continue

            try:
                channel_type = ChannelType(channel_type_str)
            except ValueError:
                logger.error(f"Unknown channel type: {channel_type_str}")
                results[channel_id] = False
                continue

            config = ChannelConfig(
                name=channel_data.get("name", ""),
                enabled=enabled,
                platform_config=config_dict,
            )

            results[channel_id] = await self.start_channel(
                channel_id, channel_type, config
            )

        return results

    async def stop_all_channels(self) -> Dict[str, bool]:
        """Stop all running channels.

        Returns:
            Dictionary mapping channel IDs to success status.
        """
        results = {}
        for channel_id in list(self._running_handlers):
            results[channel_id] = await self.stop_channel(channel_id)
        return results

    def get_running_channels(self) -> List[str]:
        """Get list of running channel IDs.

        Returns:
            List of channel IDs that are currently running.
        """
        return list(self._running_handlers)

    def get_handler(self, channel_id: str) -> Optional[ChannelHandler]:
        """Get a handler by channel ID.

        Args:
            channel_id: The channel ID.

        Returns:
            The handler instance, or None if not found.
        """
        return self._registry.get_handler(channel_id)

    async def start(self) -> None:
        """Start the connection manager."""
        if self._started:
            return

        self._started = True
        await self._message_router.start()
        logger.info("Channel connection manager started")

    async def stop(self) -> None:
        """Stop the connection manager."""
        if not self._started:
            return

        await self.stop_all_channels()
        await self._message_router.stop()
        self._started = False
        logger.info("Channel connection manager stopped")

    @property
    def is_running(self) -> bool:
        """Check if the manager is running."""
        return self._started
