"""Channel handler registry for managing channel handlers.

This module provides a registry for channel handlers that can be used to
manage and retrieve handlers by channel type and ID.
"""

import logging
from typing import Callable, Dict, Optional, Type

from derisk.channel.base import (
    ChannelCapabilities,
    ChannelConfig,
    ChannelHandler,
    ChannelType,
)

logger = logging.getLogger(__name__)


class ChannelHandlerRegistry:
    """Registry for channel handlers.

    This registry manages channel handlers by their type and ID.
    It supports:
    - Registering handler classes by channel type
    - Creating handler instances for specific channels
    - Retrieving active handlers by channel ID
    """

    _instance: Optional["ChannelHandlerRegistry"] = None

    def __new__(cls) -> "ChannelHandlerRegistry":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the registry."""
        if self._initialized:
            return
        self._initialized = True
        self._handler_classes: Dict[ChannelType, Type[ChannelHandler]] = {}
        self._active_handlers: Dict[str, ChannelHandler] = {}
        self._factories: Dict[
            ChannelType, Callable[[str, ChannelConfig], ChannelHandler]
        ] = {}
        logger.info("ChannelHandlerRegistry initialized")

    @classmethod
    def get_instance(cls) -> "ChannelHandlerRegistry":
        """Get the singleton registry instance."""
        return cls()

    def register_handler_class(
        self,
        channel_type: ChannelType,
        handler_class: Type[ChannelHandler],
    ) -> None:
        """Register a handler class for a channel type.

        Args:
            channel_type: The channel type.
            handler_class: The handler class to register.
        """
        self._handler_classes[channel_type] = handler_class
        logger.info(f"Registered handler class for channel type: {channel_type}")

    def register_factory(
        self,
        channel_type: ChannelType,
        factory: Callable[[str, ChannelConfig], ChannelHandler],
    ) -> None:
        """Register a factory function for creating handlers.

        Args:
            channel_type: The channel type.
            factory: Factory function that creates handler instances.
        """
        self._factories[channel_type] = factory
        logger.info(f"Registered factory for channel type: {channel_type}")

    def create_handler(
        self,
        channel_id: str,
        channel_type: ChannelType,
        config: ChannelConfig,
    ) -> Optional[ChannelHandler]:
        """Create a handler instance for a channel.

        Args:
            channel_id: The unique channel identifier.
            channel_type: The channel type.
            config: The channel configuration.

        Returns:
            The created handler instance, or None if creation failed.
        """
        if channel_id in self._active_handlers:
            logger.warning(f"Handler already exists for channel: {channel_id}")
            return self._active_handlers[channel_id]

        handler: Optional[ChannelHandler] = None

        if channel_type in self._factories:
            try:
                handler = self._factories[channel_type](channel_id, config)
            except Exception as e:
                logger.error(f"Failed to create handler using factory: {e}")
                return None
        elif channel_type in self._handler_classes:
            handler_class = self._handler_classes[channel_type]
            try:
                handler = handler_class(channel_id=channel_id, config=config)
            except Exception as e:
                logger.error(f"Failed to create handler instance: {e}")
                return None
        else:
            logger.error(f"No handler registered for channel type: {channel_type}")
            return None

        if handler:
            self._active_handlers[channel_id] = handler
            logger.info(f"Created handler for channel: {channel_id}")

        return handler

    def get_handler(self, channel_id: str) -> Optional[ChannelHandler]:
        """Get an active handler by channel ID.

        Args:
            channel_id: The channel identifier.

        Returns:
            The handler instance, or None if not found.
        """
        return self._active_handlers.get(channel_id)

    def remove_handler(self, channel_id: str) -> bool:
        """Remove a handler from the registry.

        Args:
            channel_id: The channel identifier.

        Returns:
            True if the handler was removed, False if not found.
        """
        if channel_id in self._active_handlers:
            del self._active_handlers[channel_id]
            logger.info(f"Removed handler for channel: {channel_id}")
            return True
        return False

    async def stop_handler(self, channel_id: str) -> bool:
        """Stop and remove a handler.

        Args:
            channel_id: The channel identifier.

        Returns:
            True if the handler was stopped and removed, False if not found.
        """
        handler = self.get_handler(channel_id)
        if handler:
            try:
                await handler.stop()
            except Exception as e:
                logger.error(f"Error stopping handler: {e}")
            self.remove_handler(channel_id)
            return True
        return False

    def get_capabilities(
        self, channel_type: ChannelType
    ) -> Optional[ChannelCapabilities]:
        """Get capabilities for a channel type.

        Args:
            channel_type: The channel type.

        Returns:
            The capabilities, or None if no handler is registered.
        """
        if channel_type in self._handler_classes:
            handler_class = self._handler_classes[channel_type]
            # Use the class method to get default capabilities without instantiation
            try:
                return handler_class.get_default_capabilities()
            except Exception as e:
                logger.warning(f"Failed to get default capabilities: {e}")
        return None

    def get_registered_types(self) -> list:
        """Get list of registered channel types.

        Returns:
            List of registered channel types.
        """
        return list(
            set(list(self._handler_classes.keys()) + list(self._factories.keys()))
        )
