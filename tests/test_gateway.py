"""
单元测试 - Gateway控制平面

测试Gateway、Session、Message等
"""

import pytest
from derisk.agent.gateway.gateway import (
    Gateway,
    Session,
    SessionState,
    Message,
    get_gateway,
    init_gateway,
)


class TestSession:
    """Session测试"""

    def test_create_session(self):
        """测试创建Session"""
        session = Session(agent_name="primary")

        assert session.agent_name == "primary"
        assert session.state == SessionState.ACTIVE
        assert len(session.messages) == 0

    def test_add_message(self):
        """测试添加消息"""
        session = Session()

        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")

        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "Hello"

    def test_session_context(self):
        """测试Session上下文"""
        session = Session(agent_name="test", metadata={"key": "value"})

        context = session.get_context()

        assert context["agent_name"] == "test"
        assert context["state"] == SessionState.ACTIVE
        assert context["message_count"] == 0


class TestGateway:
    """Gateway测试"""

    @pytest.fixture
    def gateway(self):
        """创建Gateway"""
        return Gateway()

    @pytest.mark.asyncio
    async def test_create_session(self, gateway):
        """测试创建Session"""
        session = await gateway.create_session("primary")

        assert session is not None
        assert session.agent_name == "primary"
        assert session.state == SessionState.ACTIVE

        # 验证Session已存储
        retrieved = gateway.get_session(session.id)
        assert retrieved is not None

    def test_get_nonexistent_session(self, gateway):
        """测试获取不存在的Session"""
        session = gateway.get_session("nonexistent")
        assert session is None

    def test_list_sessions(self, gateway):
        """测试列出Sessions"""
        # 创建多个Session
        import asyncio

        async def create_sessions():
            await gateway.create_session("primary")
            await gateway.create_session("plan")

        asyncio.run(create_sessions())

        sessions = gateway.list_sessions()
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_close_session(self, gateway):
        """测试关闭Session"""
        session = await gateway.create_session("primary")

        await gateway.close_session(session.id)

        retrieved = gateway.get_session(session.id)
        assert retrieved.state == SessionState.CLOSED

    @pytest.mark.asyncio
    async def test_send_message(self, gateway):
        """测试发送消息"""
        session = await gateway.create_session("primary")

        await gateway.send_message(session.id, "user", "Hello")
        await gateway.send_message(session.id, "assistant", "Hi!")

        # 验证消息已添加
        retrieved = gateway.get_session(session.id)
        assert len(retrieved.messages) == 2

    def test_get_status(self, gateway):
        """测试获取状态"""
        status = gateway.get_status()

        assert "total_sessions" in status
        assert "active_sessions" in status
        assert "queue_size" in status


class TestMessage:
    """Message测试"""

    def test_create_message(self):
        """测试创建消息"""
        message = Message(
            type="test", session_id="session-1", content={"text": "Hello"}
        )

        assert message.type == "test"
        assert message.session_id == "session-1"
        assert message.content["text"] == "Hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
