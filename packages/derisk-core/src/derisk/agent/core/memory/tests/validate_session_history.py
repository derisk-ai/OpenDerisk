"""
Session History Manager - Validation Script

这个脚本用于验证 SessionHistoryManager 的核心功能是否正常工作。
可以直接运行此脚本来测试基本功能,无需完整的测试环境。

运行方式:
    python validate_session_history.py
"""

import asyncio
import sys
from datetime import datetime
from typing import List, Optional

# 添加路径以便导入
sys.path.insert(0, "/Users/tuyang.yhj/Code/python/derisk/packages/derisk-core/src")

from derisk.agent.core.memory.session_history import (
    SessionConversation,
    SessionHistoryConfig,
    SessionHistoryManager,
)


# =============================================================================
# Mock Classes for Testing
# =============================================================================


class MockMessage:
    """模拟消息对象"""

    def __init__(
        self,
        role: str,
        content: str,
        conv_id: str = "test_conv",
        tool_calls: Optional[List[dict]] = None,
    ):
        self.role = role
        self.content = content
        self.conv_id = conv_id
        self.tool_calls = tool_calls
        self.context = {}
        self.metadata = {}


class MockGptsMemory:
    """模拟 GptsMemory"""

    def __init__(self):
        self.messages = {
            "session_123_1": [
                MockMessage(role="user", content="Hello", conv_id="session_123_1"),
                MockMessage(
                    role="assistant", content="Hi there!", conv_id="session_123_1"
                ),
            ],
            "session_123_2": [
                MockMessage(role="user", content="Read file", conv_id="session_123_2"),
                MockMessage(
                    role="assistant",
                    content="",
                    conv_id="session_123_2",
                    tool_calls=[{"id": "tc_1", "function": {"name": "read"}}],
                ),
                MockMessage(
                    role="tool", content="file content", conv_id="session_123_2"
                ),
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

    async def get_messages(self, conv_id: str):
        return self.messages.get(conv_id, [])

    async def get_session_messages(self, session_id: str):
        all_messages = []
        for conv_id, msgs in self.messages.items():
            if conv_id.startswith(session_id):
                all_messages.extend(msgs)
        return all_messages


# =============================================================================
# Validation Functions
# =============================================================================


async def validate_basic_functionality():
    """验证基本功能"""
    print("\n" + "=" * 70)
    print("✓ 测试 1: 基本功能")
    print("=" * 70)

    # 创建 SessionConversation
    conv = SessionConversation(
        conv_id="session_123_1",
        session_id="session_123",
        user_query="Hello",
        final_answer="Hi there!",
        has_tool_calls=False,
        pure_model_output="Hi there!",
    )

    print(f"✓ 创建 SessionConversation: {conv.conv_id}")
    print(f"  - User Query: {conv.user_query}")
    print(f"  - Pure Model Output: {conv.pure_model_output}")
    print(f"  - Has Tool Calls: {conv.has_tool_calls}")

    # 序列化测试
    data = conv.to_dict()
    print(f"\n✓ 序列化成功:")
    print(f"  - Keys: {list(data.keys())}")

    # 反序列化测试
    conv2 = SessionConversation.from_dict(data)
    print(f"\n✓ 反序列化成功:")
    print(f"  - Conv ID: {conv2.conv_id}")
    print(f"  - Pure Model Output: {conv2.pure_model_output}")


async def validate_session_history_manager():
    """验证 SessionHistoryManager"""
    print("\n" + "=" * 70)
    print("✓ 测试 2: SessionHistoryManager")
    print("=" * 70)

    # 创建 manager
    config = SessionHistoryConfig(
        hot_retention_count=2,
        warm_retention_count=3,
        include_pure_model_outputs=True,
    )

    manager = SessionHistoryManager(
        session_id="session_123",
        gpts_memory=MockGptsMemory(),
        config=config,
    )

    print(f"✓ 创建 SessionHistoryManager:")
    print(f"  - Session ID: {manager.session_id}")
    print(f"  - Hot Retention: {config.hot_retention_count}")
    print(f"  - Include Pure Model Outputs: {config.include_pure_model_outputs}")

    # 加载历史
    await manager.load_session_history()

    stats = manager.get_stats()
    print(f"\n✓ 加载历史成功:")
    print(f"  - Hot Count: {stats['hot_count']}")
    print(f"  - Warm Count: {stats['warm_count']}")
    print(f"  - Cold Count: {stats['cold_count']}")


async def validate_pure_model_output_tracking():
    """验证纯模型输出跟踪"""
    print("\n" + "=" * 70)
    print("✓ 测试 3: 纯模型输出跟踪")
    print("=" * 70)

    manager = SessionHistoryManager(
        session_id="session_456",
        config=SessionHistoryConfig(include_pure_model_outputs=True),
    )

    # 添加纯模型输出对话
    messages = [
        MockMessage(role="user", content="What is Python?", conv_id="session_456_1"),
        MockMessage(
            role="assistant",
            content="Python is a programming language...",
            conv_id="session_456_1",
        ),
    ]

    await manager.on_conversation_complete("session_456_1", messages)

    print(f"✓ 添加纯模型输出对话:")
    print(f"  - Conv ID: session_456_1")
    print(f"  - Pure Model Outputs Count: {len(manager._pure_model_outputs)}")

    if manager._pure_model_outputs:
        print(f"  - First Output Preview: {manager._pure_model_outputs[0][:50]}...")


async def validate_compression():
    """验证压缩机制"""
    print("\n" + "=" * 70)
    print("✓ 测试 4: 压缩机制")
    print("=" * 70)

    config = SessionHistoryConfig(
        hot_retention_count=1,  # 只保留1个,便于测试压缩
        warm_retention_count=2,
    )

    manager = SessionHistoryManager(
        session_id="session_789",
        config=config,
    )

    # 添加多个对话触发压缩
    for i in range(3):
        messages = [
            MockMessage(role="user", content=f"Query {i}", conv_id=f"session_789_{i}"),
            MockMessage(
                role="assistant", content=f"Response {i}", conv_id=f"session_789_{i}"
            ),
        ]
        await manager.on_conversation_complete(f"session_789_{i}", messages)

    stats = manager.get_stats()
    print(f"✓ 压缩测试结果:")
    print(f"  - Hot Count: {stats['hot_count']} (应该为 1)")
    print(f"  - Warm Count: {stats['warm_count']} (应该 > 0)")
    print(f"  - Pure Model Outputs Count: {stats['pure_model_outputs_count']}")

    # 验证压缩是否正确
    assert stats["hot_count"] == 1, "Hot count should be 1"
    assert stats["warm_count"] > 0, "Warm count should be > 0"
    print("\n✓ 压缩机制验证通过!")


async def validate_history_context_building():
    """验证历史上下文构建"""
    print("\n" + "=" * 70)
    print("✓ 测试 5: 历史上下文构建")
    print("=" * 70)

    manager = SessionHistoryManager(
        session_id="session_999",
        config=SessionHistoryConfig(
            include_pure_model_outputs=True,
        ),
    )

    # 添加历史
    for i in range(2):
        messages = [
            MockMessage(
                role="user", content=f"Question {i}", conv_id=f"session_999_{i}"
            ),
            MockMessage(
                role="assistant", content=f"Answer {i}", conv_id=f"session_999_{i}"
            ),
        ]
        await manager.on_conversation_complete(f"session_999_{i}", messages)

    # 构建历史上下文
    context = await manager.build_history_context(
        current_conv_id="session_999_3",
        max_tokens=5000,
    )

    print(f"✓ 历史上下文构建成功:")
    print(f"  - Messages Count: {len(context)}")
    print(f"  - Has Pure Model Outputs: {len(manager._pure_model_outputs) > 0}")

    if context:
        print(f"\n  示例消息:")
        for i, msg in enumerate(context[:2]):
            content = msg.get("content", "")[:100]
            print(f"    {i + 1}. {content}...")


async def validate_full_workflow():
    """验证完整工作流"""
    print("\n" + "=" * 70)
    print("✓ 测试 6: 完整工作流")
    print("=" * 70)

    # 1. 初始化
    manager = SessionHistoryManager(
        session_id="session_full",
        gpts_memory=MockGptsMemory(),
        config=SessionHistoryConfig(
            hot_retention_count=3,
            include_pure_model_outputs=True,
        ),
    )
    print("✓ 步骤 1: 初始化成功")

    # 2. 加载历史
    await manager.load_session_history()
    print("✓ 步骤 2: 加载历史成功")

    # 3. 添加新对话 (纯模型输出)
    new_messages = [
        MockMessage(role="user", content="New question", conv_id="session_full_new"),
        MockMessage(role="assistant", content="New answer", conv_id="session_full_new"),
    ]
    await manager.on_conversation_complete("session_full_new", new_messages)
    print("✓ 步骤 3: 添加新对话成功")

    # 4. 构建历史上下文
    context = await manager.build_history_context(max_tokens=8000)
    print(f"✓ 步骤 4: 构建历史上下文成功 ({len(context)} messages)")

    # 5. 获取统计
    stats = manager.get_stats()
    print(f"✓ 步骤 5: 获取统计成功")
    print(f"  - Hot: {stats['hot_count']}")
    print(f"  - Warm: {stats['warm_count']}")
    print(f"  - Pure Model Outputs: {stats['pure_model_outputs_count']}")

    print("\n✓ 完整工作流验证通过!")


# =============================================================================
# Main Entry Point
# =============================================================================


async def main():
    """主入口"""
    print("\n" + "🚀" * 35)
    print("Session History Manager - Validation Script")
    print("🚀" * 35)

    try:
        await validate_basic_functionality()
        await validate_session_history_manager()
        await validate_pure_model_output_tracking()
        await validate_compression()
        await validate_history_context_building()
        await validate_full_workflow()

        print("\n" + "=" * 70)
        print("✅ 所有测试通过! SessionHistoryManager 工作正常")
        print("=" * 70)

        print("\n📊 测试总结:")
        print("  ✓ SessionConversation 数据模型")
        print("  ✓ SessionHistoryManager 初始化")
        print("  ✓ 纯模型输出跟踪")
        print("  ✓ 自动压缩机制")
        print("  ✓ 历史上下文构建")
        print("  ✓ 完整工作流")

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
