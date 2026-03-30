"""
测试 Core_v2 架构的 VIS 推送功能

验证 Agent 内部的 _push_vis_message 方法能正确推送消息到 GptsMemory。
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from derisk.agent.core_v2.agent_base import AgentBase, AgentInfo, AgentContext
from derisk.agent.core_v2.enhanced_agent import (
    AgentBase as EnhancedAgentBase,
    AgentInfo as EnhancedAgentInfo,
    Decision,
    DecisionType,
    ActionResult,
)


class MockGptsMemory:
    """Mock GptsMemory for testing"""

    def __init__(self):
        self.pushed_messages = []
        self.call_count = 0

    async def push_message(
        self,
        conv_id: str,
        gpt_msg=None,
        stream_msg=None,
        is_first_chunk: bool = False,
        **kwargs,
    ):
        self.call_count += 1
        self.pushed_messages.append(
            {
                "conv_id": conv_id,
                "stream_msg": stream_msg,
                "is_first_chunk": is_first_chunk,
                "kwargs": kwargs,
            }
        )


class TestAgentBaseVISPush:
    """测试 agent_base.py 中的 VIS 推送功能"""

    def test_init_vis_state(self):
        """测试 VIS 状态初始化"""
        info = AgentInfo(name="test-agent", max_steps=10)
        agent = AgentBase(info)

        agent._init_vis_state("test-message-id", goal="test goal")

        assert agent._current_message_id == "test-message-id"
        assert agent._accumulated_content == ""
        assert agent._accumulated_thinking == ""
        assert agent._is_first_chunk == True
        assert agent._current_goal == "test goal"

    @pytest.mark.asyncio
    async def test_push_vis_message_without_gpts_memory(self):
        """测试没有 GptsMemory 时的 VIS 推送（应该跳过）"""
        info = AgentInfo(name="test-agent", max_steps=10)
        agent = AgentBase(info)

        # 不设置 GptsMemory
        agent._init_vis_state("test-message-id")

        # 推送应该静默跳过
        await agent._push_vis_message(thinking="test thinking")

        # 应该没有错误，只是跳过

    @pytest.mark.asyncio
    async def test_push_vis_message_with_gpts_memory(self):
        """测试有 GptsMemory 时的 VIS 推送"""
        info = AgentInfo(name="test-agent", max_steps=10)
        agent = AgentBase(info)

        # 设置 mock GptsMemory
        mock_memory = MockGptsMemory()
        agent.set_gpts_memory(mock_memory, conv_id="test-conv-id")
        agent._init_vis_state("test-message-id", goal="test goal")

        # 推送 thinking
        await agent._push_vis_message(
            thinking="test thinking",
            is_first_chunk=True,
        )

        # 验证调用
        assert mock_memory.call_count == 1
        assert mock_memory.pushed_messages[0]["conv_id"] == "test-conv-id"
        assert (
            mock_memory.pushed_messages[0]["stream_msg"]["thinking"] == "test thinking"
        )
        assert mock_memory.pushed_messages[0]["is_first_chunk"] == True

        # 验证状态累积
        assert agent._accumulated_thinking == "test thinking"

    @pytest.mark.asyncio
    async def test_push_vis_message_with_action_report(self):
        """测试带 action_report 的 VIS 推送"""
        info = AgentInfo(name="test-agent", max_steps=10)
        agent = AgentBase(info)

        # 设置 mock GptsMemory
        mock_memory = MockGptsMemory()
        agent.set_gpts_memory(mock_memory, conv_id="test-conv-id")
        agent._init_vis_state("test-message-id")

        # 构建 action_report
        action_report = agent._build_action_output(
            tool_name="bash",
            tool_args={"command": "ls"},
            result_content="file1.txt\nfile2.txt",
            action_id="call_bash_123",
            success=True,
        )

        # 推送
        await agent._push_vis_message(
            content="file1.txt\nfile2.txt",
            action_report=action_report,
        )

        # 验证
        assert mock_memory.call_count == 1
        assert "action_report" in mock_memory.pushed_messages[0]["stream_msg"]

    def test_build_action_output(self):
        """测试 ActionOutput 构建"""
        info = AgentInfo(name="test-agent", max_steps=10)
        agent = AgentBase(info)

        # Mock ActionOutput
        with patch("derisk.agent.core_v2.agent_base.ActionOutput") as MockActionOutput:
            mock_output = Mock()
            MockActionOutput.return_value = mock_output

            result = agent._build_action_output(
                tool_name="bash",
                tool_args={"command": "ls"},
                result_content="output",
                action_id="call_123",
                success=True,
            )

            # 验证 ActionOutput 被正确调用
            assert MockActionOutput.called
            call_kwargs = MockActionOutput.call_args[1]
            assert call_kwargs["action"] == "bash"
            assert call_kwargs["action_id"] == "call_123"
            assert call_kwargs["is_exe_success"] == True

    def test_build_tool_start_action_output(self):
        """测试工具开始时的 ActionOutput 构建"""
        info = AgentInfo(name="test-agent", max_steps=10)
        agent = AgentBase(info)

        with patch("derisk.agent.core_v2.agent_base.ActionOutput") as MockActionOutput:
            result = agent._build_tool_start_action_output(
                tool_name="bash",
                tool_args={"command": "ls"},
                action_id="call_123",
                thought="thinking...",
            )

            assert MockActionOutput.called
            call_kwargs = MockActionOutput.call_args[1]
            assert call_kwargs["state"] == "running"
            assert call_kwargs["stream"] == True


class TestEnhancedAgentBaseVISPush:
    """测试 enhanced_agent.py 中的 VIS 推送功能"""

    def test_set_gpts_memory(self):
        """测试设置 GptsMemory"""
        info = EnhancedAgentInfo(name="test-agent", max_steps=10)
        agent = EnhancedAgentBase(info)

        mock_memory = Mock()
        agent.set_gpts_memory(mock_memory, conv_id="conv-123", session_id="session-456")

        assert agent._gpts_memory == mock_memory
        assert agent._conv_id == "conv-123"
        assert agent._session_id == "session-456"

    def test_init_vis_state(self):
        """测试 VIS 状态初始化"""
        info = EnhancedAgentInfo(name="test-agent", max_steps=10)
        agent = EnhancedAgentBase(info)

        agent._init_vis_state("msg-123", goal="test goal")

        assert agent._current_message_id == "msg-123"
        assert agent._current_goal == "test goal"

    @pytest.mark.asyncio
    async def test_push_vis_message_integration(self):
        """测试 VIS 推送集成"""
        info = EnhancedAgentInfo(name="test-agent", max_steps=10)
        agent = EnhancedAgentBase(info)

        mock_memory = MockGptsMemory()
        agent.set_gpts_memory(mock_memory, conv_id="conv-123", session_id="session-456")
        agent._init_vis_state("msg-123")

        # 推送 thinking
        await agent._push_vis_message(thinking="thinking...", is_first_chunk=True)

        # 推送 content
        await agent._push_vis_message(content="response", status="complete")

        # 验证调用次数
        assert mock_memory.call_count == 2

        # 验证累积
        assert "thinking..." in agent._accumulated_thinking
        assert "response" in agent._accumulated_content


class TestVISPushInRun:
    """测试 VIS 推送在 Agent run() 方法中的集成"""

    @pytest.mark.asyncio
    async def test_vis_push_during_run(self):
        """测试 run() 方法中的 VIS 推送"""

        # 创建一个简单的测试 Agent
        class TestAgent(AgentBase):
            async def think(self, message: str, **kwargs):
                yield "thinking..."

            async def decide(self, message: str, **kwargs):
                return {"type": "response", "content": "test response"}

            async def act(self, tool_name: str, tool_args, **kwargs):
                return "result"

        info = AgentInfo(name="test-agent", max_steps=10)
        agent = TestAgent(info)

        # 设置 mock GptsMemory
        mock_memory = MockGptsMemory()
        agent.set_gpts_memory(mock_memory, conv_id="test-conv-id")

        # 运行
        chunks = []
        async for chunk in agent.run("test message"):
            chunks.append(chunk)

        # 验证 VIS 推送被调用
        assert mock_memory.call_count > 0

        # 验证推送了 thinking 和 content
        has_thinking = any(
            msg["stream_msg"] and msg["stream_msg"].get("thinking")
            for msg in mock_memory.pushed_messages
        )
        has_content = any(
            msg["stream_msg"] and msg["stream_msg"].get("content")
            for msg in mock_memory.pushed_messages
        )
        assert has_thinking or has_content


class TestRuntimeGptsMemoryInjection:
    """测试 Runtime 中 GptsMemory 注入"""

    @pytest.mark.asyncio
    async def test_gpts_memory_injection(self):
        """测试 GptsMemory 被正确注入到 Agent"""
        from derisk.agent.core_v2.integration.runtime import V2Runtime

        # 创建 runtime
        runtime = V2Runtime()
        runtime.gpts_memory = MockGptsMemory()

        # 注册一个简单的 agent factory
        async def agent_factory(context=None, **kwargs):
            info = AgentInfo(name="test-agent", max_steps=10)
            return AgentBase(info)

        runtime.register_agent_factory("test-agent", agent_factory)

        # 创建会话
        context = await runtime.create_session("test-agent")

        # 获取 agent
        agent = await runtime._get_or_create_agent(context, {})

        # 验证 GptsMemory 被注入
        assert hasattr(agent, "_gpts_memory")
        assert agent._gpts_memory == runtime.gpts_memory


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
