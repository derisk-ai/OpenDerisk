"""
Tests for Session History Manager (Layer 4 Compression)

测试第四层压缩机制的核心功能:
1. SessionConversation 数据模型
2. SessionHistoryManager 的分层存储
3. 纯模型输出处理
4. 历史上下文构建
5. 自动压缩和归档
"""

import asyncio
import pytest
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

from derisk.agent.core.memory.session_history import (
    SessionConversation,
    SessionHistoryConfig,
    SessionHistoryManager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def session_config():
    """创建测试配置"""
    return SessionHistoryConfig(
        hot_retention_count=2,  # 测试用较小的值
        warm_retention_count=3,
        cold_retention_days=7,
        max_hot_tokens=3000,
        max_warm_tokens=1500,
        include_pure_model_outputs=True,
        pure_model_max_length=500,
    )


@pytest.fixture
def mock_gpts_memory():
    """模拟 GptsMemory"""
    memory = AsyncMock()

    # 模拟消息数据
    messages_data = {
        "session_123_1": [
            MockMessage(role="user", content="Hello", conv_id="session_123_1"),
            MockMessage(role="assistant", content="Hi there!", conv_id="session_123_1"),
        ],
        "session_123_2": [
            MockMessage(role="user", content="Read file", conv_id="session_123_2"),
            MockMessage(
                role="assistant",
                content="",
                conv_id="session_123_2",
                tool_calls=[{"id": "tc_1", "function": {"name": "read"}}],
            ),
            MockMessage(role="tool", content="file content", conv_id="session_123_2"),
        ],
        "session_123_3": [
            MockMessage(
                role="user", content="What is Python?", conv_id="session_123_3"
            ),
            MockMessage(
                role="assistant",
                content="Python is a programming language...",
                conv_id="session_123_3",
            ),
        ],
    }

    async def get_messages(conv_id):
        return messages_data.get(conv_id, [])

    async def get_session_messages(session_id):
        all_messages = []
        for conv_id, msgs in messages_data.items():
            if conv_id.startswith(session_id):
                all_messages.extend(msgs)
        return all_messages

    memory.get_messages = get_messages
    memory.get_session_messages = get_session_messages

    return memory


class MockMessage:
    """模拟消息对象"""

    def __init__(
        self,
        role: str,
        content: str,
        conv_id: str = "test_conv",
        tool_calls: Optional[List[Dict]] = None,
    ):
        self.role = role
        self.content = content
        self.conv_id = conv_id
        self.tool_calls = tool_calls
        self.context = {}
        self.metadata = {}


# =============================================================================
# SessionConversation Tests
# =============================================================================


class TestSessionConversation:
    """测试 SessionConversation 数据模型"""

    def test_create_basic_conversation(self):
        """测试创建基本对话"""
        conv = SessionConversation(
            conv_id="session_123_1",
            session_id="session_123",
            user_query="Hello",
        )

        assert conv.conv_id == "session_123_1"
        assert conv.session_id == "session_123"
        assert conv.user_query == "Hello"
        assert conv.status == "active"
        assert not conv.has_tool_calls
        assert conv.pure_model_output is None

    def test_create_conversation_with_tools(self):
        """测试创建包含工具调用的对话"""
        conv = SessionConversation(
            conv_id="session_123_2",
            session_id="session_123",
            user_query="Read file",
            has_tool_calls=True,
        )

        assert conv.has_tool_calls
        assert conv.pure_model_output is None

    def test_create_pure_model_conversation(self):
        """测试创建纯模型输出对话"""
        conv = SessionConversation(
            conv_id="session_123_3",
            session_id="session_123",
            user_query="What is Python?",
            has_tool_calls=False,
            pure_model_output="Python is a programming language...",
        )

        assert not conv.has_tool_calls
        assert conv.pure_model_output is not None
        assert "Python" in conv.pure_model_output

    def test_serialization(self):
        """测试序列化和反序列化"""
        conv = SessionConversation(
            conv_id="session_123_1",
            session_id="session_123",
            user_query="Test query",
            final_answer="Test answer",
            has_tool_calls=False,
            pure_model_output="Pure model response",
        )

        # 序列化
        data = conv.to_dict()
        assert data["conv_id"] == "session_123_1"
        assert data["pure_model_output"] == "Pure model response"

        # 反序列化
        conv2 = SessionConversation.from_dict(data)
        assert conv2.conv_id == conv.conv_id
        assert conv2.pure_model_output == conv.pure_model_output


# =============================================================================
# SessionHistoryManager Tests
# =============================================================================


class TestSessionHistoryManager:
    """测试 SessionHistoryManager"""

    @pytest.mark.asyncio
    async def test_initialization(self, session_config):
        """测试初始化"""
        manager = SessionHistoryManager(
            session_id="session_123",
            config=session_config,
        )

        assert manager.session_id == "session_123"
        assert len(manager.hot_conversations) == 0
        assert len(manager.warm_summaries) == 0
        assert len(manager.cold_archive_refs) == 0

    @pytest.mark.asyncio
    async def test_load_session_history(self, session_config, mock_gpts_memory):
        """测试加载会话历史"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        await manager.load_session_history()

        # 验证分层加载
        assert len(manager.hot_conversations) == 2  # hot_retention_count=2
        assert len(manager.warm_summaries) == 1  # 第3个对话
        assert len(manager.cold_archive_refs) == 0

    @pytest.mark.asyncio
    async def test_build_session_conversation_pure_model(
        self, session_config, mock_gpts_memory
    ):
        """测试构建纯模型输出对话"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        # 模拟纯模型输出的消息
        messages = [
            MockMessage(
                role="user", content="What is Python?", conv_id="session_123_3"
            ),
            MockMessage(
                role="assistant",
                content="Python is a programming language...",
                conv_id="session_123_3",
            ),
        ]

        conv = await manager._build_session_conversation("session_123_3", messages)

        # 验证纯模型输出被正确识别和记录
        assert not conv.has_tool_calls
        assert conv.pure_model_output is not None
        assert "Python" in conv.pure_model_output
        assert conv.user_query == "What is Python?"

    @pytest.mark.asyncio
    async def test_build_session_conversation_with_tools(
        self, session_config, mock_gpts_memory
    ):
        """测试构建包含工具调用的对话"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        # 模拟包含工具调用的消息
        messages = [
            MockMessage(role="user", content="Read file", conv_id="session_123_2"),
            MockMessage(
                role="assistant",
                content="",
                conv_id="session_123_2",
                tool_calls=[{"id": "tc_1", "function": {"name": "read"}}],
            ),
            MockMessage(role="tool", content="file content", conv_id="session_123_2"),
        ]

        conv = await manager._build_session_conversation("session_123_2", messages)

        # 验证工具调用被正确识别
        assert conv.has_tool_calls
        assert conv.pure_model_output is None

    @pytest.mark.asyncio
    async def test_on_conversation_complete_pure_model(
        self, session_config, mock_gpts_memory
    ):
        """测试对话完成时保存纯模型输出"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        # 模拟纯模型输出的对话
        messages = [
            MockMessage(role="user", content="Hello", conv_id="session_123_new"),
            MockMessage(
                role="assistant", content="Hi there!", conv_id="session_123_new"
            ),
        ]

        await manager.on_conversation_complete("session_123_new", messages)

        # 验证纯模型输出被记录
        assert len(manager._pure_model_outputs) == 1
        assert "Hi there!" in manager._pure_model_outputs[0]

        # 验证对话被加入热数据区
        assert "session_123_new" in manager.hot_conversations

    @pytest.mark.asyncio
    async def test_compression_trigger(self, session_config, mock_gpts_memory):
        """测试压缩触发机制"""
        # 使用更小的配置值便于测试
        config = SessionHistoryConfig(
            hot_retention_count=1,  # 只保留1个热数据
            warm_retention_count=2,
        )

        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=config,
        )

        # 添加第1个对话
        messages1 = [
            MockMessage(role="user", content="Query 1", conv_id="session_123_1"),
            MockMessage(
                role="assistant", content="Response 1", conv_id="session_123_1"
            ),
        ]
        await manager.on_conversation_complete("session_123_1", messages1)

        # 添加第2个对话 (应触发压缩)
        messages2 = [
            MockMessage(role="user", content="Query 2", conv_id="session_123_2"),
            MockMessage(
                role="assistant", content="Response 2", conv_id="session_123_2"
            ),
        ]
        await manager.on_conversation_complete("session_123_2", messages2)

        # 验证压缩
        assert len(manager.hot_conversations) == 1  # 只有最新的
        assert len(manager.warm_summaries) == 1  # 第1个被压缩
        assert "session_123_1" in manager.warm_summaries

    @pytest.mark.asyncio
    async def test_build_history_context(self, session_config, mock_gpts_memory):
        """测试构建历史上下文"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        # 加载历史
        await manager.load_session_history()

        # 添加一些纯模型输出
        manager._pure_model_outputs = [
            "Previous model response 1",
            "Previous model response 2",
        ]

        # 构建历史上下文
        context = await manager.build_history_context(
            current_conv_id="session_123_4",
            max_tokens=5000,
        )

        # 验证上下文包含历史消息
        assert len(context) > 0

        # 验证包含纯模型输出
        pure_outputs_found = False
        for msg in context:
            if "历史纯模型输出" in msg.get("content", ""):
                pure_outputs_found = True
                break

        assert pure_outputs_found, "历史上下文应包含纯模型输出"

    @pytest.mark.asyncio
    async def test_format_conversation_summary(self, session_config):
        """测试格式化对话摘要"""
        manager = SessionHistoryManager(
            session_id="session_123",
            config=session_config,
        )

        # 创建一个压缩过的对话
        conv = SessionConversation(
            conv_id="session_123_1",
            session_id="session_123",
            user_query="Test query",
            summary="This is a test summary",
            has_tool_calls=False,
            pure_model_output="Pure model response",
        )

        summary = manager._format_conversation_summary(conv)

        assert len(summary) > 0
        assert "历史对话摘要" in summary[0]["content"]
        assert "纯模型输出" in summary[0]["content"]

    @pytest.mark.asyncio
    async def test_get_stats(self, session_config, mock_gpts_memory):
        """测试获取统计信息"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        await manager.load_session_history()

        stats = manager.get_stats()

        assert stats["session_id"] == "session_123"
        assert stats["hot_count"] == 2
        assert stats["warm_count"] == 1
        assert "pure_model_outputs_count" in stats


