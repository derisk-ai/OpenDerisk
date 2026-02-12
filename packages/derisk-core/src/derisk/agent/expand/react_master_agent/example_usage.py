"""
ReActMasterV3 Agent 使用示例

演示如何使用 ReActMasterV3Agent 及其 WorkLog 功能。
"""

import asyncio
from typing import Optional

# 注意：这里仅展示用法，实际使用时需要根据项目实际情况导入
from derisk.agent.expand.react_master_agent import (
    ReActMasterV3Agent,
    create_work_log_manager,
)


async def example_basic_usage():
    """
    基本使用示例
    """
    print("=== ReActMasterV3Agent 基本使用示例 ===\n")

    # 1. 创建 ReActMasterV3Agent
    agent = ReActMasterV3Agent(
        name="ReActMasterV3",
        context_window=128000,  # LLM 上下文窗口大小
        compaction_threshold_ratio=0.7,  # 压缩阈值（70%）
        # 继承自 V2 的所有特性
        enable_doom_loop_detection=True,  # 启用末日循环检测
        doom_loop_threshold=3,  # 连续 3 次相同调用触发检测
        enable_session_compaction=True,  # 启用会话压缩
        enable_output_truncation=True,  # 启用输出截断
        enable_history_pruning=True,  # 启用历史修剪
    )

    # 2. 初始化组件（通常会在 act() 时自动调用，也可以手动调用）
    await agent._initialize_components()

    print("✅ Agent 创建并初始化成功")

    # 3. 使用 Agent 执行任务（需要提供实际的消息和发送者）
    # 例如：
    # from derisk.agent import AgentMessage, ActionOutput
    # message = AgentMessage(
    #     message_id="msg_001",
    #     content="帮我分析一下这个项目的代码结构",
    #     role="user",
    # )
    # sender = agent  # 或其他 Agent 实例
    # result = await agent.act(message, sender)

    print("\n注意：实际使用时需要配置 LLM 和 Action 执行环境")

    # 4. 查询 WorkLog 统计信息
    stats = await agent.get_work_log_stats()
    print(f"\n📊 WorkLog 统计:")
    print(f"  - 总条目数: {stats.get('total_entries', 0)}")
    print(f"  - 活跃条目数: {stats.get('active_entries', 0)}")
    print(f"  - 压缩摘要数: {stats.get('compressed_summaries', 0)}")
    print(f"  - 当前 Token 数: {stats.get('current_tokens', 0)}")
    print(f"  - 使用率: {stats.get('usage_ratio', 0):.2%}")

    # # 5. 获取 WorkLog 上下文（用于调试）
    # context = await agent.get_work_log_context(max_entries=20)
    # print(f"\n📝 WorkLog 上下文（前 20 条）:")
    # print(context)

    # 6. 获取完整 WorkLog
    # full_log = await agent.get_full_work_log()
    # print(f"\n📚 完整 WorkLog 包含 {len(full_log['work_log'])} 条日志和 {len(full_log['summaries'])} 个摘要")

    # 7. 清理
    await agent.cleanup()
    print("\n✅ 清理完成")


async def example_worklog_manager_standalone():
    """
    独立使用 WorkLogManager 的示例
    """
    print("\n=== WorkLogManager 独立使用示例 ===\n")

    # 创建 WorkLog 管理器
    from derisk.agent.expand.react_master_agent import (
        WorkLogManager,
        WorkEntry,
        WorkLogStatus,
    )

    # 可以不传递 AgentFileSystem，这时不会持久化文件
    work_log = WorkLogManager(
        agent_id="demo_agent",
        session_id="demo_session",
        agent_file_system=None,  # 可以为 None
        context_window_tokens=128000,
        compression_threshold_ratio=0.7,
    )

    # 初始化
    await work_log.initialize()
    print("✅ WorkLogManager 初始化成功")

    # 模拟记录一些动作
    from derisk.agent import ActionOutput

    for i in range(10):
        action_output = ActionOutput(
            action_id=f"action_{i}",
            name="TestAction",
            action="search",
            is_exe_success=True,
            content=f"这是第 {i} 次的搜索结果，包含一些返回数据。"
            * (i + 1),  # 模拟不同大小的结果
        )

        await work_log.record_action(
            tool_name="search",
            args={"query": f"query_{i}"},
            action_output=action_output,
            tags=["search", "test"],
        )

    print("✅ 记录了 10 条工作日志")

    # 查询统计
    stats = await work_log.get_stats()
    print(f"\n📊 统计信息:")
    print(f"  - 总条目: {stats['total_entries']}")
    print(f"  - 活跃条目: {stats['active_entries']}")
    print(f"  - Token 使用率: {stats['usage_ratio']:.2%}")

    # 获取上下文
    context = await work_log.get_context_for_prompt(max_entries=5)
    print(f"\n📝 前 5 条日志上下文:")
    print(context)

    # 清空日志
    # await work_log.clear()
    # print("\n✅ 日志已清空")


