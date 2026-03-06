"""DingTalk channel implementation.

This module provides a complete implementation for DingTalk integration
using the official dingtalk-stream SDK with Stream mode for receiving messages.
"""

from derisk_ext.channels.dingtalk.client import DingTalkClient
from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler
from derisk_ext.channels.dingtalk.sender import DingTalkSender

__all__ = [
    "DingTalkClient",
    "DingTalkChannelHandler",
    "DingTalkSender",
]
