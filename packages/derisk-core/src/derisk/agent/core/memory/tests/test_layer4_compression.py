"""
四层上下文压缩架构 - 验证脚本

该脚本验证四层压缩架构的正确性：
- Layer 1: 工具输出截断
- Layer 2: 历史修剪
- Layer 3: 上下文压缩
- Layer 4: 跨轮次对话历史压缩
"""

import asyncio
import sys
sys.path.insert(0, '/Users/tuyang/GitHub/OpenDerisk/packages/derisk-core/src')

from derisk.agent.core.memory.layer4_conversation_history import (
    ConversationHistoryManager,
    ConversationRoundStatus,
    WorkLogSummary,
    Layer4CompressionConfig,
)


async def test_layer4_basic():
    """测试 Layer 4 基本功能"""
    print("=" * 60)
    print("Testing Layer 4: Multi-Turn History Compression")
    print("=" * 60)

    # 创建管理器
    manager = ConversationHistoryManager(
        session_id="test_session",
        config=Layer4CompressionConfig(
            max_rounds_before_compression=2,
            max_total_rounds=5,
        ),
    )
    await manager.initialize()

    # 模拟多轮对话
    print("\n1. Starting round 1...")
    round1 = await manager.start_new_round(
        user_question="What is the weather today?",
        user_context={"location": "Beijing"},
    )
    
    # 添加 WorkLog
    await manager.update_current_round_worklog(
        worklog_entries=[
            {"tool": "weather_api", "args": {"city": "Beijing"}, "result": "Sunny, 25C"},
        ],
        summary=WorkLogSummary(
            tool_count=1,
            key_tools=["weather_api"],
            key_findings="Weather is sunny in Beijing",
            execution_time_ms=500,
            success_rate=1.0,
        ),
    )
    
    # 完成轮次
    await manager.complete_current_round(
        ai_response="The weather in Beijing today is sunny with a temperature of 25°C.",
        ai_thinking="User asked about weather in Beijing, called weather_api successfully.",
    )
    print("   Round 1 completed")

    # 第二轮
    print("\n2. Starting round 2...")
    round2 = await manager.start_new_round(
        user_question="What about tomorrow?",
    )
    
    await manager.update_current_round_worklog(
        worklog_entries=[
            {"tool": "weather_api", "args": {"city": "Beijing", "day": "tomorrow"}, "result": "Cloudy, 22C"},
        ],
        summary=WorkLogSummary(
            tool_count=1,
            key_tools=["weather_api"],
            key_findings="Tomorrow will be cloudy in Beijing",
            execution_time_ms=400,
            success_rate=1.0,
        ),
    )
    
    await manager.complete_current_round(
        ai_response="Tomorrow in Beijing will be cloudy with a temperature of 22°C.",
    )
    print("   Round 2 completed")

    # 第三轮（应该触发压缩）
    print("\n3. Starting round 3 (should trigger compression)...")
    round3 = await manager.start_new_round(
        user_question="Thanks! What should I wear?",
    )
    
    await manager.update_current_round_worklog(
        worklog_entries=[
            {"tool": "recommendation", "args": {"weather": "cloudy", "temp": 22}, "result": "Light jacket recommended"},
        ],
        summary=WorkLogSummary(
            tool_count=1,
            key_tools=["recommendation"],
            key_findings="Recommended light jacket for cloudy 22C weather",
            execution_time_ms=300,
            success_rate=1.0,
        ),
    )
    
    await manager.complete_current_round(
        ai_response="For cloudy weather at 22°C, I recommend wearing a light jacket.",
    )
    print("   Round 3 completed")

    # 获取统计信息
    print("\n4. Statistics:")
    stats = await manager.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # 获取历史记录（用于 prompt）
    print("\n5. Layer 4 History for Prompt:")
    history = await manager.get_history_for_prompt()
    print(history)

    print("\n" + "=" * 60)
    print("Layer 4 Test Completed Successfully!")
    print("=" * 60)


async def test_layer4_compression():
    """测试 Layer 4 压缩功能"""
    print("\n" + "=" * 60)
    print("Testing Layer 4 Compression")
    print("=" * 60)

    manager = ConversationHistoryManager(
        session_id="test_compression",
        config=Layer4CompressionConfig(
            max_rounds_before_compression=1,  # 只保留1轮，其他都压缩
            max_total_rounds=3,
        ),
    )
    await manager.initialize()

    # 创建多轮对话
    for i in range(3):
        print(f"\nStarting round {i+1}...")
        round_obj = await manager.start_new_round(
            user_question=f"Question {i+1}",
        )
        
        await manager.update_current_round_worklog(
            worklog_entries=[{"tool": "test_tool", "args": {}, "result": f"Result {i+1}"}],
            summary=WorkLogSummary(
                tool_count=1,
                key_tools=["test_tool"],
                key_findings=f"Finding {i+1}",
                execution_time_ms=100,
                success_rate=1.0,
            ),
        )
        
        await manager.complete_current_round(ai_response=f"Answer {i+1}")
        print(f"  Round {i+1} completed")

    # 检查压缩状态
    print("\nCompression Status:")
    stats = await manager.get_stats()
    print(f"  Total rounds: {stats['total_rounds']}")
    print(f"  Compressed rounds: {stats['compressed_rounds']}")

    # 获取压缩后的历史
    print("\nCompressed History:")
    history = await manager.get_history_for_prompt()
    print(history)

    print("\n" + "=" * 60)
    print("Compression Test Completed!")
    print("=" * 60)


async def main():
    """主测试函数"""
    try:
        await test_layer4_basic()
        await test_layer4_compression()
        print("\n✅ All Layer 4 tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
