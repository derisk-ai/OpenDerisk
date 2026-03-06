"""Feishu channel handler implementation.

This module provides the channel handler implementation for Feishu/Lark
using WebSocket mode for receiving messages.
"""

import asyncio
import hashlib
import hmac
import json
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
from derisk.channel.schemas import FeishuConfig

from .client import FeishuClient
from .models import (
    FeishuEvent,
    FeishuEventType,
    FeishuMessageContentType,
    FeishuMessageEvent,
    FeishuUrlVerifyEvent,
)
from .sender import FeishuSender

logger = logging.getLogger(__name__)


class FeishuChannelHandler(ChannelHandler):
    """Channel handler for Feishu/Lark platform.

    This handler implements the ChannelHandler interface for Feishu,
    supporting:
    - WebSocket mode for receiving messages (no public URL needed)
    - Sending various message types
    - Message parsing and routing
    """

    @classmethod
    def get_default_capabilities(cls) -> ChannelCapabilities:
        """Get default capabilities for Feishu channel type.

        Returns:
            ChannelCapabilities describing Feishu's features.
        """
        return ChannelCapabilities(
            chat_types=["private", "group"],
            threads=True,
            media=["text", "image", "file", "audio", "video"],
            reactions=True,
            edit=True,
            reply=True,
        )

    def __init__(
        self,
        channel_id: str,
        config: ChannelConfig,
        platform_config: Optional[FeishuConfig] = None,
        message_callback: Optional[Callable[[ChannelMessage], None]] = None,
    ):
        """Initialize the Feishu channel handler.

        Args:
            channel_id: The unique channel identifier.
            config: Base channel configuration.
            platform_config: Feishu-specific configuration.
            message_callback: Optional callback for received messages.
        """
        super().__init__(channel_id, config)
        self._platform_config = platform_config
        self._message_callback = message_callback
        self._client: Optional[FeishuClient] = None
        self._sender: Optional[FeishuSender] = None
        self._running = False

        if platform_config:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Feishu client."""
        if not self._platform_config:
            return

        self._client = FeishuClient(
            config=self._platform_config,
            message_callback=self._on_message_received,
        )
        self._sender = FeishuSender(self._client)
        logger.info(f"Feishu client initialized for channel: {self._channel_id}")

    async def start(self) -> None:
        """Start the channel handler.

        This establishes the WebSocket connection and starts listening
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
            logger.info(f"Feishu handler started for channel: {self._channel_id}")
        except Exception as e:
            logger.error(f"Failed to start Feishu handler: {e}")
            self._connection_state = ChannelConnectionState.ERROR
            self._running = False

    async def stop(self) -> None:
        """Stop the channel handler.

        This closes the WebSocket connection and stops listening for messages.
        """
        if not self._running:
            return

        self._running = False

        if self._client:
            await self._client.stop()

        self._connection_state = ChannelConnectionState.DISCONNECTED
        logger.info(f"Feishu handler stopped for channel: {self._channel_id}")

    async def send_message(
        self,
        receiver_id: str,
        content: str,
        content_type: str = "text",
        **kwargs,
    ) -> SendMessageResult:
        """Send a message to a receiver.

        Args:
            receiver_id: The receiver ID (user or chat).
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

        reply_to = kwargs.get("reply_to")
        mentions = kwargs.get("mentions", [])

        try:
            if content_type == "markdown":
                return await self._sender.send_markdown(
                    receive_id=receiver_id,
                    title="",
                    markdown_content=content,
                )
            elif content_type == "interactive":
                return await self._sender.send_interactive_card(
                    receive_id=receiver_id,
                    title="",
                    content=content,
                )
            elif mentions:
                return await self._sender.send_text_with_mentions(
                    receive_id=receiver_id,
                    text=content,
                    mention_ids=mentions,
                )
            else:
                if reply_to:
                    return await self._sender.reply_text(
                        message_id=reply_to,
                        text=content,
                    )
                else:
                    return await self._sender.send_text(
                        receive_id=receiver_id,
                        text=content,
                    )

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return SendMessageResult(
                success=False,
                error=str(e),
            )

    def get_connection_url(self) -> Optional[str]:
        """Get the webhook URL.

        Returns None since Feishu uses WebSocket mode, not webhooks.
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

        This is not needed for WebSocket mode but is kept for compatibility.

        Args:
            channel_id: The channel configuration ID.
            signature: The signature from the request header.
            timestamp: The timestamp from the request.
            nonce: The nonce from the request.
            body: The raw request body bytes.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not self._platform_config or not self._platform_config.verification_token:
            return True

        try:
            token = self._platform_config.verification_token
            string_to_sign = f"{timestamp}{nonce}{token}"
            expected_signature = hashlib.sha256(string_to_sign.encode()).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Error validating signature: {e}")
            return False

    def get_capabilities(self) -> ChannelCapabilities:
        """Get Feishu channel capabilities.

        Returns:
            ChannelCapabilities describing Feishu's features.
        """
        return self.get_default_capabilities()

    async def test_connection(self, channel_id: str) -> bool:
        """Test the connection to Feishu.

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
        """Handle received WebSocket message.

        Args:
            event_dict: The parsed event dictionary.
        """
        try:
            event_type = event_dict.get("event_type", "")
            body = event_dict.get("body", {})

            if event_type == FeishuEventType.MESSAGE_RECEIVE:
                header = FeishuEventHeader(
                    event_id=event_dict.get("event_id", ""),
                    event_type=event_type,
                    create_time=str(int(datetime.now().timestamp() * 1000)),
                )

                event = FeishuEvent(header=header, event=body)
                message_event = event.get_message_event()

                if message_event:
                    channel_message = self._parse_message_event(message_event)
                    if channel_message and self._message_callback:
                        try:
                            self._message_callback(channel_message)
                        except Exception as e:
                            logger.error(f"Error in message callback: {e}")

        except Exception as e:
            logger.error(f"Error processing received message: {e}")

    def _parse_message_event(
        self, event: FeishuMessageEvent
    ) -> Optional[ChannelMessage]:
        """Parse a Feishu message event into a ChannelMessage.

        Args:
            event: The Feishu message event.

        Returns:
            ChannelMessage or None if parsing fails.
        """
        try:
            sender_id = event.sender.sender_id or {}
            open_id = sender_id.get("open_id", sender_id.get("user_id", ""))

            message = event.message
            content = self._extract_text_content(message.content, message.message_type)

            is_group = True

            timestamp = None
            if message.create_time:
                try:
                    timestamp = datetime.fromtimestamp(int(message.create_time) / 1000)
                except (ValueError, TypeError):
                    pass

            mentions = None
            if message.mentions:
                mentions = [
                    m.get("id", {}).get("open_id", "")
                    for m in message.mentions
                    if m.get("id", {}).get("open_id")
                ]

            return ChannelMessage(
                channel_type=ChannelType.FEISHU,
                message_id=message.message_id,
                conversation_id=message.chat_id,
                sender={
                    "user_id": open_id,
                    "name": "",
                    "extra": event.sender.model_dump(),
                },
                content=content,
                content_type=message.message_type,
                timestamp=timestamp,
                reply_to=message.parent_id,
                thread_id=message.root_id,
                is_group=is_group,
                mentions=mentions,
                extra={"raw_event": event.model_dump()},
            )

        except Exception as e:
            logger.error(f"Error parsing message event: {e}")
            return None

    def _extract_text_content(self, content: str, content_type: str) -> str:
        """Extract text content from a Feishu message.

        Args:
            content: The raw message content (JSON string).
            content_type: The message type.

        Returns:
            Extracted text content.
        """
        try:
            if content_type == FeishuMessageContentType.TEXT:
                data = json.loads(content)
                return data.get("text", "")

            elif content_type == FeishuMessageContentType.POST:
                data = json.loads(content)
                text_parts = []
                for paragraph in data.get("content", []):
                    for segment in paragraph:
                        if segment.get("tag") == "text":
                            text_parts.append(segment.get("text", ""))
                return "".join(text_parts)

            else:
                return f"[{content_type}]"

        except json.JSONDecodeError:
            return content
        except Exception as e:
            logger.error(f"Error extracting text content: {e}")
            return content

    def set_message_callback(self, callback: Callable[[ChannelMessage], None]) -> None:
        """Set the message callback.

        Args:
            callback: The callback function for received messages.
        """
        self._message_callback = callback

    @property
    def client(self) -> Optional[FeishuClient]:
        """Get the Feishu client."""
        return self._client

    @property
    def sender(self) -> Optional[FeishuSender]:
        """Get the Feishu sender."""
        return self._sender


class FeishuEventHeader:
    """Simple event header class for parsing."""

    def __init__(
        self,
        event_id: str,
        event_type: str,
        create_time: str,
        token: Optional[str] = None,
        app_id: Optional[str] = None,
        tenant_key: Optional[str] = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.create_time = create_time
        self.token = token
        self.app_id = app_id
        self.tenant_key = tenant_key
