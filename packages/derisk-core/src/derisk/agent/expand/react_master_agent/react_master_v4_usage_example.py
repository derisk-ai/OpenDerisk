"""
ReActMasterAgentV4 使用示例

展示如何使用集成了 WorkLog、PhaseManager 和 ReportGenerator 的新 Agent。
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)


async def example_basic_usage():
    """
    基本使用示例

    展示如何创建和使用 ReActMasterAgentV4
    """
    print("=== ReActMasterAgentV4 基本使用示例 ===\n")

    from derisk.agent.expand.react_master_agent import ReActMasterAgentV4

    print("✅ 导入成功：ReActMasterAgentV4")
    print("   - 文件位置：react_master_agent/react_master_agent_v4.py")
    print("   - 继承自：ReActMasterAgent")
    print("   - 新增功能：WorkLog、PhaseManager、ReportGenerator\n")

    # 注意：实际使用需要配置环境
    print("实际使用示例：")
    print("=" * 50)
    print("""
from derisk.agent.expand.react_master_agent import ReActMasterAgentV4

# 创建 Agent（启用所有新功能）
agent = await ReActMasterAgentV4(
    # 现有特性
    enable_doom_loop_detection=True,
    doom_loop_threshold=3,
    enable_session_compaction=True,
    context_window=128000,
    enable_output_truncation=True,
    enable_history_pruning=True,
    
    # 新功能配置
    enable_work_log=True,
    work_log_compression_ratio=0.7,
    
    enable_phase_management=True,
    phase_auto_detection=True,
    
    enable_auto_report=True,
    report_default_type="detailed",
    report_default_format="markdown",
).bind(context).bind(llm_config).bind(agent_memory).bind(tools).build()

# 使用 Agent
result = await agent.act(message, sender)

# 自动功能（完全自动，无需手动调用）：
# ✅ 每次工具调用自动记录到 WorkLog
# ✅ WorkLog 自动压缩（超出 128000 tokens 时）
# ✅ 自动阶段切换
# ✅ 任务完成时自动生成并保存报告

# 手动查询功能：
from derisk.agent.expand.react_master_agent import ReActMasterV4

# 等同于 agent.get_work_log_stats()，但为了清晰展示：
await agent.get_work_log_stats()      # 查看 WorkLog 统计
await agent.get_work_log_context(50)     # 获取最近的上下文
agent.get_current_phase()                # 查看当前阶段
agent.set_phase("execution", "开始执行") # 手动切换阶段
await agent.generate_report("detailed", "md", True)  # 生成并保存报告
""")
    print("=" * 50)


async def example_manual_control():
    """
    手动控制示例

    展示如何手动查询和手动控制
    """
    print("\n=== 手动控制示例 ===\n")

    print("手动查询和控制：")
    print("-" * 40)
    print("""
# 1. 查询 WorkLog 状态
stats = await agent.get_work_log_stats()
print(f"总条目: {stats.get('total_entries', 0)}")
print(f"活跃条目: {stats.get('active_entries', 0)}")
print(f"压缩摘要数: {stats.get('compressed_summaries', 0)}")
print(f"Token 使用率: {stats.get('usage_ratio', 0):.1%}")

# 2. 获取 WorkLog 上下文（用于调试或注入到 prompt）
context = await agent.get_work_log_context(max_entries=20)
print("最近的 20 条操作:")
print(context)

# 3. 查看和使用阶段
phase = agent.get_current_phase()
print(f"当前阶段: {phase}")

# 手动切换阶段
agent.set_phase("execution", "开始执行具体任务")
agent.set_phase("reporting", "准备生成报告")
agent.set_phase("complete", "任务完成")

# 4. 手动生成报告
report = await agent.generate_report(
    report_type="detailed",      # summary/detailed/technical/executive/progress/final
    report_format="markdown",    # markdown/html/json/plain
    save_to_file=True,          # 是否保存到文件系统
)

# 保存报告到文件
with open("task_report.md", "w", encoding="utf-8") as f:
    f.write(report)
print("✅ 报告已保存到 task_report.md")
""")
    print("-" * 40)


async def example_configurations():
    """
    配置示例

    展示不同的配置选项
    """
    print("\n=== 配置示例 ===\n")

    print("不同的使用场景和配置：")
    print("-" * 40)
    print("""
# 场景 1：标准使用（推荐生产环境）
agent = await ReActMasterV4Agent(
    # 启用所有现有特性
    enable_doom_loop_detection=True,
    enable_session_compaction=True,
    enable_output_truncation=True,
    enable_history_pruning=True,
    
    # 新功能配置
    enable_work_log=True,
    work_log_compression_ratio=0.7,  # 70% 上下文时开始压缩
    
    enable_phase_management=True,
    phase_auto_detection=True,      # 自动切换阶段
    
    enable_auto_report=False,         # 手动控制报告生成
)

# 场景 2：快速原型（仅使用 WorkLog）
agent = await ReActMasterV4Agent(
    enable_work_log=True,
    enable_work_log_compression_ratio=0.6,
    # 禁用其他特性以提高性能
    enable_doom_loop_detection=False,
    enable_session_compaction=False,
    enable_phase_management=False,
    enable_auto_report=False,
)

# 场景 3：调试模式（保留所有日志，不压缩）
agent = await ReActMasterV4Agent(
    enable_work_log=True,
    work_log_compression_ratio=1.0,  # 不压缩
    # 启用所有功能，也使用系统输出
    enable_phase_management=True,
    phase_enable_prompts=True,    # 显示阶段提示
    enable_auto_report=True,
)
""")
    print("-" * 40)


async def example_workflow():
    """
    完整工作流程示例

    展示一个典型任务执行过程中的状态变化
    """
    print("\n=== 完整工作流程示例 ===\n")

    print("典型任务执行流程：")
    print("-" * 40)
    print("""
1. 初始化阶段
   - Agent 创建，PhaseManager 设置为 'exploration'
   - WorkLog 管理器创建（懒加载，首次使用时初始化）

2. 任务执行中（每一轮）
   - Agent 选择工具
   - 工具执行
   - ✅ 自动记录到 WorkLog
   - ✅ 自动记录到 PhaseManager
   - ✅ PhaseManager 自动判断是否需要切换阶段

3. 阶段自动切换（示例）
   exploration → planning → execution → refinement → verification → reporting → complete
   - 每个阶段都有特定的 prompt 指导
   - 切换条件在 phase_manager.py 中定义

4. WorkLog 自动管理
   - 记录每次工具调用
   - 大结果（>10KB）自动归档到文件系统
   - 超出 70% 上下文窗口时自动压缩
   - 生成摘要并保留关键信息

5. 任务完成时
   - 检测到 terminate action
   - 切换到 'reporting' 阶段
   - 自动生成详细报告
   - 保存到文件系统
   - 切换到 'complete' 阶段
""")
    print("-" * 40)


async def main():
    """运行所有示例"""
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 20 + "ReActMasterAgentV4 使用示例" + " " * 21 + "║")
    print("╚" + "=" * 58 + "╝\n")

    await example_basic_usage()
    await example_manual_control()
    await example_configurations()
    await example_workflow()

    print("\n╔" + "=" * 58 + "╗")
    print("║" + " " * 18 + "所有示例运行完成" + " " * 24 + "║")
    print("╚" + "=" * 58 + "╝")


if __name__ == "__main__":
    asyncio.run(main())
