"""DingTalk channel handler implementation.

This module provides the channel handler implementation for DingTalk
using Stream mode for receiving messages.
"""

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from derisk.channel.base import (
    ChannelCapabilities,
    ChannelConfig,
    ChannelConnectionState,
    ChannelHandler,
    ChannelMessage,
    ChannelType,
    SendMessageResult,
)
from derisk.channel.schemas import DingTalkConfig

from .client import DingTalkClient
from .models import DingTalkEventType
from .sender import DingTalkSender

logger = logging.getLogger(__name__)


class DingTalkChannelHandler(ChannelHandler):
    """Channel handler for DingTalk platform.

    This handler implements the ChannelHandler interface for DingTalk,
    supporting:
    - Stream mode for receiving messages (no public URL needed)
    - Sending various message types
    - Message parsing and routing
    """

    @classmethod
    def get_default_capabilities(cls) -> ChannelCapabilities:
        """Get default capabilities for DingTalk channel type.

        Returns:
            ChannelCapabilities describing DingTalk's features.
        """
        return ChannelCapabilities(
            chat_types=["private", "group"],
            threads=False,
            media=["text", "image", "file", "voice", "link"],
            reactions=False,
            edit=False,
            reply=True,
        )

    def __init__(
        self,
        channel_id: str,
        config: ChannelConfig,
        platform_config: Optional[DingTalkConfig] = None,
        message_callback: Optional[Callable[[ChannelMessage], None]] = None,
    ):
        """Initialize the DingTalk channel handler.

        Args:
            channel_id: The unique channel identifier.
            config: Base channel configuration.
            platform_config: DingTalk-specific configuration.
            message_callback: Optional callback for received messages.
        """
        super().__init__(channel_id, config)
        self._platform_config = platform_config
        self._message_callback = message_callback
        self._client: Optional[DingTalkClient] = None
        self._sender: Optional[DingTalkSender] = None
        self._running = False

        if platform_config:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the DingTalk client."""
        if not self._platform_config:
            return

        self._client = DingTalkClient(
            config=self._platform_config,
            message_callback=self._on_message_received,
        )
        self._sender = DingTalkSender(self._client)
        logger.info(f"DingTalk client initialized for channel: {self._channel_id}")

    async def start(self) -> None:
        """Start the channel handler.

        This establishes the Stream mode connection and starts listening
        for incoming messages.
        """
        if self._running:
            logger.warning("Handler is already running")
            return

        if not self._client:
            logger.error("Client not initialized")
            self._connection_state = ChannelConnectionState.ERROR
            return

        self._connection_state = ChannelConnectionState.CONNECTING
        self._running = True

        try:
            await self._client.start()
            self._connection_state = ChannelConnectionState.CONNECTED
            logger.info(f"DingTalk handler started for channel: {self._channel_id}")
        except Exception as e:
            logger.error(f"Failed to start DingTalk handler: {e}")
            self._connection_state = ChannelConnectionState.ERROR
            self._running = False

    async def stop(self) -> None:
        """Stop the channel handler.

        This closes the Stream connection and stops listening for messages.
        """
        if not self._running:
            return

        self._running = False

        if self._client:
            await self._client.stop()

        self._connection_state = ChannelConnectionState.DISCONNECTED
        logger.info(f"DingTalk handler stopped for channel: {self._channel_id}")

    async def send_message(
        self,
        receiver_id: str,
        content: str,
        content_type: str = "text",
        **kwargs,
    ) -> SendMessageResult:
        """Send a message to a receiver.

        Args:
            receiver_id: The receiver ID (user or conversation).
            content: The message content.
            content_type: Content type (text, markdown, etc.).
            **kwargs: Additional parameters.

        Returns:
            SendMessageResult indicating success or failure.
        """
        if not self._sender:
            return SendMessageResult(
                success=False,
                error="Sender not initialized",
            )

        is_group = kwargs.get("is_group", False)
        conversation_id = kwargs.get("conversation_id")
        mentions = kwargs.get("mentions", [])

        try:
            if content_type == "markdown":
                title = kwargs.get("title", "")
                return await self._sender.send_markdown(
                    user_id=receiver_id,
                    title=title,
                    markdown_content=content,
                    is_group=is_group,
                    conversation_id=conversation_id,
                )
            elif content_type == "actionCard":
                btns = kwargs.get("btns", [])
                title = kwargs.get("title", "")
                return await self._sender.send_action_card(
                    user_id=receiver_id,
                    title=title,
                    text=content,
                    btns=btns,
                    is_group=is_group,
                    conversation_id=conversation_id,
                )
            elif mentions:
                return await self._sender.send_text_with_mentions(
                    user_id=receiver_id,
                    text=content,
                    mentions=mentions,
                    is_group=is_group,
                    conversation_id=conversation_id,
                )
            else:
                return await self._sender.send_text(
                    user_id=receiver_id,
                    text=content,
                    is_group=is_group,
                    conversation_id=conversation_id or receiver_id,
                )

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return SendMessageResult(
                success=False,
                error=str(e),
            )

    def get_connection_url(self) -> Optional[str]:
        """Get the webhook URL.

        Returns None since DingTalk uses Stream mode, not webhooks.
        """
        return None

    async def process_message(
        self,
        channel_id: str,
        message: ChannelMessage,
    ) -> Optional[str]:
        """Process an incoming channel message.

        Args:
            channel_id: The channel configuration ID.
            message: The incoming message.

        Returns:
            Optional response message to send back.
        """
        if self._message_callback:
            try:
                await asyncio.to_thread(self._message_callback, message)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

        return None

    def validate_signature(
        self,
        channel_id: str,
        signature: str,
        timestamp: str,
        nonce: str,
        body: bytes,
    ) -> bool:
        """Validate the webhook signature.

        This is not needed for Stream mode but is kept for compatibility.

        Args:
            channel_id: The channel configuration ID.
            signature: The signature from the request header.
            timestamp: The timestamp from the request.
            nonce: The nonce from the request.
            body: The raw request body bytes.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not self._platform_config:
            return True

        token = self._platform_config.token

        if not token:
            return True

        try:
            string_to_sign = "".join(sorted([timestamp, nonce, token]))
            expected_signature = hashlib.sha256(string_to_sign.encode()).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Error validating signature: {e}")
            return False

    def get_capabilities(self) -> ChannelCapabilities:
        """Get DingTalk channel capabilities.

        Returns:
            ChannelCapabilities describing DingTalk's features.
        """
        return self.get_default_capabilities()

    async def test_connection(self, channel_id: str) -> bool:
        """Test the connection to DingTalk.

        Args:
            channel_id: The channel configuration ID.

        Returns:
            True if connection is successful, False otherwise.
        """
        if not self._client:
            return False

        try:
            bot_info = await self._client.get_bot_info()
            return bot_info is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def _on_message_received(self, event_dict: Dict[str, Any]) -> None:
        """Handle received Stream event.

        Args:
            event_dict: The parsed event dictionary from Stream mode.
        """
        try:
            event_type = event_dict.get("event_type")

            if event_type == DingTalkEventType.CHATBOT_MESSAGE.value:
                channel_message = self._parse_chatbot_message_event(event_dict)
                if channel_message and self._message_callback:
                    try:
                        self._message_callback(channel_message)
                    except Exception as e:
                        logger.error(f"Error in message callback: {e}")
            else:
                logger.warning("Received unknown event type: %s", event_type)

        except Exception as e:
            logger.error(f"Error processing received event: {e}")

    def _parse_chatbot_message_event(
        self, event_dict: Dict[str, Any]
    ) -> Optional[ChannelMessage]:
        """Parse chatbot_message event from ChatbotHandler.

        Args:
            event_dict: The chatbot_message event dictionary.

        Returns:
            ChannelMessage or None if parsing fails.
        """
        try:
            sender_id = event_dict.get("sender_id", "")
            sender_nick = event_dict.get("sender_nick", "")
            sender_staff_id = event_dict.get("sender_staff_id", "")

            message_id = event_dict.get("message_id", "")
            conversation_id = event_dict.get("conversation_id", "")
            conversation_type = event_dict.get("conversation_type", "private")
            is_group = conversation_type == "group"

            text_content = event_dict.get("text", "")

            timestamp = None
            create_at = event_dict.get("create_at")
            if create_at:
                try:
                    timestamp = datetime.fromtimestamp(int(create_at) / 1000)
                except (ValueError, TypeError):
                    pass

            mentions = None
            at_users = event_dict.get("at_users", [])
            if at_users:
                mentions = [
                    user.get("dingtalkId", user.get("staffId", ""))
                    for user in at_users
                    if user.get("dingtalkId") or user.get("staffId")
                ]

            return ChannelMessage(
                channel_type=ChannelType.DINGTALK,
                message_id=message_id,
                conversation_id=conversation_id,
                sender={
                    "user_id": sender_staff_id or sender_id,
                    "name": sender_nick,
                    "extra": {
                        "sender_id": sender_id,
                        "sender_staff_id": sender_staff_id,
                    },
                },
                content=text_content,
                content_type=event_dict.get("message_type", "text"),
                timestamp=timestamp,
                is_group=is_group,
                mentions=mentions,
                extra={
                    "raw_event": event_dict,
                    "robot_code": event_dict.get("robot_code"),
                    "session_webhook": event_dict.get("session_webhook"),
                    "is_in_at_list": event_dict.get("is_in_at_list"),
                },
            )

        except Exception as e:
            logger.error(f"Error parsing chatbot_message event: {e}")
            return None

    def set_message_callback(self, callback: Callable[[ChannelMessage], None]) -> None:
        """Set the message callback.

        Args:
            callback: The callback function for received messages.
        """
        self._message_callback = callback

    @property
    def client(self) -> Optional[DingTalkClient]:
        """Get the DingTalk client."""
        return self._client

    @property
    def sender(self) -> Optional[DingTalkSender]:
        """Get the DingTalk sender."""
        return self._sender