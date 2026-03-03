"""
统一消息模块单元测试
"""
import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

from derisk.core.interface.unified_message import UnifiedMessage


class TestUnifiedMessage:
    """UnifiedMessage测试类"""
    
    def test_create_unified_message(self):
        """测试创建UnifiedMessage"""
        msg = UnifiedMessage(
            message_id="test_msg_1",
            conv_id="test_conv_1",
            sender="user",
            message_type="human",
            content="Hello",
            rounds=0
        )
        
        assert msg.message_id == "test_msg_1"
        assert msg.conv_id == "test_conv_1"
        assert msg.sender == "user"
        assert msg.message_type == "human"
        assert msg.content == "Hello"
        assert msg.rounds == 0
        assert msg.created_at is not None
    
    def test_from_base_message_human(self):
        """测试从HumanMessage转换"""
        from derisk.core.interface.message import HumanMessage
        
        base_msg = HumanMessage(content="Test message")
        base_msg.round_index = 1
        
        unified_msg = UnifiedMessage.from_base_message(
            msg=base_msg,
            conv_id="conv_1",
            sender="user",
            round_index=1
        )
        
        assert unified_msg.message_type == "human"
        assert unified_msg.content == "Test message"
        assert unified_msg.sender == "user"
        assert unified_msg.rounds == 1
        assert unified_msg.metadata["source"] == "core_v1"
    
    def test_from_base_message_ai(self):
        """测试从AIMessage转换"""
        from derisk.core.interface.message import AIMessage
        
        base_msg = AIMessage(content="AI response")
        base_msg.round_index = 1
        
        unified_msg = UnifiedMessage.from_base_message(
            msg=base_msg,
            conv_id="conv_1",
            sender="assistant",
            round_index=1
        )
        
        assert unified_msg.message_type == "ai"
        assert unified_msg.content == "AI response"
        assert unified_msg.sender == "assistant"
    
    def test_to_base_message(self):
        """测试转换为BaseMessage"""
        unified_msg = UnifiedMessage(
            message_id="msg_1",
            conv_id="conv_1",
            sender="user",
            message_type="human",
            content="Hello",
            rounds=0,
            metadata={"additional_kwargs": {}}
        )
        
        base_msg = unified_msg.to_base_message()
        
        assert base_msg.type == "human"
        assert base_msg.content == "Hello"
        assert hasattr(base_msg, 'round_index')
    
    def test_to_dict(self):
        """测试转换为字典"""
        unified_msg = UnifiedMessage(
            message_id="msg_1",
            conv_id="conv_1",
            sender="user",
            message_type="human",
            content="Test",
            rounds=1
        )
        
        msg_dict = unified_msg.to_dict()
        
        assert isinstance(msg_dict, dict)
        assert msg_dict["message_id"] == "msg_1"
        assert msg_dict["conv_id"] == "conv_1"
        assert msg_dict["content"] == "Test"
        assert "created_at" in msg_dict
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "message_id": "msg_1",
            "conv_id": "conv_1",
            "sender": "user",
            "message_type": "human",
            "content": "Test",
            "rounds": 1,
            "created_at": "2025-01-01T00:00:00"
        }
        
        unified_msg = UnifiedMessage.from_dict(data)
        
        assert unified_msg.message_id == "msg_1"
        assert unified_msg.conv_id == "conv_1"
        assert unified_msg.content == "Test"