# =============================================================================
# Integration Tests
# =============================================================================


class TestSessionHistoryIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, session_config, mock_gpts_memory):
        """测试完整工作流"""
        manager = SessionHistoryManager(
            session_id="session_123",
            gpts_memory=mock_gpts_memory,
            config=session_config,
        )

        # 1. 加载历史
        await manager.load_session_history()
        assert len(manager.hot_conversations) > 0

        # 2. 添加新对话 (纯模型输出)
        new_messages = [
            MockMessage(role="user", content="New query", conv_id="session_123_new"),
            MockMessage(
                role="assistant", content="New response", conv_id="session_123_new"
            ),
        ]
        await manager.on_conversation_complete("session_123_new", new_messages)

        # 3. 验证纯模型输出被记录
        assert len(manager._pure_model_outputs) > 0

        # 4. 构建历史上下文
        context = await manager.build_history_context(max_tokens=5000)
        assert len(context) > 0

        # 5. 检查统计
        stats = manager.get_stats()
        assert stats["hot_count"] > 0

    @pytest.mark.asyncio
    async def test_pure_model_output_tracking(self, session_config):
        """测试纯模型输出跟踪"""
        manager = SessionHistoryManager(
            session_id="session_123",
            config=session_config,
        )

        # 添加多个纯模型输出对话
        for i in range(3):
            messages = [
                MockMessage(
                    role="user", content=f"Query {i}", conv_id=f"session_123_{i}"
                ),
                MockMessage(
                    role="assistant",
                    content=f"Response {i}",
                    conv_id=f"session_123_{i}",
                ),
            ]
            await manager.on_conversation_complete(f"session_123_{i}", messages)

        # 验证所有纯模型输出被记录
        assert len(manager._pure_model_outputs) == 3

        # 验证对话都被标记为纯模型输出
        for conv in manager.hot_conversations.values():
            assert not conv.has_tool_calls
            assert conv.pure_model_output is not None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
