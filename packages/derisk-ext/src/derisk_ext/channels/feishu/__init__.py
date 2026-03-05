"""Feishu channel implementation.

This module provides a complete implementation for Feishu/Lark integration
using the official lark-oapi SDK with WebSocket mode for receiving messages.
"""

from derisk_ext.channels.feishu.client import FeishuClient
from derisk_ext.channels.feishu.handler import FeishuChannelHandler
from derisk_ext.channels.feishu.sender import FeishuSender

__all__ = [
    "FeishuClient",
    "FeishuChannelHandler",
    "FeishuSender",
]
