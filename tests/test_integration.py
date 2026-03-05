"""
端到端集成测试

测试完整的消息流：创建对话 -> 发送消息 -> 加载历史 -> 渲染展示
"""
import pytest
import asyncio
from datetime import datetime

from derisk.core.interface.unified_message import UnifiedMessage
from derisk.storage.unified_message_dao import UnifiedMessageDAO


class TestEndToEnd:
    """端到端集成测试"""
    
    @pytest.fixture
    async def dao(self):
        """DAO fixture"""
        dao = UnifiedMessageDAO()
        yield dao
    
    @pytest.mark.asyncio
    async def test_complete_message_flow(self, dao):
        """测试完整消息流"""
        conv_id = "test_conv_e2e_001"
        user_id = "test_user_001"
        
        try:
            await dao.create_conversation(
                conv_id=conv_id,
                user_id=user_id,
                goal="测试对话",
                chat_mode="chat_normal"
            )
            
            messages = [
                UnifiedMessage(
                    message_id=f"{conv_id}_msg_{i}",
                    conv_id=conv_id,
                    sender="user" if i % 2 == 0 else "assistant",
                    message_type="human" if i % 2 == 0 else "ai",
                    content=f"测试消息 {i}",
                    rounds=i // 2
                )
                for i in range(10)
            ]
            
            await dao.save_messages_batch(messages)
            
            loaded_messages = await dao.get_messages_by_conv_id(conv_id)
            
            assert len(loaded_messages) == 10
            assert loaded_messages[0].message_type == "human"
            assert loaded_messages[1].message_type == "ai"
            assert loaded_messages[0].content == "测试消息 0"
            
            latest = await dao.get_latest_messages(conv_id, limit=5)
            
            assert len(latest) == 5
            assert latest[-1].content == "测试消息 9"
            
            print(f"✅ 端到端测试通过：创建了{len(messages)}条消息，成功加载和查询")
            
        finally:
            try:
                await dao.delete_conversation(conv_id)
            except:
                pass
    
    @pytest.mark.asyncio
    async def test_core_v1_flow(self, dao):
        """测试Core V1流程"""
        from derisk.core.interface.message import HumanMessage, AIMessage
        
        conv_id = "test_conv_v1_001"
        
        try:
            await dao.create_conversation(
                conv_id=conv_id,
                user_id="user1",
                goal="Core V1测试",
                chat_mode="chat_normal"
            )
            
            human_msg = HumanMessage(content="你好")
            ai_msg = AIMessage(content="你好！有什么我可以帮助你的吗？")
            
            unified_human = UnifiedMessage.from_base_message(
                human_msg, conv_id, sender="user", round_index=0
            )
            unified_ai = UnifiedMessage.from_base_message(
                ai_msg, conv_id, sender="assistant", round_index=0
            )
            
            await dao.save_messages_batch([unified_human, unified_ai])
            
            loaded = await dao.get_messages_by_conv_id(conv_id)
            
            assert len(loaded) == 2
            
            restored_human = loaded[0].to_base_message()
            assert restored_human.type == "human"
            assert restored_human.content == "你好"
            
            print("✅ Core V1流程测试通过")
            
        finally:
            try:
                await dao.delete_conversation(conv_id)
            except:
                pass


class TestRenderingPerformance:
    """渲染性能测试"""
    
    @pytest.mark.asyncio
    async def test_large_conversation_rendering(self):
        """测试大对话渲染性能"""
        import time
        
        messages = [
            UnifiedMessage(
                message_id=f"msg_{i}",
                conv_id="large_conv",
                sender="user" if i % 2 == 0 else "assistant",
                message_type="human" if i % 2 == 0 else "ai",
                content=f"这是第{i}条消息，内容较长用于测试渲染性能。" * 10,
                rounds=i // 2
            )
            for i in range(100)
        ]
        
        start = time.time()
        markdown_lines = []
        for msg in messages:
            prefix = "**用户**" if msg.message_type == "human" else "**助手**"
            markdown_lines.append(f"{prefix}: {msg.content}\n")
        markdown = "\n".join(markdown_lines)
        render_time = time.time() - start
        
        assert render_time < 1.0
        assert len(markdown) > 0
        
        print(f"✅ 渲染{len(messages)}条消息耗时: {render_time*1000:.2f}ms")


class TestDataIntegrity:
    """数据完整性测试"""
    
    @pytest.mark.asyncio
    async def test_message_serialization(self):
        """测试消息序列化完整性"""
        msg = UnifiedMessage(
            message_id="msg_001",
            conv_id="conv_001",
            sender="user",
            message_type="human",
            content="测试序列化",
            thinking="思考过程",
            tool_calls=[{"name": "tool1", "args": {}}],
            rounds=0,
            metadata={"key": "value"}
        )
        
        msg_dict = msg.to_dict()
        
        assert "message_id" in msg_dict
        assert "thinking" in msg_dict
        assert "tool_calls" in msg_dict
        
        restored = UnifiedMessage.from_dict(msg_dict)
        
        assert restored.message_id == msg.message_id
        assert restored.content == msg.content
        assert restored.thinking == msg.thinking
        assert restored.tool_calls == msg.tool_calls
        
        print("✅ 消息序列化完整性测试通过")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始集成测试...")
    print("=" * 60 + "\n")
    
    tests = [
        ("端到端流程测试", TestEndToEnd().test_complete_message_flow),
        ("Core V1流程测试", TestEndToEnd().test_core_v1_flow),
        ("渲染性能测试", TestRenderingPerformance().test_large_conversation_rendering),
        ("数据完整性测试", TestDataIntegrity().test_message_serialization),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            print(f"\n运行: {name}...")
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                await test_func()
            passed += 1
            print(f"✅ {name} 通过")
        except Exception as e:
            failed += 1
            print(f"❌ {name} 失败: {e}")
    
    print("\n" + "=" * 60)
    print(f"测试完成: 通过 {passed} / {passed + failed}")
    print("=" * 60)
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = asyncio.run(run_all_tests())
    
    if failed > 0:
        exit(1)
    else:
        exit(0)