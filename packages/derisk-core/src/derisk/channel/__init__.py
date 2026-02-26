"""Channel module for Derisk.

This module provides types and interfaces for message channels,
including:
- Channel types (DingTalk, Feishu, WeChat, QQ)
- Channel configuration
- Channel message format
- Channel handler interface

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
    ChannelHandler,
    ChannelMessage,
    ChannelSender,
    ChannelType,
)
from .schemas import DingTalkConfig, FeishuConfig

__all__ = [
    # Types
    "ChannelType",
    "ChannelConfig",
    "ChannelSender",
    "ChannelMessage",
    "ChannelCapabilities",
    # Interfaces
    "ChannelHandler",
    # Platform configs
    "DingTalkConfig",
    "FeishuConfig",
]