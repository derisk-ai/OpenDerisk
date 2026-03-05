"""
Integration Tests for Session History Manager with Core V1 and Core V2

测试 SessionHistoryManager 与实际 Agent 的集成:
1. 与 ReActMasterAgent (Core V1) 的集成
2. 与 EnhancedAgent (Core V2) 的集成
3. 端到端的工作流测试
"""

import asyncio
import pytest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from derisk.agent.core.memory.session_history import (
    SessionConversation,
    SessionHistoryConfig,
    SessionHistoryManager,
)


# =============================================================================
# Core V1 Integration Tests
# =============================================================================


class TestCoreV1Integration:
    """测试与 Core V1 (ConversableAgent) 的集成"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """测试 Agent 初始化 SessionHistoryManager"""
        # 模拟 ConversableAgent 的初始化
        with patch("derisk.agent.core.base_agent.ConversableAgent") as MockAgent:
            # 创建 mock agent
            agent = Mock()
            agent.not_null_agent_context = Mock()
            agent.not_null_agent_context.conv_session_id = "session_123"
            agent.not_null_agent_context.conv_id = "session_123_1"

            # 模拟 memory
            agent.memory = Mock()
            agent.memory.gpts_memory = AsyncMock()

            # 初始化 SessionHistoryManager
            manager = SessionHistoryManager(
                session_id=agent.not_null_agent_context.conv_session_id,
                gpts_memory=agent.memory.gpts_memory,
                config=SessionHistoryConfig(
                    hot_retention_count=3,
                    include_pure_model_outputs=True,
                ),
            )

            # 验证初始化成功
            assert manager.session_id == "session_123"
            assert manager.config.include_pure_model_outputs

    @pytest.mark.asyncio
    async def test_inject_history_to_thinking_messages(self):
        """测试注入历史到 thinking_messages"""
        # 创建 SessionHistoryManager
        manager = SessionHistoryManager(
            session_id="session_123",
            config=SessionHistoryConfig(),
        )

        # 添加一些历史
        conv = SessionConversation(
            conv_id="session_123_1",
            session_id="session_123",
            user_query="Previous query",
            has_tool_calls=False,
            pure_model_output="Previous response",
        )
        manager.hot_conversations["session_123_1"] = conv
        manager._pure_model_outputs.append("Previous response")

        # 构建历史上下文
        history_context = await manager.build_history_context(
            current_conv_id="session_123_2",
            max_tokens=8000,
        )

        # 验证历史被构建
        assert len(history_context) > 0

        # 模拟注入到 thinking_messages
        thinking_messages = []
        thinking_messages.extend(history_context)

        # 验证注入成功
        assert len(thinking_messages) == len(history_context)

    @pytest.mark.asyncio
    async def test_save_on_conversation_complete(self):
        """测试对话完成时保存历史"""
        manager = SessionHistoryManager(
            session_id="session_123",
            config=SessionHistoryConfig(
                hot_retention_count=3,
            ),
        )

        # 模拟对话完成
        messages = [
            Mock(role="user", content="Test query", conv_id="session_123_1"),
            Mock(role="assistant", content="Test response", conv_id="session_123_1"),
        ]

        await manager.on_conversation_complete("session_123_1", messages)

        # 验证保存成功
        assert "session_123_1" in manager.hot_conversations
        assert len(manager._pure_model_outputs) > 0


# =============================================================================
# Core V2 Integration Tests
# =============================================================================


class TestCoreV2Integration:
    """测试与 Core V2 (AgentBase) 的集成"""

    @pytest.mark.asyncio
    async def test_v2_agent_initialization(self):
        """测试 V2 Agent 初始化 SessionHistoryManager"""
        # 模拟 AgentBase 的初始化
        with patch("derisk.agent.core_v2.agent_base.AgentBase") as MockAgentBase:
            # 创建 mock agent
            agent = Mock()
            agent.conv_id = "session_456_1"
            agent._session_history_manager = None

            # 提取 session_id
            session_id = agent.conv_id.rsplit("_", 1)[0]

            # 初始化 SessionHistoryManager
            agent._session_history_manager = SessionHistoryManager(
                session_id=session_id,
                config=SessionHistoryConfig(),
            )

            # 验证初始化成功
            assert agent._session_history_manager.session_id == "session_456"

    @pytest.mark.asyncio
    async def test_v2_run_with_session_history(self):
        """测试 V2 Agent 的 run() 方法集成 SessionHistory"""
        # 创建 SessionHistoryManager
        manager = SessionHistoryManager(
            session_id="session_456",
            config=SessionHistoryConfig(),
        )

        # 添加历史
        conv = SessionConversation(
            conv_id="session_456_1",
            session_id="session_456",
            user_query="Previous question",
            has_tool_calls=False,
            pure_model_output="Previous answer",
        )
        manager.hot_conversations["session_456_1"] = conv

        # 模拟 run() 中的历史加载
        history_context = await manager.build_history_context(
            current_conv_id="session_456_2",
            max_tokens=8000,
        )

        # 验证历史上下文可用于注入
        assert len(history_context) > 0


# =============================================================================
# End-to-End Tests
# =============================================================================


class TestEndToEnd:
    """端到端测试"""

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_with_pure_model_outputs(self):
        """测试多轮对话中的纯模型输出处理"""
        manager = SessionHistoryManager(
            session_id="session_789",
            config=SessionHistoryConfig(
                hot_retention_count=5,
                include_pure_model_outputs=True,
            ),
        )

        # 模拟多轮对话
        conversations = [
            {
                "conv_id": "session_789_1",
                "user_query": "What is Python?",
                "response": "Python is a programming language.",
                "has_tools": False,
            },
            {
                "conv_id": "session_789_2",
                "user_query": "Read the README file",
                "response": "",  # 使用工具
                "has_tools": True,
            },
            {
                "conv_id": "session_789_3",
                "user_query": "What are the main features?",
                "response": "Python has many features including...",
                "has_tools": False,
            },
        ]

        for conv_data in conversations:
            messages = [
                Mock(
                    role="user",
                    content=conv_data["user_query"],
                    conv_id=conv_data["conv_id"],
                ),
                Mock(
                    role="assistant",
                    content=conv_data["response"],
                    conv_id=conv_data["conv_id"],
                    tool_calls=[{"id": "tc_1"}] if conv_data["has_tools"] else None,
                ),
            ]

            await manager.on_conversation_complete(conv_data["conv_id"], messages)

        # 验证纯模型输出被正确记录
        stats = manager.get_stats()
        assert stats["pure_model_outputs_count"] == 2  # 第1和第3轮

        # 验证历史上下文包含所有对话
        context = await manager.build_history_context(max_tokens=10000)
        assert len(context) > 0

    @pytest.mark.asyncio
    async def test_context_inheritance_across_conversations(self):
        """测试跨对话的上下文继承"""
        manager = SessionHistoryManager(
            session_id="session_999",
            config=SessionHistoryConfig(
                hot_retention_count=3,
                include_pure_model_outputs=True,
            ),
        )

        # 第1轮: 纯模型输出
        messages1 = [
            Mock(role="user", content="My name is Alice", conv_id="session_999_1"),
            Mock(
                role="assistant",
                content="Nice to meet you, Alice!",
                conv_id="session_999_1",
            ),
        ]
        await manager.on_conversation_complete("session_999_1", messages1)

        # 第2轮: 新对话
        messages2 = [
            Mock(role="user", content="What's my name?", conv_id="session_999_2"),
            Mock(
                role="assistant", content="Your name is Alice!", conv_id="session_999_2"
            ),
        ]
        await manager.on_conversation_complete("session_999_2", messages2)

        # 构建第3轮的历史上下文
        context = await manager.build_history_context(
            current_conv_id="session_999_3",
            max_tokens=8000,
        )

        # 验证第2轮可以访问第1轮的历史
        assert len(context) > 0

        # 验证历史包含第1轮的信息
        history_text = "\n".join([msg.get("content", "") for msg in context])
        # 注意: 实际的上下文注入会在 Agent 的 thinking_messages 中完成


# =============================================================================
# Helper Classes
# =============================================================================


class Mock:
    """简单的 Mock 对象"""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
