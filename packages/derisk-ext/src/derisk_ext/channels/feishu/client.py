"""Feishu API client using lark-oapi SDK.

This module provides a client for interacting with Feishu/Lark APIs
using the official lark-oapi Python SDK with WebSocket support.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from derisk.channel.base import SendMessageResult
from derisk.channel.schemas import FeishuConfig

logger = logging.getLogger(__name__)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        GetChatRequest,
        GetMessageRequest,
    )

    LARK_SDK_AVAILABLE = True
except ImportError:
    LARK_SDK_AVAILABLE = False
    lark = None
    logger.warning("lark-oapi SDK not installed. Install with: pip install lark-oapi")


class FeishuClient:
    """Feishu API client using lark-oapi SDK.

    This client handles:
    - Authentication and token management
    - WebSocket connection for receiving events
    - Message sending and receiving
    - User and conversation information retrieval
    """

    def __init__(
        self,
        config: FeishuConfig,
        message_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """Initialize the Feishu client.

        Args:
            config: Feishu configuration.
            message_callback: Optional callback for received messages.
        """
        if not LARK_SDK_AVAILABLE:
            raise ImportError(
                "lark-oapi SDK is required for Feishu integration. "
                "Install with: pip install lark-oapi"
            )

        self._config = config
        self._message_callback = message_callback
        self._client: Optional[Any] = None
        self._ws_client: Optional[Any] = None
        self._running = False

        domain = lark.FEISHU_DOMAIN if config.domain == "feishu" else lark.LARK_DOMAIN

        self._client = (
            lark.Client.builder()
            .app_id(config.app_id)
            .app_secret(config.app_secret)
            .domain(domain)
            .log_level(lark.LogLevel.DEBUG)
            .build()
        )

        logger.info(f"FeishuClient initialized for app_id: {config.app_id}")

    async def start(self) -> None:
        """Start the WebSocket connection for receiving events."""
        if self._running:
            logger.warning("Feishu client is already running")
            return

        self._running = True
        await self._connect_websocket()

    async def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
        self._ws_client = None
        logger.info("Feishu client stopped")

    async def _connect_websocket(self) -> None:
        """Establish WebSocket connection for receiving events."""
        if not LARK_SDK_AVAILABLE:
            return

        def do_p2_im_message_receive_v1(data: Any) -> None:
            """Handle receiving message event."""
            try:
                if self._message_callback:
                    event_dict = {
                        "event_type": "im.message.receive_v1",
                        "event_id": data.header.event_id,
                        "body": data.event.model_dump() if hasattr(data.event, 'model_dump') else data.event,
                        "raw": data,
                    }
                    asyncio.create_task(
                        asyncio.to_thread(self._message_callback, event_dict)
                    )
            except Exception as e:
                logger.error(f"Error processing message event: {e}")

        try:
            event_handler = (
                lark.EventDispatcherHandler.builder(
                    self._config.verification_token or "",
                    self._config.encrypt_key or ""
                )
                .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
                .build()
            )

            self._ws_client = lark.ws.Client(
                self._config.app_id,
                self._config.app_secret,
                event_handler=event_handler,
                domain=lark.FEISHU_DOMAIN if self._config.domain == "feishu" else lark.LARK_DOMAIN,
                log_level=lark.LogLevel.DEBUG
            )
            self._ws_client.start()
            logger.info("WebSocket connection established")
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            self._running = False

    async def send_message(
        self,
        receive_id: str,
        content: str,
        msg_type: str = "text",
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a message to a user or chat.

        Args:
            receive_id: The receiver ID (user_id, chat_id, or open_id).
            content: The message content.
            msg_type: Message type (text, post, image, etc.).
            receive_id_type: Type of receive_id (chat_id, open_id, user_id).

        Returns:
            SendMessageResult indicating success or failure.
        """
        if not self._client:
            return SendMessageResult(
                success=False,
                error="Client not initialized",
            )

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                )
                .build()
            )

            response = self._client.im.v1.message.create(request)

            if response.success():
                return SendMessageResult(
                    success=True,
                    message_id=response.data.message_id,
                )
            else:
                return SendMessageResult(
                    success=False,
                    error=f"API error: {response.msg}",
                )

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return SendMessageResult(
                success=False,
                error=str(e),
            )

    async def send_text_message(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send a text message.

        Args:
            receive_id: The receiver ID.
            text: The text content.
            receive_id_type: Type of receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        import json

        content = json.dumps({"text": text})
        return await self.send_message(
            receive_id=receive_id,
            content=content,
            msg_type="text",
            receive_id_type=receive_id_type,
        )

    async def send_interactive_card(
        self,
        receive_id: str,
        title: str,
        content: str,
        receive_id_type: str = "chat_id",
    ) -> SendMessageResult:
        """Send an interactive card message.

        Args:
            receive_id: The receiver ID.
            title: Card title.
            content: Card content (markdown supported).
            receive_id_type: Type of receive_id.

        Returns:
            SendMessageResult indicating success or failure.
        """
        import json

        card_content = {
            "type": "template",
            "data": {
                "template_id": "AAqk3gJ",  # Default template
                "template_variable": {
                    "title": title,
                    "content": content,
                },
            },
        }

        return await self.send_message(
            receive_id=receive_id,
            content=json.dumps(card_content),
            msg_type="interactive",
            receive_id_type=receive_id_type,
        )

    async def reply_message(
        self,
        message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> SendMessageResult:
        """Reply to a message.

        Args:
            message_id: The message ID to reply to.
            content: The reply content.
            msg_type: Message type.

        Returns:
            SendMessageResult indicating success or failure.
        """
        if not self._client:
            return SendMessageResult(
                success=False,
                error="Client not initialized",
            )

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(message_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                )
                .build()
            )

            response = self._client.im.v1.message.create(request)

            if response.success():
                return SendMessageResult(
                    success=True,
                    message_id=response.data.message_id,
                )
            else:
                return SendMessageResult(
                    success=False,
                    error=f"API error: {response.msg}",
                )

        except Exception as e:
            logger.error(f"Error replying to message: {e}")
            return SendMessageResult(
                success=False,
                error=str(e),
            )

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information by user ID.

        Args:
            user_id: The user ID.

        Returns:
            User information dictionary or None if not found.
        """
        if not self._client:
            return None

        try:
            response = self._client.contact.v3.user.get(
                user_id=user_id,
                user_id_type="open_id",
            )

            if response.success():
                return {
                    "user_id": response.data.user.user_id,
                    "name": response.data.user.name,
                    "avatar": response.data.user.avatar_url,
                    "department_ids": response.data.user.department_ids,
                }
            return None

        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    async def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """Get bot information for connection test.

        Returns:
            Bot information dictionary or None if failed.
        """
        if not self._client:
            return None

        try:
            # Create a client for bot info request
            domain = lark.FEISHU_DOMAIN if self._config.domain == "feishu" else lark.LARK_DOMAIN
            client = (
                lark.Client.builder()
                .app_id(self._config.app_id)
                .app_secret(self._config.app_secret)
                .domain(domain)
                .build()
            )

            # Call bot/v3/info API
            response = client.request(
                method="GET",
                url="/open-apis/bot/v3/info",
            )

            if response.code == 0:
                bot = response.data.get("bot", {}) if isinstance(response.data, dict) else {}
                return {
                    "app_name": bot.get("app_name", self._config.app_id),
                    "open_id": bot.get("open_id"),
                    "avatar_url": bot.get("avatar_url"),
                }
            logger.error(f"Failed to get bot info: code={response.code}, msg={response.msg}")
            return None
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return None

    async def get_conversation_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation information.

        Args:
            chat_id: The chat/conversation ID.

        Returns:
            Conversation information or None if not found.
        """
        if not self._client:
            return None

        try:
            request = GetChatRequest.builder().chat_id(chat_id).build()

            response = self._client.im.v1.chat.get(request)

            if response.success():
                return {
                    "chat_id": response.data.chat_id,
                    "name": response.data.name,
                    "chat_mode": getattr(response.data, "chat_mode", None),
                    "chat_type": getattr(response.data, "chat_type", None),
                }
            return None

        except Exception as e:
            logger.error(f"Error getting conversation info: {e}")
            return None

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._running and self._ws_client is not None