async def example_configuration():
    """
    配置示例
    """
    print("\n=== ReActMasterV3 配置示例 ===\n")

    # 示例 1：高性能配置（适合长任务）
    agent_high_perf = ReActMasterV3Agent(
        context_window=200000,  # 更大的上下文窗口
        compaction_threshold_ratio=0.8,  # 80% 时才压缩
        enable_doom_loop_detection=True,
        doom_loop_threshold=5,  # 更宽松的阈值
    )

    # 示例 2：资源友好配置（适合短任务）
    agent_friendly = ReActMasterV3Agent(
        context_window=64000,  # 较小的上下文窗口
        compaction_threshold_ratio=0.6,  # 60% 时就开始压缩
        enable_doom_loop_detection=True,
        doom_loop_threshold=3,
        enable_session_compaction=True,
        enable_output_truncation=True,
        enable_history_pruning=True,
    )

    # 示例 3：只使用 WorkLog，禁用其他特性
    agent_worklog_only = ReActMasterV3Agent(
        context_window=128000,
        compaction_threshold_ratio=0.7,
        # 禁用其他特性
        enable_doom_loop_detection=False,
        enable_session_compaction=False,
        enable_output_truncation=False,
        enable_history_pruning=False,
    )

    print("✅ 创建了三种不同配置的 Agent")


async def example_integrated_usage_with_filesystem():
    """
    集成 AgentFileSystem 的完整示例
    """
    print("\n=== 集成 AgentFileSystem 的完整示例 ===\n")

    # 注意：需要根据项目实际情况导入和配置 AgentFileSystem
    # from derisk.agent.expand.pdca_agent.agent_file_system import AgentFileSystem

    # # 1. 创建或获取 AgentFileSystem
    # afs = AgentFileSystem(
    #     conv_id="conversation_123",
    #     session_id="session_456",
    #     metadata_storage=None,  # 可选
    #     file_storage_client=None,  # 可选
    # )

    # # 2. 创建带文件系统的 WorkLog 管理器
    # work_log = await create_work_log_manager(
    #     agent_id="my_agent",
    #     session_id="session_456",
    #     agent_file_system=afs,
    #     context_window_tokens=128000,
    # )

    # print("✅ WorkLogManager（带文件系统）创建成功")

    # # 3. 记录动作（大结果会自动归档）
    # large_result_content = "这是一个很大的结果..." * 10000  # 模拟大结果
    #
    # action_output = ActionOutput(
    #     action_id="large_action",
    #     name="LargeAction",
    #     action="process_large_data",
    #     is_exe_success=True,
    #     content=large_result_content,
    # )

    # await work_log.record_action(
    #     tool_name="process_large_data",
    #     args={"data_size": "large"},
    #     action_output=action_output,
    #     tags=["large_output", "important"],
    # )

    # print("✅ 大结果已自动归档到文件系统")

    # # 4. 查询统计
    # stats = await work_log.get_stats()
    # print(f"💾 工作日志已持久化到文件系统")
    # print(f"   - 归档的大结果可以在文件系统中查看")

    print("（此示例需要配置实际的 AgentFileSystem）\n")


async def example_query_and_inspect():
    """
    查询和检查 WorkLog 的示例
    """
    print("\n=== WorkLog 查询和检查示例 ===\n")

    # 创建 Agent
    agent = ReActMasterV3Agent(
        context_window=128000,
        compaction_threshold_ratio=0.7,
    )

    await agent._initialize_components()
    await agent._ensure_work_log_manager()

    # 获取 Agent 的综合统计
    agent_stats = agent.get_stats()
    print(f"📊 Agent 综合统计:")
    print(f"  - 工具调用次数: {agent_stats.get('tool_call_count', 0)}")
    print(f"  - 压缩次数: {agent_stats.get('compaction_count', 0)}")
    print(f"  - 修剪次数: {agent_stats.get('prune_count', 0)}")
    print(
        f"  - WorkLog 初始化: {agent_stats.get('work_log', {}).get('initialized', False)}"
    )

    # 获取 WorkLog 详细统计
    work_log_stats = await agent.get_work_log_stats()
    print(f"\n📊 WorkLog 详细统计:")
    print(f"  - 总条目数: {work_log_stats.get('total_entries', 0)}")
    print(f"  - 活跃条目: {work_log_stats.get('active_entries', 0)}")
    print(f"  - 压缩摘要: {work_log_stats.get('compressed_summaries', 0)}")
    print(f"  - 当前 Token: {work_log_stats.get('current_tokens', 0)}")
    print(f"  - 压缩阈值: {work_log_stats.get('compression_threshold', 0)}")
    print(f"  - 使用率: {work_log_stats.get('usage_ratio', 0):.2%}")

    # 获取完整 WorkLog（包含摘要）
    # full_log = await agent.get_full_work_log()
    # print(f"\n📚 完整日志:")
    # print(f"  - 日志条目: {len(full_log['work_log'])} 条")
    # print(f"  - 压缩摘要: {len(full_log['summaries'])} 个")

    # if full_log['summaries']:
    #     print(f"\n  摘要示例（第一份）:")
    #     first_summary = full_log['summaries'][0]
    #     print(f"    - 压缩条目数: {first_summary['compressed_entries_count']}")
    #     print(f"    - 时间范围: {first_summary['time_range']}")
    #     print(f"    - 关键工具: {', '.join(first_summary['key_tools'][:5])}")

    await agent.cleanup()
    print("\n✅ 查询和检查完成")


async def main():
    """
    主函数：运行所有示例
    """
    print("╔════════════════════════════════════════════════════════╗")
    print("║     ReActMasterV3Agent 使用示例集合                    ║")
    print("╚════════════════════════════════════════════════════════╝\n")

    # 运行各个示例
    await example_basic_usage()
    await example_worklog_manager_standalone()
    await example_configuration()
    await example_integrated_usage_with_filesystem()
    await example_query_and_inspect()

    print("\n╔════════════════════════════════════════════════════════╗")
    print("║     所有示例运行完成                                  ║")
    print("╚════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
