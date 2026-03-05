"""Unit tests for Feishu channel implementation.

This module contains unit tests for:
- Feishu client
- Feishu sender
- Feishu handler
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from derisk.channel import (
    ChannelCapabilities,
    ChannelConfig,
    ChannelMessage,
    ChannelType,
    SendMessageResult,
)
from derisk.channel.schemas import FeishuConfig

from derisk_ext.channels.feishu.models import (
    FeishuEvent,
    FeishuEventHeader,
    FeishuMessage,
    FeishuMessageContentType,
    FeishuMessageEvent,
    FeishuSender,
)


class TestFeishuModels:
    """Tests for Feishu models."""

    def test_feishu_sender(self):
        """Test FeishuSender model."""
        sender = FeishuSender(
            sender_id={"open_id": "ou_xxx"},
            sender_type="user",
        )
        assert sender.sender_id["open_id"] == "ou_xxx"
        assert sender.sender_type == "user"

    def test_feishu_message(self):
        """Test FeishuMessage model."""
        message = FeishuMessage(
            message_id="om_xxx",
            chat_id="oc_xxx",
            message_type="text",
            content='{"text": "Hello"}',
            create_time="1234567890000",
        )
        assert message.message_id == "om_xxx"
        assert message.chat_id == "oc_xxx"
        assert message.message_type == "text"

    def test_feishu_message_event(self):
        """Test FeishuMessageEvent model."""
        event = FeishuMessageEvent(
            sender=FeishuSender(sender_id={"open_id": "ou_xxx"}),
            message=FeishuMessage(
                message_id="om_xxx",
                chat_id="oc_xxx",
                message_type="text",
                content='{"text": "Hello"}',
                create_time="1234567890000",
            ),
        )
        assert event.sender.sender_id["open_id"] == "ou_xxx"
        assert event.message.message_id == "om_xxx"

    def test_feishu_event(self):
        """Test FeishuEvent model."""
        event = FeishuEvent(
            header=FeishuEventHeader(
                event_id="ev_xxx",
                event_type="im.message.receive_v1",
                create_time="1234567890",
            ),
            event={
                "sender": {"sender_id": {"open_id": "ou_xxx"}},
                "message": {
                    "message_id": "om_xxx",
                    "chat_id": "oc_xxx",
                    "message_type": "text",
                    "content": '{"text": "Hello"}',
                    "create_time": "1234567890000",
                },
            },
        )
        assert event.header.event_id == "ev_xxx"
        message_event = event.get_message_event()
        assert message_event is not None
        assert message_event.message.message_id == "om_xxx"


class TestFeishuSender:
    """Tests for FeishuSender."""

    @pytest.mark.asyncio
    async def test_send_text(self):
        """Test sending text message."""
        from derisk_ext.channels.feishu.sender import FeishuSender

        mock_client = MagicMock()
        mock_client.send_text_message = AsyncMock(
            return_value=SendMessageResult(success=True, message_id="om_xxx")
        )

        sender = FeishuSender(mock_client)
        result = await sender.send_text(
            receive_id="oc_xxx",
            text="Hello World",
        )

        assert result.success == True
        mock_client.send_text_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_markdown(self):
        """Test sending markdown message."""
        from derisk_ext.channels.feishu.sender import FeishuSender

        mock_client = MagicMock()
        mock_client.send_message = AsyncMock(
            return_value=SendMessageResult(success=True)
        )

        sender = FeishuSender(mock_client)
        result = await sender.send_markdown(
            receive_id="oc_xxx",
            title="Test Title",
            markdown_content="# Hello\n\nWorld",
        )

        assert result.success == True
        mock_client.send_message.assert_called_once()

        call_args = mock_client.send_message.call_args
        assert call_args.kwargs["msg_type"] == "post"


class TestFeishuChannelHandler:
    """Tests for FeishuChannelHandler."""

    def test_handler_initialization(self):
        """Test handler initialization."""
        from derisk_ext.channels.feishu.handler import FeishuChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = FeishuConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        try:
            handler = FeishuChannelHandler(
                channel_id="test_channel",
                config=config,
                platform_config=platform_config,
            )
            assert handler.channel_id == "test_channel"
            assert handler._platform_config is not None
        except ImportError:
            pytest.skip("lark-oapi SDK not installed")

    def test_get_capabilities(self):
        """Test getting capabilities."""
        from derisk_ext.channels.feishu.handler import FeishuChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = FeishuConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        try:
            handler = FeishuChannelHandler(
                channel_id="test_channel",
                config=config,
                platform_config=platform_config,
            )

            capabilities = handler.get_capabilities()
            assert capabilities.threads == True
            assert capabilities.reply == True
            assert "text" in capabilities.media
        except ImportError:
            pytest.skip("lark-oapi SDK not installed")

    def test_get_connection_url(self):
        """Test getting connection URL (should be None for WebSocket mode)."""
        from derisk_ext.channels.feishu.handler import FeishuChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = FeishuConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        try:
            handler = FeishuChannelHandler(
                channel_id="test_channel",
                config=config,
                platform_config=platform_config,
            )
            assert handler.get_connection_url() is None
        except ImportError:
            pytest.skip("lark-oapi SDK not installed")

    def test_parse_message_event(self):
        """Test parsing message event."""
        from derisk_ext.channels.feishu.handler import FeishuChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = FeishuConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        try:
            handler = FeishuChannelHandler(
                channel_id="test_channel",
                config=config,
                platform_config=platform_config,
            )

            message_event = FeishuMessageEvent(
                sender=FeishuSender(
                    sender_id={"open_id": "ou_user123"},
                    sender_type="user",
                ),
                message=FeishuMessage(
                    message_id="om_msg123",
                    chat_id="oc_chat123",
                    message_type="text",
                    content='{"text": "Hello World"}',
                    create_time="1234567890000",
                ),
            )

            channel_message = handler._parse_message_event(message_event)

            assert channel_message is not None
            assert channel_message.channel_type == ChannelType.FEISHU
            assert channel_message.message_id == "om_msg123"
            assert channel_message.conversation_id == "oc_chat123"
            assert "Hello World" in channel_message.content
        except ImportError:
            pytest.skip("lark-oapi SDK not installed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
