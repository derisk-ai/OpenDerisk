"""
阶段管理详细使用说明

本文档详细说明如何使用 PhaseManager 进行阶段管理，
包括自动模式、手动模式以及两者的结合使用。
"""

import asyncio
from typing import Dict, Any
from derisk.agent.expand.react_master_agent import (
    PhaseManager,
    TaskPhase,
)

# ========================================
# 模式 1：全自动感知切换（推荐）
# ========================================


async def example_automatic_mode():
    """
    模式 1：全自动模式

    系统会自动根据以下条件判断阶段切换：
    - 工具调用数量
    - 成功率
    - 错误数量
    - 持续时间

    优点：
    - 无需手动干预
    - 自动适应任务进展
    - 减少认知负担

    适用场景：
    - 标准化的任务流程
    - 不需要对阶段有精细控制的需求
    """
    print("=== 全自动模式 ===\n")

    # 创建阶段管理器，启用自动检测
    phase_manager = PhaseManager(
        auto_phase_detection=True,  # 自动检测
        enable_phase_prompts=True,  # 启用 prompt
    )

    # 模拟工具调用
    print("1. 探索阶段开始...")
    await phase_manager.record_action("search", success=True)
    await phase_manager.record_action("read", success=True)
    await phase_manager.record_action("browse", success=True)

    # 系统会自动判断是否满足转换条件
    current_phase = phase_manager.current_phase
    print(f"   当前阶段: {current_phase.value}")

    # 继续调用，可能触发阶段切换
    await phase_manager.record_action("search", success=True)
    await phase_manager.record_action("search", success=True)
    await phase_manager.record_action("search", success=True)

    # 检查是否自动切换
    current_phase = phase_manager.current_phase
    print(f"   （自动）当前阶段: {current_phase.value}")

    # 查看决策过程
    suggested = phase_manager.should_transition_phase({})
    if suggested:
        print(f"   建议切换到: {suggested.value}")

    stats = phase_manager.get_stats()
    print(f"\n   阶段统计: {stats}\n")


# ========================================
# 模式 2：完全手动控制
# ========================================


async def example_manual_mode():
    """
    模式 2：完全手动模式

    你完全控制阶段切换的时机和原因。

    优点：
    - 精确控制阶段转换
    - 可以基于业务逻辑决定
    - 灵活性高

    适用场景：
    - 需要严格的阶段控制
    - 特定业务流程要求
    - 需要在特定条件下切换
    """
    print("=== 完全手动模式 ===\n")

    # 创建阶段管理器，禁用自动检测
    phase_manager = PhaseManager(
        auto_phase_detection=False,  # 禁用自动检测
        enable_phase_prompts=True,  # 仍启用 prompt
    )

    # 手动切换阶段
    print("1. 开始探索阶段")
    phase_manager.set_phase(TaskPhase.EXPLORATION, reason="开始任务探索")
    print(f"   阶段切换: {phase_manager.current_phase.value}")

    # 执行一些操作
    await phase_manager.record_action("search", success=True)
    await phase_manager.record_action("read", success=True)

    # 手动决定切换
    print("2. 探索完成，进入规划阶段")
    phase_manager.set_phase(TaskPhase.PLANNING, reason="信息收集完毕")
    print(f"   阶段切换: {phase_manager.current_phase.value}")

    await phase_manager.record_action("analyze", success=True)

    # 继续手动切换
    print("3. 规划完成，进入执行阶段")
    phase_manager.set_phase(TaskPhase.EXECUTION, reason="计划已制定")
    print(f"   阶段切换: {phase_manager.current_phase.value}")

    # 查看历史
    print(f"\n   阶段历史: {[p.value for p in phase_manager.phase_history]}")
    print(f"   当前阶段: {phase_manager.current_phase.value}\n")


# ========================================
# 模式 3：混合模式（推荐用于复杂场景）
# ========================================


