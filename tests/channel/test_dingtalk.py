"""Unit tests for DingTalk channel implementation.

This module contains unit tests for:
- DingTalk client
- DingTalk sender
- DingTalk handler
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
from derisk.channel.schemas import DingTalkConfig

from derisk_ext.channels.dingtalk.models import (
    DingTalkEventType,
    DingTalkMessageContent,
    DingTalkMessageType,
)


class TestDingTalkModels:
    """Tests for DingTalk models."""

    def test_message_content(self):
        """Test DingTalkMessageContent model."""
        content = DingTalkMessageContent(
            content="Hello World",
            title="Test Title",
        )
        assert content.content == "Hello World"
        assert content.title == "Test Title"

    def test_event_type_enum(self):
        """Test DingTalkEventType enum."""
        assert DingTalkEventType.CHATBOT_MESSAGE.value == "chatbot_message"

    def test_message_type_enum(self):
        """Test DingTalkMessageType enum."""
        assert DingTalkMessageType.TEXT.value == "text"
        assert DingTalkMessageType.MARKDOWN.value == "markdown"


class TestDingTalkSender:
    """Tests for DingTalkSender."""

    @pytest.mark.asyncio
    async def test_send_text(self):
        """Test sending text message."""
        from derisk_ext.channels.dingtalk.sender import DingTalkSender

        mock_client = MagicMock()
        mock_client.send_private_message = AsyncMock(
            return_value=SendMessageResult(success=True, message_id="msg123")
        )

        sender = DingTalkSender(mock_client)
        result = await sender.send_text(
            user_id="user123",
            text="Hello World",
        )

        assert result.success == True
        mock_client.send_private_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_markdown(self):
        """Test sending markdown message."""
        from derisk_ext.channels.dingtalk.sender import DingTalkSender

        mock_client = MagicMock()
        mock_client.send_private_message = AsyncMock(
            return_value=SendMessageResult(success=True)
        )

        sender = DingTalkSender(mock_client)
        result = await sender.send_markdown(
            user_id="user123",
            title="Test Title",
            markdown_content="# Hello\n\nWorld",
        )

        assert result.success == True
        mock_client.send_private_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_action_card(self):
        """Test sending action card message."""
        from derisk_ext.channels.dingtalk.sender import DingTalkSender

        mock_client = MagicMock()
        mock_client.send_private_message = AsyncMock(
            return_value=SendMessageResult(success=True)
        )

        sender = DingTalkSender(mock_client)
        result = await sender.send_action_card(
            user_id="user123",
            title="Card Title",
            text="Card content",
            btns=[
                {"title": "Button 1", "actionURL": "https://example.com/1"},
                {"title": "Button 2", "actionURL": "https://example.com/2"},
            ],
        )

        assert result.success == True
        mock_client.send_private_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_group_message(self):
        """Test sending group message."""
        from derisk_ext.channels.dingtalk.sender import DingTalkSender

        mock_client = MagicMock()
        mock_client.send_group_message = AsyncMock(
            return_value=SendMessageResult(success=True)
        )

        sender = DingTalkSender(mock_client)
        result = await sender.send_text(
            user_id="user123",
            text="Hello Group",
            is_group=True,
            conversation_id="conv123",
        )

        assert result.success == True
        mock_client.send_group_message.assert_called_once()


class TestDingTalkChannelHandler:
    """Tests for DingTalkChannelHandler."""

    def test_handler_creation(self):
        """Test creating handler."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
        )

        assert handler.channel_id == "test_channel"
        assert handler._platform_config is not None

    def test_get_capabilities(self):
        """Test getting capabilities."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
        )

        capabilities = handler.get_capabilities()
        assert capabilities.threads == False
        assert capabilities.reply == True
        assert "text" in capabilities.media

    def test_get_connection_url(self):
        """Test getting connection URL (should be None for Stream mode)."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
        )

        assert handler.get_connection_url() is None

    def test_parse_chatbot_message_event(self):
        """Test parsing chatbot_message event."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
        )

        # ChatbotMessage format from DingTalkChatbotHandler
        event_dict = {
            "event_type": "chatbot_message",
            "message_id": "msg123",
            "conversation_id": "conv123",
            "conversation_type": "private",
            "conversation_title": None,
            "sender_id": "user_union_id",
            "sender_nick": "Test User",
            "sender_staff_id": "staff123",
            "sender_corp_id": "corp123",
            "robot_code": "robot123",
            "message_type": "text",
            "text": "Hello World",
            "at_users": [],
            "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
            "create_at": 1234567890000,
            "is_in_at_list": False,
        }

        channel_message = handler._parse_chatbot_message_event(event_dict)

        assert channel_message is not None
        assert channel_message.channel_type == ChannelType.DINGTALK
        assert channel_message.message_id == "msg123"
        assert channel_message.conversation_id == "conv123"
        assert channel_message.content == "Hello World"
        assert channel_message.is_group == False
        assert channel_message.sender.user_id == "staff123"
        assert channel_message.sender.name == "Test User"

    def test_parse_chatbot_message_event_group(self):
        """Test parsing chatbot_message event for group chat."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
        )

        # Group chat with @mention
        event_dict = {
            "event_type": "chatbot_message",
            "message_id": "msg456",
            "conversation_id": "conv456",
            "conversation_type": "group",
            "conversation_title": "Test Group",
            "sender_id": "user_union_id",
            "sender_nick": "Group User",
            "sender_staff_id": "staff456",
            "sender_corp_id": "corp123",
            "robot_code": "robot123",
            "message_type": "text",
            "text": " @机器人 你好",
            "at_users": [
                {"dingtalkId": "atuser1", "staffId": "staff1"}
            ],
            "session_webhook": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
            "create_at": 1234567890000,
            "is_in_at_list": True,
        }

        channel_message = handler._parse_chatbot_message_event(event_dict)

        assert channel_message is not None
        assert channel_message.is_group == True
        assert channel_message.mentions is not None
        assert "atuser1" in channel_message.mentions
        assert channel_message.extra.get("is_in_at_list") == True

    def test_on_message_received(self):
        """Test _on_message_received with chatbot_message event."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        received_messages = []

        def message_callback(msg):
            received_messages.append(msg)

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
            message_callback=message_callback,
        )

        event_dict = {
            "event_type": "chatbot_message",
            "message_id": "msg123",
            "conversation_id": "conv123",
            "conversation_type": "private",
            "sender_id": "user123",
            "sender_nick": "Test User",
            "sender_staff_id": "staff123",
            "text": "Test message",
            "create_at": 1234567890000,
        }

        handler._on_message_received(event_dict)

        assert len(received_messages) == 1
        assert received_messages[0].content == "Test message"

    def test_on_message_received_unknown_event(self):
        """Test _on_message_received with unknown event type."""
        from derisk_ext.channels.dingtalk.handler import DingTalkChannelHandler

        config = ChannelConfig(name="Test Channel", enabled=True)
        platform_config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        received_messages = []

        def message_callback(msg):
            received_messages.append(msg)

        handler = DingTalkChannelHandler(
            channel_id="test_channel",
            config=config,
            platform_config=platform_config,
            message_callback=message_callback,
        )

        # Unknown event type should not trigger callback
        event_dict = {
            "event_type": "unknown_event",
            "data": {"foo": "bar"},
        }

        handler._on_message_received(event_dict)

        assert len(received_messages) == 0


class TestDingTalkClient:
    """Tests for DingTalkClient."""

    @pytest.mark.asyncio
    async def test_get_access_token(self):
        """Test getting access token."""
        from derisk_ext.channels.dingtalk.client import DingTalkClient

        config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        client = DingTalkClient(config)

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "errcode": 0,
                "access_token": "test_token",
                "expires_in": 7200,
            }
            mock_get.return_value = mock_response

            token = await client._get_access_token()

            assert token == "test_token"
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_private_message(self):
        """Test sending private message."""
        from derisk_ext.channels.dingtalk.client import DingTalkClient

        config = DingTalkConfig(
            app_id="test_app_id",
            app_secret="test_secret",
        )

        client = DingTalkClient(config)

        with patch.object(
            client._http_client, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_token_response = MagicMock()
            mock_token_response.json.return_value = {
                "errcode": 0,
                "access_token": "test_token",
                "expires_in": 7200,
            }
            mock_get.return_value = mock_token_response

            with patch.object(
                client._http_client, "post", new_callable=AsyncMock
            ) as mock_post:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "processQueryKeys": ["key123"],
                }
                mock_post.return_value = mock_response

                msg = {
                    "msgKey": "sampleText",
                    "msgParam": json.dumps({"content": "Hello"}),
                }

                result = await client.send_private_message(
                    user_id="user123",
                    msg=msg,
                )

                assert result.success == True
                mock_post.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])