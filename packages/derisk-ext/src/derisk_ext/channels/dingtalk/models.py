"""DingTalk event and message models.

This module defines Pydantic models for DingTalk events and messages.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class DingTalkEventType(str, Enum):
    """DingTalk event type enumeration."""

    # Robot message event from ChatbotHandler (private chat or group @mention)
    CHATBOT_MESSAGE = "chatbot_message"


class DingTalkMessageType(str, Enum):
    """DingTalk message type enumeration."""

    TEXT = "text"
    MARKDOWN = "markdown"
    ACTION_CARD = "actionCard"
    IMAGE = "picture"
    FILE = "file"
    LINK = "link"
    OA = "oa"


class DingTalkChatType(str, Enum):
    """DingTalk chat type enumeration."""

    PRIVATE = "private"
    GROUP = "group"


class DingTalkMessageContent(BaseModel):
    """DingTalk message content."""

    model_config = ConfigDict(title="DingTalkMessageContent")

    content: str = Field(default="", description="Message content")
    title: Optional[str] = Field(default=None, description="Message title")


class DingTalkTextMessage(BaseModel):
    """DingTalk text message to send."""

    model_config = ConfigDict(title="DingTalkTextMessage")

    msgtype: str = Field(default="text", description="Message type")
    text: Dict[str, Any] = Field(
        default_factory=lambda: {"content": ""},
        description="Text content",
    )


class DingTalkMarkdownMessage(BaseModel):
    """DingTalk markdown message to send."""

    model_config = ConfigDict(title="DingTalkMarkdownMessage")

    msgtype: str = Field(default="markdown", description="Message type")
    markdown: Dict[str, Any] = Field(
        default_factory=lambda: {"title": "", "text": ""},
        description="Markdown content",
    )


class DingTalkActionCardMessage(BaseModel):
    """DingTalk action card message to send."""

    model_config = ConfigDict(title="DingTalkActionCardMessage")

    msgtype: str = Field(default="actionCard", description="Message type")
    actionCard: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action card content",
    )


class DingTalkAtUser(BaseModel):
    """DingTalk @mention user info."""

    model_config = ConfigDict(title="DingTalkAtUser")

    dingtalkId: str = Field(..., description="User DingTalk ID")
    staffId: Optional[str] = Field(default=None, description="Staff ID")


class DingTalkSendResult(BaseModel):
    """DingTalk message send result."""

    model_config = ConfigDict(title="DingTalkSendResult")

    errcode: int = Field(default=0, description="Error code")
    errmsg: str = Field(default="", description="Error message")
    msgid: Optional[str] = Field(default=None, description="Message ID")