async def example_hybrid_mode():
    """
    模式 3：混合模式（自动 + 手动）

    结合两种模式的优点：
    - 普通情况下自动切换
    - 特殊情况下手动干预

    优点：
    - 减少手动工作
    - 保留干预能力
    - 最佳实践方案

    适用场景：
    - 大部分流程标准化
    - 少数特殊情况需要手动控制
    - 需要健壮性和灵活性平衡
    """
    print("=== 混合模式 ===\n")

    # 启用自动检测
    phase_manager = PhaseManager(
        auto_phase_detection=True,
        enable_phase_prompts=True,
        custom_transition_rules={
            TaskPhase.EXPLORATION: {
                "require_min_actions": 5,  # 需要至少5次调用
                "require_success_rate": 0.6,  # 成功率需60%
            },
        },
    )

    # 前5次调用 - 自动管理
    print("1. 自动管理阶段...")
    for i in range(5):
        await phase_manager.record_action("search", success=True)

    current_phase = phase_manager.current_phase
    print(f"   当前阶段: {current_phase.value} (自动切换)")

    # 突然遇到特殊情况，手动切换
    print("2. 遇到紧急情况，手动干预...")
    phase_manager.set_phase(TaskPhase.VERIFICATION, reason="发现关键问题，提前进行验证")
    print(f"   手动切换到: {phase_manager.current_phase.value}")

    # 继续执行
    await phase_manager.record_action("validate", success=True)

    # 然后回到自动模式继续
    print("3. 问题解决，继续自动模式...")
    phase_manager.set_phase(TaskPhase.EXECUTION, reason="问题已解决，继续执行")

    for i in range(3):
        await phase_manager.record_action("execute", success=True)

    stats = phase_manager.get_stats()
    print(f"\n   最终阶段: {phase_manager.current_phase.value}")
    print(f"   历史切换: {len(phase_manager.phase_history)} 次\n")


# ========================================
# 实际集成到 Agent 的完整示例
# ========================================


class PhaseAwareReActAgent:
    """
    集成阶段管理的 Agent 示例

    这个示例展示如何将 PhaseManager 集成到实际的 Agent 中。
    """

    def __init__(self, **kwargs):
        # 初始化阶段管理器
        self.phase_manager = PhaseManager(
            auto_phase_detection=True,
            enable_phase_prompts=True,
        )

        # 其他初始化...

    async def execute_tool(self, tool_name: str, args: Dict, **kwargs):
        """
        执行工具并记录到阶段管理器
        """
        # 执行工具
        try:
            result = await self._actual_execute_tool(tool_name, args)
            success = True
        except Exception as e:
            result = str(e)
            success = False

        # 记录到阶段管理器
        self.phase_manager.record_action(tool_name, success)

        # 检查是否需要手动干预
        if self._should_intervene():
            self._manual_intervention()

        return result

    def _should_intervene(self) -> bool:
        """
        判断是否需要手动干预

        可以基于业务逻辑决定
        """
        # 示例：如果在执行阶段遇到3次连续失败
        if self.phase_manager.current_phase == TaskPhase.EXECUTION:
            stats = self.phase_manager.phase_stats.get(TaskPhase.EXECUTION, {})
            if stats.get("error_count", 0) >= 3:
                return True

        return False

    def _manual_intervention(self):
        """
        手动干预逻辑
        """
        # 切换到验证阶段检查问题
        self.phase_manager.set_phase(
            TaskPhase.VERIFICATION, reason="检测到多次失败，暂停执行进行验证"
        )
        print(f"⚠️  手动干预：切换到验证阶段")

    async def _load_thinking_messages(self, *args, **kwargs):
        """
        注入阶段特定的 prompt
        """
        # 获取基础消息
        messages, context, system_prompt, user_prompt = await self._base_load_messages()

        # 获取阶段 prompt
        phase_prompt = self.phase_manager.get_phase_prompt()

        # 注入到 prompt
        if system_prompt:
            system_prompt = self.phase_manager.get_phase_context(system_prompt)

        if user_prompt:
            user_prompt += f"\n\n{phase_prompt}"

        return messages, context, system_prompt, user_prompt

    async def generate_report_with_phase_info(self):
        """
        生成包含阶段信息的报告
        """
        from derisk.agent.expand.react_master_agent.report_generator import (
            ReportGenerator,
        )

        generator = ReportGenerator(
            work_log_manager=self._work_log_manager,
            agent_id=self.name,
            task_id="your_task_id",
        )

        # 在报告中添加阶段信息
        report = await generator.generate_report()

        # 添加阶段历史章节
        from derisk.agent.expand.react_master_agent.report_generator import (
            ReportSection,
        )

        phase_section = ReportSection(
            title="Phase Progression",
            content=self._format_phase_history(),
            level=2,
        )
        report.sections.insert(0, phase_section)

        return report.to_markdown()

    def _format_phase_history(self) -> str:
        """格式化阶段历史"""
        lines = ["Task completed through the following phases:\n"]
        for i, phase in enumerate(self.phase_manager.phase_history, 1):
            lines.append(f"{i}. **{phase.value}**")

        if self.phase_manager.phase_stats:
            lines.append("\n**Phase Statistics:**")
            for phase, stats in self.phase_manager.phase_stats.items():
                if stats.get("actions_count", 0) > 0:
                    lines.append(
                        f"- {phase.value}: {stats} actions, "
                        f"success rate: {stats.get('success_count', 0) / stats.get('actions_count', 1):.1%}"
                    )

        return "\n".join(lines)


