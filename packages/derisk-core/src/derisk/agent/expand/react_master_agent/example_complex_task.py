"""
复杂任务实战案例：自动化代码审查与优化系统

场景：
一个需要多阶段协作的复杂任务 - 对一个大型代码库进行全面的代码审查、
问题识别、自动修复、验证，并生成详细报告。

这个案例展示了：
1. 多阶段自动切换的实际应用
2. 复杂任务中的阶段管理
3. 如何处理突发情况和手动干预
4. 生成详细的阶段报告
"""

import asyncio
import json
from typing import Dict, Any, List
from datetime import datetime

from derisk.agent.expand.react_master_agent import (
    PhaseManager,
    TaskPhase,
    WorkLogManager,
    ReportGenerator,
    ReportType,
    ReportFormat,
)


class CodeReviewAndOptimizationSystem:
    """
    代码审查与优化系统

    复杂任务：代码审查 → 问题识别 → 自动修复 → 验证 → 报告生成
    """

    def __init__(self, repo_url: str):
        self.repo_url = repo_url
        self.task_id = f"code_review_{int(datetime.now().timestamp())}"

        # 初始化组件
        self.phase_manager = PhaseManager(
            auto_phase_detection=True,
            enable_phase_prompts=True,
        )

        # 模拟 WorkLog（实际使用时会从 WorkLogManager 获取）
        self.work_log = []

        # 结果存储
        self.issues_found = []
        self.fixes_applied = []
        self.validation_results = []

        print(f"🚀 代码审查与优化系统初始化完成")
        print(f"📁 目标仓库: {repo_url}\n")

    async def execute_full_review(self):
        """
        执行完整的代码审查流程
        """
        print("=" * 60)
        print("开始执行代码审查与优化任务")
        print("=" * 60)

        # 阶段 1：探索 - 了解代码库结构
        await self._exploration_phase()

        # 阶段 2：规划 - 制定审查计划
        await self._planning_phase()

        # 阶段 3：执行 - 进行代码审查和修复
        await self._execution_phase()

        # 阶段 4：验证 - 验证修复效果
        await self._verification_phase()

        # 阶段 5：报告 - 生成详细报告
        await self._reporting_phase()

        print("=" * 60)
        print("✅ 任务完成！")
        print("=" * 60)

    async def _exploration_phase(self):
        """
        阶段 1：探索阶段

        目标：
        - 了解代码库结构
        - 识别主要模块和文件
        - 检查基本信息（语言、框架、依赖）
        """
        print("\n" + "=" * 60)
        print("🔍 阶段 1: 探索代码库结构")
        print("=" * 60)

        # 模拟探索操作
        operations = [
            ("git_clone", f"克隆仓库: {self.repo_url}", True),
            ("read_structure", "读取项目结构和配置文件", True),
            ("analyze_deps", "分析项目依赖关系", True),
            ("scan_files", "扫描代码文件类型", True),
            ("identify_modules", "识别主要模块", True),
            ("check_framework", "检查使用的框架", True),
        ]

        for tool_name, description, success in operations:
            await self._execute_tool(tool_name, description, success)
            await asyncio.sleep(0.3)  # 模拟操作耗时

        # 系统自动判断是否应该进入下一阶段
        print(f"\n🎯 自动检测: 准备进入下一阶段...")
        print(f"   当前工具调用数: {len(self.work_log)}")

        # 继续探索直到满足条件
        more_ops = [
            ("analyze_complexity", "分析代码复杂度", True),
            ("find_tests", "查找测试文件", True),
        ]

        for tool_name, description, success in more_ops:
            await self._execute_tool(tool_name, description, success)

        print(f"\n✅ 探索阶段完成")
        print(f"   自动切换到: {self.phase_manager.current_phase.value}")

    async def _planning_phase(self):
        """
        阶段 2：规划阶段

        目标：
        - 制定审查计划
        - 确定审查优先级
        - 规划修复策略
        """
        print("\n" + "=" * 60)
        print(
            f"📋 阶段 2: {self.phase_manager.current_phase.value.upper()} - 制定审查计划"
        )
        print("=" * 60)

        # 模拟规划操作
        operations = [
            ("create_checklist", "创建审查检查清单", True),
            ("prioritize_files", "按优先级排序审查文件", True),
            ("define_rules", "定义代码审查规则", True),
        ]

        for tool_name, description, success in operations:
            await self._execute_tool(tool_name, description, success)
            await asyncio.sleep(0.2)

        print(f"\n✅ 规划阶段完成，审查策略已制定")

    async def _execution_phase(self):
        """
        阶段 3：执行阶段

        目标：
        - 执行代码审查
        - 识别问题
        - 应用修复
        """
        print("\n" + "=" * 60)
        print(
            f"⚙️  阶段 3: {self.phase_manager.current_phase.value.upper()} - 执行代码审查"
        )
        print("=" * 60)

        # 批量执行代码审查
        review_operations = [
            ("lint_python", "运行 Python linter 检查", True),
            ("security_scan", "安全漏洞扫描", True),
            ("code_smell_detect", "代码异味检测", True),
            ("duplication_check", "代码重复检查", True),
            ("error_check", "静态错误检查", True),
            ("complexity_analyze", "复杂度分析", True),
        ]

        # 执行审查
        for tool_name, description, success in review_operations:
            await self._execute_tool(tool_name, description, success)
            await asyncio.sleep(0.2)

        # 发现问题，开始修复
        print("\n🔧 发现问题，开始修复...")
        self.issues_found = [
            {"type": "security", "severity": "high", "file": "auth.py"},
            {"type": "error", "severity": "critical", "file": "payment.py"},
            {"type": "code_smell", "severity": "medium", "file": "utils.py"},
            {"type": "duplication", "severity": "low", "file": "helpers.py"},
        ]

        print(f"   发现 {len(self.issues_found)} 个问题")

        # 修复操作
        fix_operations = [
            ("fix_security", f"修复安全问题: {self.issues_found[0]['file']}", True),
            ("fix_critical", f"修复关键错误: {self.issues_found[1]['file']}", True),
            ("refactor", f"重构代码: {self.issues_found[2]['file']}", True),
            ("remove_dup", f"消除重复代码: {self.issues_found[3]['file']}", True),
            ("run_tests", "运行测试套件", True),  # 可能会失败，进入优化阶段
        ]

        for tool_name, description, success in fix_operations:
            await self._execute_tool(tool_name, description, success)
            await asyncio.sleep(0.2)

        # 模拟：测试失败，系统应该检测到并可能切换到优化阶段
        print("\n⚠️  测试发现 3 个失败，系统检测中...")

        # 触发系统检测
        await self._handle_test_failures()

        print(f"\n✅ 执行阶段完成")
        print(f"   自动切换到: {self.phase_manager.current_phase.value}")

    async def _handle_test_failures(self):
        """
        处理测试失败的情况

        这展示系统如何自动检测问题并决定阶段切换
        """
        # 记录失败
        await self._execute_tool("test_runner", "运行测试", False)
        await self._execute_tool("test_runner", "运行测试", False)
        await self._execute_tool("test_runner", "运行测试", False)

        # 系统应该检测到连续失败并可能切换到优化
        await asyncio.sleep(0.5)

        # 模拟一些修复
        print("   🔧 尝试修复 failing tests...")
        await self._execute_tool("debug_test", "调试测试失败原因", True)
        await self._execute_tool("fix_bug", "修复导致测试失败的 bug", True)
        await self._execute_tool("test_runner", "重新运行测试", True)  # 成功

    async def _verification_phase(self):
        """
        阶段 4：验证阶段

        目标：
        - 验证修复效果
        - 确保没有引入新问题
        - 运行完整测试套件
        """
        print("\n" + "=" * 60)
        print(
            f"✅ 阶段 4: {self.phase_manager.current_phase.value.upper()} - 验证修复效果"
        )
        print("=" * 60)

        # 验证操作
        verification_operations = [
            ("full_test_suite", "运行完整测试套件", True),
            ("regression_test", "回归测试", True),
            ("check_coverage", "检查代码覆盖率", True),
            ("validate_fixes", "验证所有修复", True),
        ]

        for tool_name, description, success in verification_operations:
            await self._execute_tool(tool_name, description, success)
            await asyncio.sleep(0.2)

        # 收集验证结果
        self.validation_results = {
            "tests_passed": 142,
            "tests_failed": 0,
            "coverage": "87.5%",
            "issues_fixed": len(self.issues_found),
            "new_issues": 0,
        }

        print(f"\n   验证结果:")
        print(
            f"   ✅ 测试通过: {self.validation_results['tests_passed']}/{self.validation_results['tests_passed']}"
        )
        print(f"   ✅ 代码覆盖率: {self.validation_results['coverage']}")
        print(f"   ✅ 修复问题: {self.validation_results['issues_fixed']}")
        print(f"   ✅ 新问题: {self.validation_results['new_issues']}")

    async def _reporting_phase(self):
        """
        阶段 5：报告阶段

        目标：
        - 生成详细的审查报告
        - 导出多种格式
        - 总结成果
        """
        print("\n" + "=" * 60)
        print(
            f"📊 阶段 5: {self.phase_manager.current_phase.value.upper()} - 生成审查报告"
        )
        print("=" * 60)

        # 生成报告
        report_operations = [
            ("generate_markdown", "生成 Markdown 报告", True),
            ("generate_html", "生成 HTML 报告", True),
            ("generate_json", "生成 JSON 报告", True),
            ("export_summary", "导出执行摘要", True),
        ]

        for tool_name, description, success in report_operations:
            await self._execute_tool(tool_name, description, success)
            await asyncio.sleep(0.2)

        print("\n   📄 报告已生成:")
        print(f"   - code_review_report.md")
        print(f"   - code_review_report.html")
        print(f"   - code_review_report.json")

        # 完成任务
        await self._execute_tool("finalize", "完成任务", True)

        print("\n✅ 所有阶段完成！")

    async def _execute_tool(self, tool_name: str, description: str, success: bool):
        """
        执行工具并记录到阶段管理器

        Args:
            tool_name: 工具名称
            description: 操作描述
            success: 是否成功
        """
        # 记录到 work log
        self.work_log.append(
            {
                "tool": tool_name,
                "description": description,
                "success": success,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # 记录到阶段管理器
        self.phase_manager.record_action(tool_name, success)

        # 打印执行信息
        icon = "✅" if success else "❌"
        print(f"   {icon} [{self.phase_manager.current_phase.value}] {description}")

    def generate_final_report(self) -> str:
        """
        生成最终的综合报告
        """
        # 获取阶段统计
        phase_stats = self.phase_manager.get_stats()

        # 构建报告
        report_lines = [
            "# 代码审查与优化任务报告",
            "",
            f"**任务 ID**: {self.task_id}",
            f"**完成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## 执行摘要",
            "",
            f"- **仓库**: {self.repo_url}",
            f"- **发现的问题**: {len(self.issues_found)}",
            f"- **应用修复**: {len(self.fixes_applied) if self.fixes_applied else len(self.issues_found)}",
            "",
            "## 阶段进度",
            "",
        ]

        # 阶段历史
        report_lines.append("任务完成以下阶段：")
        for i, phase in enumerate(phase_stats["phase_history"], 1):
            report_lines.append(f"{i}. **{phase}**")

        report_lines.extend(
            [
                "",
                f"最终阶段: **{phase_stats['current_phase']}**",
                "",
                "---",
                "",
                "## 执行详细记录",
                "",
                "### 阶段分解",
                "",
            ]
        )

        # 按阶段分组显示执行记录
        current_phase = "exploration"
        phase_count = 0

        for log in self.work_log:
            # 这里简化，实际应该从阶段管理器获取准确的阶段信息
            phase_count += 1
            icon = "✅" if log["success"] else "❌"
            report_lines.append(f"{icon} {log['tool']}: {log['description']}")

        report_lines.extend(
            [
                "",
                f"**总操作数**: {len(self.work_log)}",
                "",
                "---",
                "",
                "## 成果验证",
                "",
                f"**测试通过**: {self.validation_results.get('tests_passed', 0)}/{self.validation_results.get('tests_passed', 0)}",
                f"**代码覆盖率**: {self.validation_results.get('coverage', 'N/A')}",
                f"**修复问题**: {self.validation_results.get('issues_fixed', 0)}",
                f"**新问题**: {self.validation_results.get('new_issues', 0)}",
                "",
                "---",
                "",
                "## 结论",
                "",
                "✅ 代码审查与优化任务已成功完成。",
                "所有发现的问题均已修复并通过验证。",
                "",
                "---",
                "",
                "*Generated by ReActMasterV3 with Phase Management*",
            ]
        )

        return "\n".join(report_lines)

    def diagnose_current_state(self):
        """
        诊断当前系统状态

        展示如何查看系统决策过程
        """
        print("\n" + "=" * 60)
        print("🔍 系统状态诊断")
        print("=" * 60)

        stats = self.phase_manager.get_stats()

        print(f"\n当前阶段: {stats['current_phase']}")
        print(f"阶段历史: {' -> '.join(stats['phase_history'])}")
        print(f"当前统计: {json.dumps(stats['current_stats'], indent=2)}")

        if stats["transition_history"]:
            print(f"\n转换历史:")
            for transition in stats["transition_history"]:
                print(f"  - {transition['from_phase']} -> {transition['to_phase']}")


async def example_basic_complex_task():
    """
    示例 1：基本的复杂任务执行

    展示完整的自动化流程
    """
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "示例 1: 自动化代码审查" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")

    # 创建系统
    system = CodeReviewAndOptimizationSystem(
        repo_url="https://github.com/example/codebase"
    )

    # 执行完整流程
    await system.execute_full_review()

    # 生成最终报告
    final_report = system.generate_final_report()

    print("\n" + "=" * 60)
    print("📊 最终报告")
    print("=" * 60)
    print(final_report)


async def example_with_manual_intervention():
    """
    示例 2：包含手动干预的复杂任务

    展示如何在自动化流程中进行手动干预
    """
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "示例 2: 手动干预 + 自动化" + " " * 12 + "║")
    print("╚" + "=" * 58 + "╝")

    # 创建系统
    system = CodeReviewAndOptimizationSystem(
        repo_url="https://github.com/example/codebase"
    )

    print("\n执行探索阶段...")
    await system._exploration_phase()

    print("\n执行规划阶段...")
    await system._planning_phase()

    # 开始执行，但手动干预
    print("\n开始执行阶段...")
    await system._execute_tool("lint_python", "运行 Python linter", True)
    await system._execute_tool("security_scan", "安全漏洞扫描", False)  # 失败

    # ⚠️ 手动干预：发现紧急安全问题
    print("\n⚠️  检测到严重安全问题，手动干预！")

    # 切换到验证阶段处理紧急问题
    system.phase_manager.set_phase(
        TaskPhase.VERIFICATION, reason="检测到严重安全问题，需要紧急验证"
    )

    await system._execute_tool("emergency_fix", "应用紧急安全修复", True)

    # 恢复执行阶段
    print("\n✅ 紧急问题已解决，恢复执行阶段...")
    system.phase_manager.set_phase(
        TaskPhase.EXECUTION, reason="紧急问题已解决，继续执行"
    )

    # 继续执行
    await system._execute_tool("code_smell_detect", "代码异味检测", True)
    await system._execute_tool("duplication_check", "代码重复检查", True)

    # 完成剩余流程
    await system._verification_phase()
    await system._reporting_phase()

    print("\n✅ 带手动干预的任务完成！")

    # 诊断状态
    system.diagnose_current_state()


async def example_detailed_diagnosis():
    """
    示例 3：详细的系统诊断

    展示如何查看系统内部状态和决策日志
    """
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 18 + "示例 3: 详细诊断" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")

    # 创建系统
    system = CodeReviewAndOptimizationSystem(
        repo_url="https://github.com/example/codebase"
    )

    # 执行一些操作
    print("\n执行操作...")

    # 探索阶段
    await system._execute_tool("git_clone", "克隆仓库", True)
    await system._execute_tool("read_structure", "读取结构", True)
    await system._execute_tool("analyze_deps", "分析依赖", True)
    await system._execute_tool("scan_files", "扫描文件", True)
    await system._execute_tool("identify_modules", "识别模块", True)

    # 规划阶段
    print("\n应该自动切换到规划阶段...")
    await system._execute_tool("create_checklist", "创建清单", True)
    await system._execute_tool("prioritize_files", "优先级排序", True)

    # 详细诊断
    system.diagnose_current_state()

    # 查看阶段统计详情
    print("\n" + "=" * 60)
    print("📊 阶段统计分析")
    print("=" * 60)

    stats = system.phase_manager.get_stats()

    print(f"\n当前阶段: {stats['current_phase']}")
    print(f"已完成阶段: {len(stats['phase_history'])}")
    print(f"当前阶段统计:")
    current_stats = stats["current_stats"]
    print(f"  - 持续时间: {current_stats['duration']:.1f} 秒")
    print(f"  - 总操作数: {current_stats['total_actions']}")
    print(f"  - 成功数: {current_stats['success_count']}")
    print(f"  - 错误数: {current_stats['error_count']}")
    print(f"  - 唯一工具: {current_stats['unique_tools']}")
    print(f"  - 最常用工具: {current_stats['most_used_tool']}")
    print(f"  - 连续成功: {current_stats['consecutive_success']}")
    print(f"  - 连续错误: {current_stats['consecutive_errors']}")
    print(f"  - 停滞计数: {current_stats['stagnation_count']}")


async def main():
    """
    运行所有示例
    """
    # 示例 1：完全自动化
    await example_basic_complex_task()

    # 示例 2：带手动干预
    await example_with_manual_intervention()

    # 示例 3：详细诊断
    await example_detailed_diagnosis()

    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 18 + "所有示例完成！" + " " * 19 + "║")
    print("╚" + "=" * 58 + "╝")


if __name__ == "__main__":
    asyncio.run(main())
