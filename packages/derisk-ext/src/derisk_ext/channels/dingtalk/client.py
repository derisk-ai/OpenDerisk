"""DingTalk API client using dingtalk-stream SDK.

This module provides a client for interacting with DingTalk APIs
using the official dingtalk-stream Python SDK with Stream mode.
"""

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import httpx

from derisk.channel.base import SendMessageResult
from derisk.channel.schemas import DingTalkConfig

if TYPE_CHECKING:
    import dingtalk_stream

logger = logging.getLogger(__name__)


class DingTalkChatbotHandler:
    """Handler for DingTalk robot chat messages.

    This handler uses ChatbotHandler to process robot chat messages
    (private messages and group @mentions).
    """

    def __init__(self, message_callback: Callable[[Dict[str, Any]], None]):
        """Initialize the handler.

        Args:
            message_callback: Callback function to handle parsed messages.
        """
        self._message_callback = message_callback
        self._handler: Optional["dingtalk_stream.ChatbotHandler"] = None

    def create_handler(self) -> "dingtalk_stream.ChatbotHandler":
        """Create and return the actual ChatbotHandler instance.

        Returns:
            A ChatbotHandler instance configured with the message callback.
        """
        import dingtalk_stream

        class _ChatbotHandler(dingtalk_stream.ChatbotHandler):
            """Inner ChatbotHandler implementation."""

            def __init__(
                self, callback: Callable[[Dict[str, Any]], None]
            ):
                super().__init__()
                self._callback = callback

            async def process(
                self, callback_message: dingtalk_stream.CallbackMessage
            ) -> tuple:
                """Process incoming chatbot message.

                Args:
                    callback_message: The CallbackMessage containing the message data.

                Returns:
                    Tuple of (AckMessage.STATUS_OK, 'OK') on success.
                """
                try:
                    # Parse as ChatbotMessage
                    chatbot_msg = dingtalk_stream.ChatbotMessage.from_dict(
                        callback_message.data
                    )

                    # Convert to standard format
                    event_dict = self._convert_to_event_dict(
                        chatbot_msg, callback_message
                    )

                    if self._callback:
                        await asyncio.to_thread(self._callback, event_dict)

                except Exception as e:
                    logger.error(f"Error processing chatbot message: {e}")

                return dingtalk_stream.AckMessage.STATUS_OK, "OK"

            def _convert_to_event_dict(
                self,
                msg: dingtalk_stream.ChatbotMessage,
                callback: dingtalk_stream.CallbackMessage,
            ) -> Dict[str, Any]:
                """Convert ChatbotMessage to standard event dictionary.

                Args:
                    msg: The parsed ChatbotMessage.
                    callback: The original CallbackMessage.

                Returns:
                    A dictionary with standardized message fields.
                """
                return {
                    "event_type": "chatbot_message",
                    "message_id": msg.message_id,
                    "conversation_id": msg.conversation_id,
                    "conversation_type": (
                        "group" if msg.conversation_type == "2" else "private"
                    ),
                    "conversation_title": msg.conversation_title,
                    "sender_id": msg.sender_id,
                    "sender_nick": msg.sender_nick,
                    "sender_staff_id": msg.sender_staff_id,
                    "sender_corp_id": msg.sender_corp_id,
                    "robot_code": msg.robot_code,
                    "message_type": msg.message_type,
                    "text": msg.text.content if msg.text else "",
                    "at_users": (
                        [u.to_dict() for u in msg.at_users]
                        if msg.at_users
                        else []
                    ),
                    "session_webhook": msg.session_webhook,
                    "create_at": msg.create_at,
                    "is_in_at_list": msg.is_in_at_list,
                    "raw_message": msg,
                    "raw_callback": callback,
                }

        self._handler = _ChatbotHandler(self._message_callback)
        return self._handler

DINGTALK_API_BASE = "https://oapi.dingtalk.com"
DINGTALK_TOP_API_BASE = "https://api.dingtalk.com"


