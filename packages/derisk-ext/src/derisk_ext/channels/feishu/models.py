"""Feishu event and message models.

This module defines Pydantic models for Feishu events and messages.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class FeishuEventType(str, Enum):
    """Feishu event type enumeration."""

    MESSAGE_RECEIVE = "im.message.receive_v1"
    MESSAGE_READ = "im.message.read_v1"
    MESSAGE_REACTION = "im.message.reaction.created_v1"
    BOT_ADDED = "im.chat.member.bot.added_v1"
    BOT_REMOVED = "im.chat.member.bot.deleted_v1"
    URL_VERIFY = "url_verification"


class FeishuMessageContentType(str, Enum):
    """Feishu message content type enumeration."""

    TEXT = "text"
    POST = "post"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    MEDIA = "media"
    STICKER = "sticker"
    INTERACTIVE = "interactive"
    LOCATION = "location"
    SHARE_CHAT = "share_chat"
    SHARE_USER = "share_user"


class FeishuChatType(str, Enum):
    """Feishu chat type enumeration."""

    PRIVATE = "p2p"
    GROUP = "group"


class FeishuEventHeader(BaseModel):
    """Feishu event header."""

    model_config = ConfigDict(title="FeishuEventHeader")

    event_id: str = Field(..., description="Event ID")
    event_type: str = Field(..., description="Event type")
    create_time: str = Field(..., description="Event create time")
    token: Optional[str] = Field(default=None, description="Verification token")
    app_id: Optional[str] = Field(default=None, description="App ID")
    tenant_key: Optional[str] = Field(default=None, description="Tenant key")


class FeishuSender(BaseModel):
    """Feishu message sender."""

    model_config = ConfigDict(title="FeishuSender")

    sender_id: Optional[Dict[str, str]] = Field(
        default=None,
        description="Sender ID with type (open_id, user_id, union_id)",
    )
    sender_type: Optional[str] = Field(
        default=None,
        description="Sender type (app, user)",
    )
    tenant_key: Optional[str] = Field(
        default=None,
        description="Tenant key",
    )


class FeishuMessage(BaseModel):
    """Feishu message content."""

    model_config = ConfigDict(title="FeishuMessage")

    message_id: str = Field(..., description="Message ID")
    root_id: Optional[str] = Field(default=None, description="Root message ID")
    parent_id: Optional[str] = Field(default=None, description="Parent message ID")
    create_time: str = Field(..., description="Message create time")
    chat_id: str = Field(..., description="Chat ID")
    message_type: str = Field(..., description="Message type")
    content: str = Field(..., description="Message content (JSON string)")
    mentions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Mentioned users/robots",
    )


class FeishuMessageEvent(BaseModel):
    """Feishu message receive event."""

    model_config = ConfigDict(title="FeishuMessageEvent")

    sender: FeishuSender = Field(..., description="Message sender")
    message: FeishuMessage = Field(..., description="Message content")


class FeishuEvent(BaseModel):
    """Feishu event wrapper."""

    model_config = ConfigDict(title="FeishuEvent")

    header: FeishuEventHeader = Field(..., description="Event header")
    event: Dict[str, Any] = Field(..., description="Event body")

    def get_message_event(self) -> Optional[FeishuMessageEvent]:
        """Parse message event from the event body.

        Returns:
            FeishuMessageEvent if this is a message event, None otherwise.
        """
        if self.header.event_type == FeishuEventType.MESSAGE_RECEIVE:
            try:
                return FeishuMessageEvent(**self.event)
            except Exception:
                pass
        return None


class FeishuUrlVerifyEvent(BaseModel):
    """Feishu URL verification event."""

    model_config = ConfigDict(title="FeishuUrlVerifyEvent")

    challenge: str = Field(..., description="Challenge string to echo back")


class FeishuTextContent(BaseModel):
    """Feishu text message content."""

    model_config = ConfigDict(title="FeishuTextContent")

    text: str = Field(..., description="Text content")


class FeishuPostContent(BaseModel):
    """Feishu post (rich text) message content."""

    model_config = ConfigDict(title="FeishuPostContent")

    title: Optional[str] = Field(default=None, description="Post title")
    content: List[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Post content segments",
    )


class FeishuImageContent(BaseModel):
    """Feishu image message content."""

    model_config = ConfigDict(title="FeishuImageContent")

    image_key: str = Field(..., description="Image key")


class FeishuFileContent(BaseModel):
    """Feishu file message content."""

    model_config = ConfigDict(title="FeishuFileContent")

    file_key: str = Field(..., description="File key")
    file_name: Optional[str] = Field(default=None, description="File name")


class FeishuInteractiveCard(BaseModel):
    """Feishu interactive card message content."""

    model_config = ConfigDict(title="FeishuInteractiveCard")

    type: str = Field(default="template", description="Card type")
    template_id: Optional[str] = Field(default=None, description="Template ID")
    template_variable: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Template variables",
    )
    elements: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Card elements",
    )


class FeishuMessageToSend(BaseModel):
    """Message to send via Feishu API."""

    model_config = ConfigDict(title="FeishuMessageToSend")

    receive_id: str = Field(..., description="Receiver ID")
    msg_type: str = Field(default="text", description="Message type")
    content: str = Field(..., description="Message content (JSON string)")
    receive_id_type: Optional[str] = Field(
        default="chat_id",
        description="Receiver ID type",
    )