# ========================================
# 自动切换的详细规则说明
# ========================================


def explain_automatic_detection_rules():
    """
    解释自动切换的详细规则

    默认规则实现在 PhaseManager.should_transition_phase() 中：
    """
    print("=== 自动切换规则说明 ===\n")

    rules = {
        "EXPLORATION → PLANNING": {
            "条件": {
                "最少工具调用": "5 次",
                "最低成功率": "60%",
            },
            "说明": "收集了足够信息且成功率满足要求后进入规划",
        },
        "PLANNING → EXECUTION": {
            "条件": {
                "规划活动": "至少 3 次",
            },
            "说明": "完成基本规划后开始执行",
        },
        "EXECUTION → REFINEMENT": {
            "条件": {
                "最大调用次数": "50 次",
                "有错误": "是",
            },
            "说明": "执行较多或遇到错误时进行优化",
        },
        "EXECUTION → VERIFICATION": {
            "条件": {
                "最大调用次数": "50 次",
                "无错误": "是",
            },
            "说明": "执行顺利完成直接进入验证",
        },
        "REFINEMENT → VERIFICATION": {
            "条件": {
                "最少优化": "5 次",
                "无错误": "是",
            },
            "说明": "优化完成后验证",
        },
        "VERIFICATION → REPORTING": {
            "条件": {
                "最少验证": "3 次",
            },
            "说明": "完成验证后生成报告",
        },
        "REPORTING → COMPLETE": {
            "条件": {
                "最少报告": "2 次",
            },
            "说明": "报告生成完毕",
        },
    }

    for transition, config in rules.items():
        print(f"【{transition}】")
        print(f"  条件:")
        for condition, value in config["条件"].items():
            print(f"    - {condition}: {value}")
        print(f"  说明: {config['说明']}")
        print()


# ========================================
# 自定义转换规则
# ========================================


async def example_custom_rules():
    """
    自定义阶段转换规则示例
    """
    print("=== 自定义转换规则 ===\n")

    # 创建自定义规则
    custom_rules = {
        TaskPhase.EXPLORATION: {
            "require_min_actions": 10,  # 需要更多探索
            "require_success_rate": 0.7,  # 更高的成功率
            "require_specific_tools": ["search", "read"],  # 必须使用特定工具
        },
        TaskPhase.EXECUTION: {
            "max_actions": 100,  # 允许更多执行
            "error_tolerance": 0.2,  # 最多20%错误率
        },
    }

    phase_manager = PhaseManager(
        auto_phase_detection=True,
        phase_transition_rules=custom_rules,
    )

    print("自定义规则已应用！")
    print("探索阶段需要 10 次调用且 70% 成功率")
    print("执行阶段需要完成或达到 100 次调用或 20% 错误率\n")


# ========================================
# 运行所有示例
# ========================================


async def main():
    """运行所有示例"""
    print("╔══════════════════════════════════════════════════╗")
    print("║     阶段管理使用说明                             ║")
    print("╚══════════════════════════════════════════════════╝\n")

    # 1. 全自动模式
    await example_automatic_mode()

    # 2. 完全手动模式
    await example_manual_mode()

    # 3. 混合模式
    await example_hybrid_mode()

    # 4. 规则说明
    explain_automatic_detection_rules()

    # 5. 自定义规则
    await example_custom_rules()

    print("╔══════════════════════════════════════════════════╗")
    print("║     使用说明总结                                 ║")
    print("╚══════════════════════════════════════════════════╝\n")

    print("1. 全自动模式（最简单）:")
    print("   phase_manager = PhaseManager(auto_phase_detection=True)")
    print("   phase_manager.record_action(tool_name, success)")
    print("   # 系统自动切换阶段\n")

    print("2. 完全手动模式（精确控制）:")
    print("   phase_manager = PhaseManager(auto_phase_detection=False)")
    print("   phase_manager.set_phase(TaskPhase.EXECUTION, reason)")
    print("   # 完全由你控制\n")

    print("3. 混合模式（推荐）:")
    print("   phase_manager = PhaseManager(auto_phase_detection=True)")
    print("   # 大部分时候自动，需要时手动 set_phase")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