class TestUnifiedMessageDAO:
    """UnifiedMessageDAO测试类"""
    
    @pytest.fixture
    def mock_gpts_messages_dao(self):
        """Mock GptsMessagesDao"""
        with patch('derisk.storage.unified_message_dao.GptsMessagesDao') as mock:
            yield mock
    
    @pytest.fixture
    def mock_gpts_conversations_dao(self):
        """Mock GptsConversationsDao"""
        with patch('derisk.storage.unified_message_dao.GptsConversationsDao') as mock:
            yield mock
    
    @pytest.mark.asyncio
    async def test_save_message(self, mock_gpts_messages_dao, mock_gpts_conversations_dao):
        """测试保存消息"""
        from derisk.storage.unified_message_dao import UnifiedMessageDAO
        
        dao = UnifiedMessageDAO()
        
        msg = UnifiedMessage(
            message_id="msg_1",
            conv_id="conv_1",
            sender="user",
            message_type="human",
            content="Hello"
        )
        
        await dao.save_message(msg)
        
        mock_gpts_messages_dao.return_value.update_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_messages_by_conv_id(self):
        """测试获取消息"""
        with patch('derisk.storage.unified_message_dao.GptsMessagesDao') as mock_dao:
            mock_entity = Mock()
            mock_entity.message_id = "msg_1"
            mock_entity.conv_id = "conv_1"
            mock_entity.sender = "user"
            mock_entity.content = "Hello"
            mock_entity.thinking = None
            mock_entity.tool_calls = None
            mock_entity.rounds = 0
            mock_entity.gmt_create = datetime.now()
            
            mock_dao.return_value.get_by_conv_id = AsyncMock(return_value=[mock_entity])
            
            from derisk.storage.unified_message_dao import UnifiedMessageDAO
            
            dao = UnifiedMessageDAO()
            messages = await dao.get_messages_by_conv_id("conv_1")
            
            assert len(messages) == 1
            assert messages[0].message_id == "msg_1"
            assert messages[0].conv_id == "conv_1"


class TestUnifiedStorageAdapter:
    """统一存储适配器测试"""
    
    @pytest.mark.asyncio
    async def test_storage_conv_adapter_save(self):
        """测试StorageConversation适配器保存"""
        from derisk.storage.unified_storage_adapter import StorageConversationUnifiedAdapter
        from derisk.core.interface.message import HumanMessage, AIMessage
        
        mock_storage_conv = Mock()
        mock_storage_conv.conv_uid = "conv_1"
        mock_storage_conv.user_name = "user1"
        mock_storage_conv.chat_mode = "chat_normal"
        mock_storage_conv.messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there")
        ]
        
        with patch('derisk.storage.unified_storage_adapter.UnifiedMessageDAO') as mock_dao:
            mock_dao.return_value.create_conversation = AsyncMock()
            mock_dao.return_value.save_messages_batch = AsyncMock()
            
            adapter = StorageConversationUnifiedAdapter(mock_storage_conv)
            await adapter.save_to_unified_storage()
            
            mock_dao.return_value.create_conversation.assert_called_once()
            mock_dao.return_value.save_messages_batch.assert_called_once()


class TestUnifiedAPI:
    """统一API测试"""
    
    @pytest.mark.asyncio
    async def test_get_conversation_messages_api(self):
        """测试获取消息API"""
        from fastapi.testclient import TestClient
        from derisk_serve.unified_api.endpoints import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router)
        
        client = TestClient(app)
        
        with patch('derisk_serve.unified_api.endpoints.get_unified_dao') as mock_get_dao:
            mock_dao = AsyncMock()
            mock_dao.get_messages_by_conv_id = AsyncMock(return_value=[])
            mock_get_dao.return_value = mock_dao
            
            response = client.get("/api/v1/unified/conversations/test_conv/messages")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_render_api(self):
        """测试渲染API"""
        from fastapi.testclient import TestClient
        from derisk_serve.unified_api.endpoints import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router)
        
        client = TestClient(app)
        
        with patch('derisk_serve.unified_api.endpoints.get_unified_dao') as mock_get_dao:
            mock_dao = AsyncMock()
            mock_dao.get_messages_by_conv_id = AsyncMock(return_value=[])
            mock_get_dao.return_value = mock_dao
            
            response = client.get(
                "/api/v1/unified/conversations/test_conv/render?render_type=markdown"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "data" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])