class DingTalkClient:
    """DingTalk API client.

    This client handles:
    - Authentication and token management
    - Stream mode connection for receiving events
    - Message sending via REST API
    - User and conversation information retrieval
    """

    def __init__(
        self,
        config: DingTalkConfig,
        message_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """Initialize the DingTalk client.

        Args:
            config: DingTalk configuration.
            message_callback: Optional callback for received messages.
        """
        self._config = config
        self._message_callback = message_callback
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._running = False
        self._stream_client: Optional[Any] = None
        self._stream_thread: Optional[threading.Thread] = None

        self._http_client = httpx.AsyncClient(timeout=30.0)

        logger.info(f"DingTalkClient initialized for app_id: {config.app_id}")

    async def _get_access_token(self) -> Optional[str]:
        """Get or refresh the access token.

        Returns:
            The access token or None if failed.
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        try:
            url = f"{DINGTALK_API_BASE}/gettoken"
            params = {
                "appkey": self._config.app_id,
                "appsecret": self._config.app_secret,
            }

            response = await self._http_client.get(url, params=params)
            result = response.json()

            if result.get("errcode") == 0:
                self._access_token = result.get("access_token")
                expires_in = result.get("expires_in", 7200)
                self._token_expires_at = time.time() + expires_in - 300
                logger.info("Successfully obtained DingTalk access token")
                return self._access_token
            else:
                logger.error(f"Failed to get access token: {result}")
                return None

        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None

    async def start(self) -> None:
        """Start the Stream mode connection for receiving events."""
        if self._running:
            logger.warning("DingTalk client is already running")
            return

        self._running = True

        try:
            await self._start_stream_mode()
            logger.info("DingTalk client started")
        except Exception as e:
            logger.error(f"Failed to start DingTalk client: {e}")
            self._running = False

    async def _start_stream_mode(self) -> None:
        """Start Stream mode for receiving robot messages using ChatbotHandler."""
        try:
            import dingtalk_stream

            # Create credential and client
            credential = dingtalk_stream.Credential(
                client_id=self._config.app_id,
                client_secret=self._config.app_secret,
            )
            self._stream_client = dingtalk_stream.DingTalkStreamClient(credential)

            # Register chatbot handler for robot messages
            # ChatbotMessage.TOPIC = '/v1.0/im/bot/messages/get'
            chatbot_handler = DingTalkChatbotHandler(self._message_callback)
            self._stream_client.register_callback_handler(
                dingtalk_stream.ChatbotMessage.TOPIC,
                chatbot_handler.create_handler(),
            )

            def run_stream():
                try:
                    self._stream_client.start_forever()
                except Exception as e:
                    logger.error(f"Stream client error: {e}")

            self._stream_thread = threading.Thread(target=run_stream, daemon=True)
            self._stream_thread.start()

            logger.info("DingTalk Stream mode started with ChatbotHandler")

        except ImportError as e:
            logger.warning(
                "dingtalk-stream SDK not installed. "
                "Install with: pip install dingtalk-stream"
            )
            logger.info("Running in API-only mode without Stream support")
        except Exception as e:
            logger.error(f"Failed to start Stream mode: {e}")
            raise

    async def stop(self) -> None:
        """Stop the Stream mode connection."""
        self._running = False

        if self._stream_client:
            try:
                # Try graceful_stop first, then stop, otherwise just cleanup
                if hasattr(self._stream_client, 'graceful_stop'):
                    self._stream_client.graceful_stop()
                elif hasattr(self._stream_client, 'stop'):
                    self._stream_client.stop()
                # If no stop method, the daemon thread will terminate on its own
            except Exception as e:
                logger.error(f"Error stopping Stream client: {e}")

        self._stream_client = None
        self._stream_thread = None

        await self._http_client.aclose()
        logger.info("DingTalk client stopped")

    async def send_message(
        self,
        user_id: str,
        msg: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> SendMessageResult:
        """Send a message to a user via DingTalk.

        Args:
            user_id: The receiver's user ID.
            msg: Message content dictionary.
            agent_id: Optional agent ID (uses config default if not provided).

        Returns:
            SendMessageResult indicating success or failure.
        """
        agent_id = agent_id or self._config.agent_id
        if not agent_id:
            return SendMessageResult(
                success=False,
                error="Agent ID is required",
            )

        token = await self._get_access_token()
        if not token:
            return SendMessageResult(
                success=False,
                error="Failed to get access token",
            )

        try:
            url = f"{DINGTALK_API_BASE}/topapi/message/corpsend"
            params = {"access_token": token}

            data = {
                "agent_id": agent_id,
                "userid_list": user_id,
                "msg": msg,
            }

            response = await self._http_client.post(url, params=params, json=data)
            result = response.json()

            if result.get("errcode") == 0:
                return SendMessageResult(
                    success=True,
                    message_id=result.get("task_id"),
                )
            else:
                return SendMessageResult(
                    success=False,
                    error=result.get("errmsg", "Unknown error"),
                )

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return SendMessageResult(
                success=False,
                error=str(e),
            )

    async def send_private_message(
        self,
        user_id: str,
        msg: Dict[str, Any],
    ) -> SendMessageResult:
        """Send a private message to a user.

        Args:
            user_id: The receiver's user ID.
            msg: Message content dictionary.

        Returns:
            SendMessageResult indicating success or failure.
        """
        token = await self._get_access_token()
        if not token:
            return SendMessageResult(
                success=False,
                error="Failed to get access token",
            )

        try:
            url = f"{DINGTALK_TOP_API_BASE}/v1.0/robot/oToMessages/batchSend"

            headers = {"x-acs-dingtalk-access-token": token}

            data = {
                "robotCode": self._config.app_id,
                "userIds": [user_id],
                "msgKey": msg.get("msgKey", "sampleText"),
                "msgParam": msg.get("msgParam", "{}"),
            }

            response = await self._http_client.post(url, headers=headers, json=data)
            result = response.json()

            if result.get("processQueryKeys"):
                return SendMessageResult(
                    success=True,
                    message_id=result.get("processQueryKeys", [None])[0],
                )
            else:
                return SendMessageResult(
                    success=False,
                    error=str(result),
                )

        except Exception as e:
            logger.error(f"Error sending private message: {e}")
            return SendMessageResult(
                success=False,
                error=str(e),
            )

    async def send_group_message(
        self,
        conversation_id: str,
        msg: Dict[str, Any],
    ) -> SendMessageResult:
        """Send a message to a group conversation.

        Args:
            conversation_id: The conversation ID (open_conversation_id).
            msg: Message content dictionary.

        Returns:
            SendMessageResult indicating success or failure.
        """
        token = await self._get_access_token()
        if not token:
            return SendMessageResult(
                success=False,
                error="Failed to get access token",
            )

        try:
            url = f"{DINGTALK_TOP_API_BASE}/v1.0/robot/groupMessages/send"

            headers = {"x-acs-dingtalk-access-token": token}

            data = {
                "robotCode": self._config.app_id,
                "openConversationId": conversation_id,
                "msgKey": msg.get("msgKey", "sampleText"),
                "msgParam": msg.get("msgParam", "{}"),
            }

            response = await self._http_client.post(url, headers=headers, json=data)
            result = response.json()

            if result.get("processQueryKey"):
                return SendMessageResult(
                    success=True,
                    message_id=result.get("processQueryKey"),
                )
            else:
                return SendMessageResult(
                    success=False,
                    error=str(result),
                )

        except Exception as e:
            logger.error(f"Error sending group message: {e}")
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
        token = await self._get_access_token()
        if not token:
            return None

        try:
            url = f"{DINGTALK_API_BASE}/topapi/v2/user/get"
            params = {"access_token": token}

            data = {"userid": user_id}

            response = await self._http_client.post(url, params=params, json=data)
            result = response.json()

            if result.get("errcode") == 0:
                user_info = result.get("result", {})
                return {
                    "user_id": user_info.get("userid"),
                    "name": user_info.get("name"),
                    "avatar": user_info.get("avatar"),
                    "mobile": user_info.get("mobile"),
                    "email": user_info.get("email"),
                    "department_ids": user_info.get("dept_id_list", []),
                }
            return None

        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    async def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """Get bot information.

        Returns:
            Bot information dictionary or None if failed.
        """
        token = await self._get_access_token()
        if not token:
            return None

        try:
            return {
                "app_id": self._config.app_id,
                "agent_id": self._config.agent_id,
            }
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return None

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._running
