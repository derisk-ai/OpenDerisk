"""
测试统一记忆管理集成
"""
import asyncio
import pytest
from derisk.agent.core_v2.agent_base import AgentBase, AgentInfo, AgentContext
from derisk.agent.core_v2.memory_factory import create_agent_memory, InMemoryStorage
from derisk.agent.core_v2.unified_memory.base import MemoryType


class MockAgent(AgentBase):
    """测试用Agent"""
    
    async def think(self, message: str, **kwargs):
        yield f"思考: {message}"
    
    async def decide(self, message: str, **kwargs):
        return {"type": "response", "content": f"回复: {message}"}
    
    async def act(self, tool_name: str, tool_args, **kwargs):
        return f"执行工具: {tool_name}"


@pytest.mark.asyncio
async def test_agent_memory_initialization():
    """测试Agent记忆初始化"""
    info = AgentInfo(name="test-agent", max_steps=10)
    agent = MockAgent(info)
    
    assert agent._memory is None
    memory = agent.memory
    assert memory is not None
    assert isinstance(memory, InMemoryStorage)
    
    stats = memory.get_stats()
    assert stats["total_items"] == 0


@pytest.mark.asyncio
async def test_agent_memory_save_and_load():
    """测试Agent记忆保存和加载"""
    info = AgentInfo(name="test-agent", max_steps=10)
    agent = MockAgent(info)
    
    memory_id = await agent.save_memory(
        content="测试记忆内容",
        memory_type=MemoryType.WORKING,
        metadata={"test": True},
    )
    
    assert memory_id is not None
    
    messages = await agent.load_memory(
        query="测试",
        memory_types=[MemoryType.WORKING],
    )
    
    assert len(messages) > 0
    assert "测试记忆内容" in messages[0].content


@pytest.mark.asyncio
async def test_agent_conversation_history():
    """测试Agent对话历史"""
    info = AgentInfo(name="test-agent", max_steps=10)
    agent = MockAgent(info)
    
    agent.add_message("user", "你好")
    agent.add_message("assistant", "你好！有什么可以帮助你的吗？")
    agent.add_message("user", "帮我写个测试")
    
    await agent.save_memory(
        content="User: 你好\nAssistant: 你好！有什么可以帮助你的吗？",
        memory_type=MemoryType.WORKING,
    )
    
    history = await agent.get_conversation_history(max_messages=10)
    
    assert len(history) > 0


@pytest.mark.asyncio
async def test_agent_run_with_memory():
    """测试Agent运行时的记忆保存"""
    info = AgentInfo(name="test-agent", max_steps=10)
    agent = MockAgent(info)
    
    context = AgentContext(session_id="test-session")
    await agent.initialize(context)
    
    messages = []
    async for chunk in agent.run("测试消息"):
        messages.append(chunk)
    
    assert len(agent._messages) > 0
    
    memory_messages = await agent.load_memory()
    assert len(memory_messages) > 0


@pytest.mark.asyncio
async def test_persistent_memory_flag():
    """测试持久化记忆标志"""
    info = AgentInfo(name="test-agent", max_steps=10)
    
    agent_in_memory = MockAgent(info, use_persistent_memory=False)
    assert agent_in_memory._use_persistent_memory is False
    
    memory = create_agent_memory(
        agent_name="test",
        session_id="test-session",
        use_persistent=False,
    )
    assert isinstance(memory, InMemoryStorage)


def test_memory_factory_create_default():
    """测试MemoryFactory创建默认记忆"""
    from derisk.agent.core_v2.memory_factory import MemoryFactory
    
    memory = MemoryFactory.create_default(session_id="test-session")
    assert isinstance(memory, InMemoryStorage)
    assert memory.session_id == "test-session"


@pytest.mark.asyncio
async def test_in_memory_storage_operations():
    """测试内存存储操作"""
    storage = InMemoryStorage(session_id="test-session")
    
    memory_id = await storage.write(
        content="测试内容",
        memory_type=MemoryType.WORKING,
        metadata={"key": "value"},
    )
    assert memory_id is not None
    
    item = await storage.get_by_id(memory_id)
    assert item is not None
    assert item.content == "测试内容"
    
    updated = await storage.update(memory_id, content="更新后的内容")
    assert updated is True
    
    item = await storage.get_by_id(memory_id)
    assert item.content == "更新后的内容"
    
    deleted = await storage.delete(memory_id)
    assert deleted is True
    
    item = await storage.get_by_id(memory_id)
    assert item is None


@pytest.mark.asyncio
async def test_memory_consolidation():
    """测试记忆整合"""
    storage = InMemoryStorage(session_id="test-session")
    
    for i in range(5):
        await storage.write(
            content=f"工作记忆 {i}",
            memory_type=MemoryType.WORKING,
            metadata={"importance": 0.8},
        )
    
    result = await storage.consolidate(
        source_type=MemoryType.WORKING,
        target_type=MemoryType.EPISODIC,
        criteria={"min_importance": 0.5, "min_access_count": 0},
    )
    
    assert result.success is True
    assert result.items_consolidated > 0


if __name__ == "__main__":
    asyncio.run(test_agent_memory_initialization())
    asyncio.run(test_agent_memory_save_and_load())
    asyncio.run(test_agent_conversation_history())
    asyncio.run(test_agent_run_with_memory())
    asyncio.run(test_persistent_memory_flag())
    asyncio.run(test_in_memory_storage_operations())
    asyncio.run(test_memory_consolidation())
    test_memory_factory_create_default()
    print("All tests passed!")