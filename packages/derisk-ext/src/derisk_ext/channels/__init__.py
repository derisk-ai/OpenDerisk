"""Channel implementations for various platforms.

This package provides concrete implementations of channel handlers
for platforms like Feishu and DingTalk.
"""

from derisk_ext.channels.feishu import FeishuChannelHandler
from derisk_ext.channels.dingtalk import DingTalkChannelHandler

__all__ = [
    "FeishuChannelHandler",
    "DingTalkChannelHandler",
]
