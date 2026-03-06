"""Channel message router for routing messages to agents.

This module provides a message router that routes incoming channel messages
to appropriate agents and handles agent responses.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from derisk.channel.base import (
    ChannelHandler,
    ChannelMessage,
    SendMessageResult,
)

logger = logging.getLogger(__name__)


class MessageHandler(ABC):
    """Abstract base class for message handlers.

    Message handlers are responsible for processing channel messages
    and generating responses.
    """

    @abstractmethod
    async def handle_message(
        self,
        message: ChannelMessage,
        channel_handler: ChannelHandler,
        channel_id: Optional[str] = None,
    ) -> Optional[str]:
        """Handle an incoming channel message.

        Args:
            message: The incoming message.
            channel_handler: The channel handler for sending responses.
            channel_id: The channel configuration ID.

        Returns:
            Optional response content to send back.
        """
        pass


class ChannelMessageRouter:
    """Router for channel messages.

    This router routes incoming channel messages to appropriate handlers
    and manages the message processing pipeline.
    """

    def __init__(self):
        """Initialize the router."""
        self._handlers: Dict[str, MessageHandler] = {}
        self._default_handler: Optional[MessageHandler] = None
        self._middleware: List[Callable] = []
        self._running = False

    def register_handler(
        self,
        channel_id: str,
        handler: MessageHandler,
    ) -> None:
        """Register a message handler for a specific channel.

        Args:
            channel_id: The channel identifier.
            handler: The message handler.
        """
        self._handlers[channel_id] = handler
        logger.info(f"Registered message handler for channel: {channel_id}")

    def unregister_handler(self, channel_id: str) -> None:
        """Unregister a message handler.

        Args:
            channel_id: The channel identifier.
        """
        if channel_id in self._handlers:
            del self._handlers[channel_id]
            logger.info(f"Unregistered message handler for channel: {channel_id}")

    def set_default_handler(self, handler: MessageHandler) -> None:
        """Set the default message handler.
·
        The default handler is used when no specific handler is registered
        for a channel.

        Args:
            handler: The default message handler.
        """
        self._default_handler = handler
        logger.info("Set default message handler")

    def add_middleware(self, middleware: Callable) -> None:
        """Add middleware to the processing pipeline.

        Middleware functions are called before the message handler.
        They can modify the message or perform additional processing.

        Args:
            middleware: Middleware function that takes a ChannelMessage
                       and returns a (possibly modified) ChannelMessage.
        """
        self._middleware.append(middleware)
        logger.info("Added middleware to message router")

    async def route_message(
        self,
        channel_id: str,
        message: ChannelMessage,
        channel_handler: ChannelHandler,
    ) -> Optional[SendMessageResult]:
        """Route a message to the appropriate handler.

        Args:
            channel_id: The channel identifier.
            message: The incoming message.
            channel_handler: The channel handler for sending responses.

        Returns:
            SendMessageResult if a response was sent, None otherwise.
        """
        processed_message = message

        for middleware in self._middleware:
            try:
                result = await middleware(processed_message)
                if result is not None:
                    processed_message = result
            except Exception as e:
                logger.error(f"Middleware error: {e}")

        handler = self._handlers.get(channel_id, self._default_handler)

        if handler is None:
            logger.warning(f"No handler found for channel: {channel_id}")
            return None

        try:
            response = await handler.handle_message(
                processed_message, channel_handler, channel_id=channel_id
            )

            if response:
                receiver_id = (
                    message.conversation_id
                    if message.is_group
                    else message.sender.user_id
                )

                if receiver_id:
                    reply_to = message.message_id
                    return await channel_handler.send_message(
                        receiver_id=receiver_id,
                        content=response,
                        reply_to=reply_to,
                    )

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return None

        return None

    async def start(self) -> None:
        """Start the router."""
        self._running = True
        logger.info("Channel message router started")

    async def stop(self) -> None:
        """Stop the router."""
        self._running = False
        logger.info("Channel message router stopped")

    @property
    def is_running(self) -> bool:
        """Check if the router is running."""
        return self._running


class AgentMessageHandler(MessageHandler):
    """Message handler that integrates with the agent system.

    This handler creates a conversation context from channel messages
    and delegates to the agent system for processing.
    """

    def __init__(
        self,
        agent_app_code: str = "main-orchestrator",
        get_agent_response: Optional[Callable] = None,
    ):
        """Initialize the agent message handler.

        Args:
            agent_app_code: The agent app code to use.
            get_agent_response: Optional function to get agent responses.
                               If None, a default implementation will be used.
        """
        self._agent_app_code = agent_app_code
        self._get_agent_response = get_agent_response
        self._conversation_histories: Dict[str, List] = {}

    async def handle_message(
        self,
        message: ChannelMessage,
        channel_handler: ChannelHandler,
        channel_id: Optional[str] = None,
    ) -> Optional[str]:
        """Handle an incoming message by routing to an agent.

        Args:
            message: The incoming message.
            channel_handler: The channel handler for sending responses.
            channel_id: The channel configuration ID.

        Returns:
            The agent's response content.
        """
        conversation_key = message.conversation_id or message.sender.user_id

        if conversation_key not in self._conversation_histories:
            self._conversation_histories[conversation_key] = []

        history = self._conversation_histories[conversation_key]

        history.append(
            {
                "role": "user",
                "content": message.content,
            }
        )

        if len(history) > 20:
            history = history[-20:]
            self._conversation_histories[conversation_key] = history

        # Build channel context for passing to agent
        channel_context = {
            "channel_id": channel_id,
            "channel_type": message.channel_type.value if message.channel_type else None,
            "receiver_id": message.conversation_id
            if message.is_group
            else message.sender.user_id,
            "is_group": message.is_group,
        }

        if self._get_agent_response:
            try:
                response = await self._get_agent_response(
                    message=message,
                    history=history,
                    agent_app_code=self._agent_app_code,
                    channel_context=channel_context,
                )
                return response
            except Exception as e:
                logger.error(f"Error getting agent response: {e}")
                return f"Error processing message: {str(e)}"
        else:
            return f"Received your message: {message.content}"

    def clear_conversation(self, conversation_key: str) -> None:
        """Clear conversation history.

        Args:
            conversation_key: The conversation key.
        """
        if conversation_key in self._conversation_histories:
            del self._conversation_histories[conversation_key]

    def clear_all_conversations(self) -> None:
        """Clear all conversation histories."""
        self._conversation_histories.clear()
