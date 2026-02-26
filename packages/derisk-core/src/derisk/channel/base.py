"""Channel base types and interfaces.

This module defines the base types and abstract interfaces for message channels.
These are used by derisk-ext to implement channel handlers for DingTalk, Feishu, etc.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class ChannelType(str, Enum):
    """Channel type enumeration."""

    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    # Future support
    WECHAT = "wechat"
    QQ = "qq"


class ChannelSender(BaseModel):
    """Channel message sender information."""

    model_config = ConfigDict(title="ChannelSender")

    user_id: str = Field(
        ...,
        description="User ID in the channel platform",
    )
    name: Optional[str] = Field(
        default=None,
        description="User display name",
    )
    avatar: Optional[str] = Field(
        default=None,
        description="User avatar URL",
    )
    department: Optional[str] = Field(
        default=None,
        description="User department",
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extra sender information",
    )


class ChannelCapabilities(BaseModel):
    """Channel capabilities definition."""

    model_config = ConfigDict(title="ChannelCapabilities")

    chat_types: List[str] = Field(
        default_factory=lambda: ["private", "group"],
        description="Supported chat types (private, group)",
    )
    threads: bool = Field(
        default=False,
        description="Whether the channel supports threaded replies",
    )
    media: List[str] = Field(
        default_factory=lambda: ["text"],
        description="Supported media types (text, image, video, file, audio)",
    )
    reactions: bool = Field(
        default=False,
        description="Whether the channel supports message reactions",
    )
    edit: bool = Field(
        default=False,
        description="Whether the channel supports editing messages",
    )
    reply: bool = Field(
        default=True,
        description="Whether the channel supports replying to messages",
    )


class ChannelConfig(BaseModel):
    """Base channel configuration."""

    model_config = ConfigDict(title="ChannelConfig")

    enabled: bool = Field(
        default=True,
        description="Whether the channel is enabled",
    )
    name: str = Field(
        ...,
        description="Channel display name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Channel description",
    )


class ChannelMessage(BaseModel):
    """Unified channel message format."""

    model_config = ConfigDict(title="ChannelMessage")

    channel_type: ChannelType = Field(
        ...,
        description="The channel type",
    )
    message_id: str = Field(
        ...,
        description="Unique message ID from the channel",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation/chat ID",
    )
    sender: ChannelSender = Field(
        ...,
        description="Message sender information",
    )
    content: str = Field(
        ...,
        description="Message content (text)",
    )
    content_type: str = Field(
        default="text",
        description="Content type (text, image, etc.)",
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Message timestamp",
    )
    reply_to: Optional[str] = Field(
        default=None,
        description="Message ID being replied to (if any)",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Thread ID (for threaded conversations)",
    )
    is_group: bool = Field(
        default=False,
        description="Whether this is a group message",
    )
    mentions: Optional[List[str]] = Field(
        default=None,
        description="List of mentioned user IDs",
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extra message data from the channel",
    )


class ChannelHandler(ABC):
    """Abstract base class for channel handlers.

    Channel handlers are implemented in derisk-ext for specific platforms.
    They handle message processing, signature validation, and capability reporting.
    """

    @abstractmethod
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
        pass

    @abstractmethod
    def validate_signature(
        self,
        channel_id: str,
        signature: str,
        timestamp: str,
        nonce: str,
        body: bytes,
    ) -> bool:
        """Validate the webhook signature from the channel platform.

        Args:
            channel_id: The channel configuration ID.
            signature: The signature from the request header.
            timestamp: The timestamp from the request.
            nonce: The nonce from the request.
            body: The raw request body bytes.

        Returns:
            True if the signature is valid, False otherwise.
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> ChannelCapabilities:
        """Get the capabilities supported by this channel.

        Returns:
            ChannelCapabilities instance describing what this channel supports.
        """
        pass

    @abstractmethod
    async def test_connection(self, channel_id: str) -> bool:
        """Test the connection to the channel platform.

        Args:
            channel_id: The channel configuration ID.

        Returns:
            True if the connection is successful, False otherwise.
        """
        pass