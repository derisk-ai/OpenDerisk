"""Channel module for Derisk.

This module provides types and interfaces for message channels,
including:
- Channel types (DingTalk, Feishu, WeChat, QQ)
- Channel configuration
- Channel message format
- Channel handler interface
- Message router for agent integration

Example:
    ```python
    from derisk.channel import (
        ChannelType,
        ChannelConfig,
        ChannelMessage,
        ChannelHandler,
    )

    # Create a channel message
    message = ChannelMessage(
        channel_type=ChannelType.DINGTALK,
        sender=ChannelSender(
            user_id="user123",
            name="John Doe",
        ),
        content="Hello from DingTalk",
    )
    ```
"""

from .base import (
    ChannelCapabilities,
    ChannelConfig,
    ChannelConnectionState,
    ChannelHandler,
    ChannelMessage,
    ChannelSender,
    ChannelType,
    SendMessageResult,
)
from .registry import ChannelHandlerRegistry
from .router import ChannelMessageRouter
from .schemas import DingTalkConfig, FeishuConfig

__all__ = [
    # Types
    "ChannelType",
    "ChannelConfig",
    "ChannelSender",
    "ChannelMessage",
    "ChannelCapabilities",
    "ChannelConnectionState",
    "SendMessageResult",
    # Interfaces
    "ChannelHandler",
    # Registry
    "ChannelHandlerRegistry",
    # Router
    "ChannelMessageRouter",
    # Platform configs
    "DingTalkConfig",
    "FeishuConfig",
]
