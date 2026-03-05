"""Unit tests for channel module.

This module contains unit tests for:
- Channel base types
- Channel handler registry
- Channel message router
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from derisk.channel import (
    ChannelCapabilities,
    ChannelConfig,
    ChannelConnectionState,
    ChannelHandler,
    ChannelHandlerRegistry,
    ChannelMessage,
    ChannelMessageRouter,
    ChannelSender,
    ChannelType,
    SendMessageResult,
)
from derisk.channel.router import AgentMessageHandler


class TestChannelTypes:
    """Tests for channel types and enums."""

    def test_channel_type_values(self):
        """Test that channel types have correct values."""
        assert ChannelType.DINGTALK == "dingtalk"
        assert ChannelType.FEISHU == "feishu"
        assert ChannelType.WECHAT == "wechat"
        assert ChannelType.QQ == "qq"

    def test_channel_connection_state_values(self):
        """Test connection state values."""
        assert ChannelConnectionState.DISCONNECTED == "disconnected"
        assert ChannelConnectionState.CONNECTING == "connecting"
        assert ChannelConnectionState.CONNECTED == "connected"
        assert ChannelConnectionState.ERROR == "error"
        assert ChannelConnectionState.RECONNECTING == "reconnecting"


class TestChannelModels:
    """Tests for channel models."""

    def test_channel_sender(self):
        """Test ChannelSender model."""
        sender = ChannelSender(
            user_id="user123",
            name="John Doe",
            avatar="https://example.com/avatar.png",
        )
        assert sender.user_id == "user123"
        assert sender.name == "John Doe"
        assert sender.avatar == "https://example.com/avatar.png"

    def test_channel_message(self):
        """Test ChannelMessage model."""
        message = ChannelMessage(
            channel_type=ChannelType.DINGTALK,
            message_id="msg123",
            sender=ChannelSender(user_id="user123"),
            content="Hello World",
        )
        assert message.channel_type == ChannelType.DINGTALK
        assert message.message_id == "msg123"
        assert message.content == "Hello World"
        assert message.content_type == "text"
        assert message.is_group == False

    def test_channel_capabilities(self):
        """Test ChannelCapabilities model."""
        caps = ChannelCapabilities(
            chat_types=["private", "group"],
            threads=True,
            media=["text", "image"],
        )
        assert "private" in caps.chat_types
        assert caps.threads == True
        assert "text" in caps.media

    def test_send_message_result(self):
        """Test SendMessageResult model."""
        result = SendMessageResult(
            success=True,
            message_id="msg456",
        )
        assert result.success == True
        assert result.message_id == "msg456"
        assert result.error is None


class TestChannelHandlerRegistry:
    """Tests for ChannelHandlerRegistry."""

    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = ChannelHandlerRegistry.get_instance()
        registry2 = ChannelHandlerRegistry.get_instance()
        assert registry1 is registry2

    def test_register_handler_class(self):
        """Test registering a handler class."""
        registry = ChannelHandlerRegistry.get_instance()

        class MockHandler(ChannelHandler):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send_message(
                self, receiver_id, content, content_type="text", **kwargs
            ):
                return SendMessageResult(success=True)

            def get_connection_url(self):
                return None

            async def process_message(self, channel_id, message):
                return None

            def validate_signature(self, channel_id, signature, timestamp, nonce, body):
                return True

            def get_capabilities(self):
                return ChannelCapabilities()

            async def test_connection(self, channel_id):
                return True

        registry.register_handler_class(ChannelType.FEISHU, MockHandler)
        assert ChannelType.FEISHU in registry.get_registered_types()

    def test_create_handler(self):
        """Test creating a handler instance."""
        registry = ChannelHandlerRegistry.get_instance()

        config = ChannelConfig(name="Test Channel", enabled=True)

        handler = registry.create_handler(
            channel_id="test_channel",
            channel_type=ChannelType.FEISHU,
            config=config,
        )

        assert handler is not None
        assert handler.channel_id == "test_channel"

    def test_get_capabilities_with_handler_class(self):
        """Test get_capabilities returns capabilities from handler class."""
        registry = ChannelHandlerRegistry.get_instance()

        class MockHandlerWithCapabilities(ChannelHandler):
            @classmethod
            def get_default_capabilities(cls):
                return ChannelCapabilities(
                    chat_types=["private"],
                    threads=True,
                    media=["text", "image"],
                    reactions=True,
                    edit=True,
                    reply=True,
                )

            async def start(self):
                pass

            async def stop(self):
                pass

            async def send_message(
                self, receiver_id, content, content_type="text", **kwargs
            ):
                return SendMessageResult(success=True)

            def get_connection_url(self):
                return None

            async def process_message(self, channel_id, message):
                return None

            def validate_signature(self, channel_id, signature, timestamp, nonce, body):
                return True

            def get_capabilities(self):
                return self.get_default_capabilities()

            async def test_connection(self, channel_id):
                return True

        registry.register_handler_class(ChannelType.WECHAT, MockHandlerWithCapabilities)

        capabilities = registry.get_capabilities(ChannelType.WECHAT)
        assert capabilities is not None
        assert "private" in capabilities.chat_types
        assert capabilities.threads is True
        assert "text" in capabilities.media

    def test_get_capabilities_unregistered_type(self):
        """Test get_capabilities returns None for unregistered type."""
        registry = ChannelHandlerRegistry.get_instance()

        # QQ is not registered
        capabilities = registry.get_capabilities(ChannelType.QQ)
        assert capabilities is None


class TestChannelMessageRouter:
    """Tests for ChannelMessageRouter."""

    @pytest.mark.asyncio
    async def test_router_start_stop(self):
        """Test starting and stopping the router."""
        router = ChannelMessageRouter()
        await router.start()
        assert router.is_running == True
        await router.stop()
        assert router.is_running == False

    @pytest.mark.asyncio
    async def test_message_handler_registration(self):
        """Test registering a message handler."""
        router = ChannelMessageRouter()

        handler = AgentMessageHandler(agent_app_code="test_agent")
        router.register_handler("channel1", handler)

        # Handler should be registered
        assert "channel1" in router._handlers

    @pytest.mark.asyncio
    async def test_default_handler(self):
        """Test setting default message handler."""
        router = ChannelMessageRouter()

        handler = AgentMessageHandler()
        router.set_default_handler(handler)

        assert router._default_handler is handler


class TestAgentMessageHandler:
    """Tests for AgentMessageHandler."""

    @pytest.mark.asyncio
    async def test_handle_message(self):
        """Test handling a message."""
        handler = AgentMessageHandler()

        message = ChannelMessage(
            channel_type=ChannelType.DINGTALK,
            message_id="msg1",
            sender=ChannelSender(user_id="user1"),
            content="Hello",
        )

        mock_channel_handler = MagicMock()
        mock_channel_handler.send_message = AsyncMock(
            return_value=SendMessageResult(success=True)
        )

        response = await handler.handle_message(message, mock_channel_handler)
        assert response is not None

    def test_conversation_management(self):
        """Test conversation history management."""
        handler = AgentMessageHandler()

        # Add some history
        handler._conversation_histories["conv1"] = [
            {"role": "user", "content": "Hello"},
        ]

        # Clear conversation
        handler.clear_conversation("conv1")
        assert "conv1" not in handler._conversation_histories

        # Add again
        handler._conversation_histories["conv2"] = []

        # Clear all
        handler.clear_all_conversations()
        assert len(handler._conversation_histories) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
