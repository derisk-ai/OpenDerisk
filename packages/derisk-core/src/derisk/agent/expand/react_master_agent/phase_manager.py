"""
ReAct 阶段式 Prompt 管理器

支持根据任务的不同阶段动态调整 prompt，提供更好的上下文和指导。
"""

import logging
from enum import Enum
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class TaskPhase(str, Enum):
    """任务阶段枚举"""

    EXPLORATION = "exploration"  # 探索阶段：理解问题、收集信息
    PLANNING = "planning"  # 规划阶段：制定执行计划
    EXECUTION = "execution"  # 执行阶段：执行具体任务
    REFINEMENT = "refinement"  # 优化阶段：优化和改进
    VERIFICATION = "verification"  # 验证阶段：验证结果
    REPORTING = "reporting"  # 报告阶段：生成最终报告
    COMPLETE = "complete"  # 完成


class PhaseContext:
    """阶段上下文，包含每个阶段特定的 prompt 片段"""

    PHASE_PROMPTS = {
        TaskPhase.EXPLORATION: """
## 当前阶段：探索与理解

你正在进行**探索阶段**，主要任务是：
1. 深入理解用户的需求和目标
2. 分析问题的范围和约束条件
3. 收集必要的信息和数据
4. 识别可能的风险和挑战

**指导原则：**
- 优先使用信息收集工具（如：search, read, browse）
- 保持好奇心，多角度思考问题
- 记录所有发现和洞察
- 避免过早下结论
""",
        TaskPhase.PLANNING: """
## 当前阶段：规划与设计

你正在进行**规划阶段**，主要任务是：
1. 基于探索结果制定清晰的执行计划
2. 将复杂任务分解为可管理的子任务
3. 确定每个子任务的优先级和依赖关系
4. 选择合适的工具和方法

**指导原则：**
- 制定详细、可执行的步骤
- 识别关键里程碑
- 评估每步的预期成果
- 考虑多种可能的方案
""",
        TaskPhase.EXECUTION: """
## 当前阶段：执行与实施

你正在进行**执行阶段**，主要任务是：
1. 按照计划执行具体的操作
2. 根据实际情况调整策略
3. 完成各个子任务
4. 收集执行过程中的数据和结果

**指导原则：**
- 严格按计划执行，但保持灵活性
- 记录每一步的进展和结果
- 遇到问题及时调整策略
- 定期评估进度，确保目标对齐
""",
        TaskPhase.REFINEMENT: """
## 当前阶段：优化与改进

你正在进行**优化阶段**，主要任务是：
1. 评估执行结果的质量
2. 识别可以改进的地方
3. 优化输出和完善细节
4. 确保成果符合最高标准

**指导原则：**
- 审查每个环节的结果
- 寻找提升空间
- 完善数据和文档
- 确保最佳实践的应用
""",
        TaskPhase.VERIFICATION: """
## 当前阶段：验证与确认

你正在进行**验证阶段**，主要任务是：
1. 验证结果的正确性和完整性
2. 检查是否满足所有需求
3. 识别并修复任何问题
4. 获得最终确认

**指导原则：**
- 系统化地验证每个部分
- 使用测试和检查工具
- 确保没有遗漏或错误
- 准备完整的验证报告
""",
        TaskPhase.REPORTING: """
## 当前阶段：报告与总结

你正在进行**报告阶段**，主要任务是：
1. 汇总所有发现和结果
2. 生成清晰、结构化的报告
3. 提供有价值的洞察和建议
4. 确保报告易于理解和传达

**指导原则：**
- 以用户价值为导向组织内容
- 使用清晰的标题和结构
- 提供具体、可操作的建议
- 包含所有关键发现和数据
""",
        TaskPhase.COMPLETE: """
## 当前阶段：已完成

任务已全部完成！回顾整个过程：

**成果总结：**
- 成功完成了所有预定目标
- 生成了完整的交付物
- 所有阶段都已验证通过

感谢你的努力！
""",
    }

    PHASE_PRIORITIZED_TOOLS = {
        TaskPhase.EXPLORATION: ["search", "browse", "read", "grep"],
        TaskPhase.PLANNING: ["think", "analyze", "list"],
        TaskPhase.EXECUTION: ["execute", "run", "process", "write"],
        TaskPhase.REFINEMENT: ["review", "optimize", "polish"],
        TaskPhase.VERIFICATION: ["test", "validate", "check"],
        TaskPhase.REPORTING: ["summarize", "format", "export"],
    }


class PhaseManager:
    """
    阶段管理器

    负责管理任务的各个阶段，提供阶段切换和上下文管理功能。
    """

    def __init__(
        self,
        auto_phase_detection: bool = True,
        enable_phase_prompts: bool = True,
        phase_transition_rules: Optional[Dict[TaskPhase, Dict[str, bool]]] = None,
    ):
        """
        初始化阶段管理器

        Args:
            auto_phase_detection: 启用自动阶段检测
            enable_phase_prompts: 启用阶段特定的 prompt
            phase_transition_rules: 阶段转换规则
        """
        self.auto_phase_detection = auto_phase_detection
        self.enable_phase_prompts = enable_phase_prompts
        self.current_phase = TaskPhase.EXPLORATION
        self.phase_history: List[TaskPhase] = []
        self.phase_start_time: Dict[TaskPhase, float] = {}
        self.phase_stats: Dict[TaskPhase, Dict[str, int]] = {}

        # 默认的阶段转换规则
        self.transition_rules = phase_transition_rules or {
            TaskPhase.EXPLORATION: {
                "require_min_actions": 3,
                "require_success_rate": 0.5,
            },
            TaskPhase.PLANNING: {
                "require_plannable": True,
            },
        }

        logger.info(f"PhaseManager initialized, starting phase: {self.current_phase}")

    def set_phase(self, phase: TaskPhase, reason: str = ""):
        """
        手动设置当前阶段

        Args:
            phase: 目标阶段
            reason: 阶段转换的原因
        """
        if self.current_phase != phase:
            import time

            old_phase = self.current_phase

            # 记录阶段开始时间
            if old_phase not in self.phase_start_time:
                self.phase_start_time[old_phase] = time.time()

            # 计算阶段持续时间
            if old_phase in self.phase_start_time:
                duration = time.time() - self.phase_start_time[old_phase]
                logger.info(
                    f"Phase transition: {old_phase} -> {phase} "
                    f"(duration: {duration:.1f}s, reason: {reason})"
                )

            # 更新当前阶段
            self.phase_history.append(self.current_phase)
            self.current_phase = phase
            self.phase_start_time[phase] = time.time()

            # 初始化阶段统计
            if phase not in self.phase_stats:
                self.phase_stats[phase] = {
                    "actions_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                }

    def should_transition_phase(self, context: Dict) -> Optional[TaskPhase]:
        """
        判断是否应该转换阶段（自动检测）

        Args:
            context: 上下文信息，包含统计、结果等

        Returns:
            建议的下一个阶段，如果不需要转换则返回 None
        """
        if not self.auto_phase_detection:
            return None

        phase_stats = self.phase_stats.get(self.current_phase, {})
        actions_count = phase_stats.get("actions_count", 0)
        success_count = phase_stats.get("success_count", 0)

        # 探索阶段 -> 规划阶段
        if self.current_phase == TaskPhase.EXPLORATION:
            rules = self.transition_rules.get(TaskPhase.EXPLORATION, {})
            min_actions = rules.get("require_min_actions", 5)
            min_success_rate = rules.get("require_success_rate", 0.6)

            if actions_count >= min_actions:
                success_rate = success_count / actions_count if actions_count > 0 else 0
                if success_rate >= min_success_rate:
                    return TaskPhase.PLANNING

        # 规划阶段 -> 执行阶段
        elif self.current_phase == TaskPhase.PLANNING:
            if actions_count >= 3:  # 至少有一些规划活动
                return TaskPhase.EXECUTION

        # 执行阶段 -> 优化阶段
        elif self.current_phase == TaskPhase.EXECUTION:
            rules = self.transition_rules.get(TaskPhase.EXECUTION, {})
            max_actions = rules.get("max_actions", 50)

            if actions_count >= max_actions:
                has_errors = phase_stats.get("error_count", 0) > 0
                if has_errors:
                    return TaskPhase.REFINEMENT
                else:
                    return TaskPhase.VERIFICATION

        # 优化阶段 -> 验证阶段
        elif self.current_phase == TaskPhase.REFINEMENT:
            if actions_count >= 5 and phase_stats.get("error_count", 0) == 0:
                return TaskPhase.VERIFICATION

        # 验证阶段 -> 报告阶段
        elif self.current_phase == TaskPhase.VERIFICATION:
            if actions_count >= 3:  # 至少执行了一些验证
                return TaskPhase.REPORTING

        # 报告阶段 -> 完成
        elif self.current_phase == TaskPhase.REPORTING:
            if actions_count >= 2:  # 至少生成了一些报告
                return TaskPhase.COMPLETE

        return None

    def record_action(self, tool_name: str, success: bool):
        """
        记录工具调用，用于阶段统计和自动转换

        Args:
            tool_name: 工具名称
            success: 是否成功
        """
        stats = self.phase_stats.setdefault(self.current_phase, {})
        stats["actions_count"] = stats.get("actions_count", 0) + 1

        if success:
            stats["success_count"] = stats.get("success_count", 0) + 1
        else:
            stats["error_count"] = stats.get("error_count", 0) + 1

        # 尝试自动转换阶段
        suggested_phase = self.should_transition_phase({})
        if suggested_phase:
            self.set_phase(suggested_phase, f"Automatic transition based on activity")

    def get_phase_prompt(self) -> str:
        """
        获取当前阶段的 prompt 片段

        Returns:
            当前阶段的 prompt 描述
        """
        if not self.enable_phase_prompts:
            return ""

        return PhaseContext.PHASE_PROMPTS.get(
            self.current_phase, f"## 当前阶段：{self.current_phase.value}\n"
        )

    def get_prioritized_tools(self) -> List[str]:
        """
        获取当前阶段优先推荐的工具

        Returns:
            工具名称列表
        """
        return PhaseContext.PHASE_PRIORITIZED_TOOLS.get(
            self.current_phase,
            [],
        )

    def get_phase_context(self, system_prompt: str) -> str:
        """
        将阶段上下文注入到 system prompt

        Args:
            system_prompt: 原始 system prompt

        Returns:
            增强后的 system prompt
        """
        phase_prompt = self.get_phase_prompt()

        if phase_prompt:
            return f"{system_prompt}\n\n{phase_prompt}"

        return system_prompt

    def get_user_prompt_context(
        self, user_prompt: str, work_log_context: str = ""
    ) -> str:
        """
        将阶段上下文和 WorkLog 注入到 user prompt

        Args:
            user_prompt: 原始 user prompt
            work_log_context: WorkLog 上下文

        Returns:
            增强后的 user prompt
        """
        lines = []

        # 添加阶段提示
        if self.enable_phase_prompts:
            stage_hint = f"\n**当前处于 {self.current_phase.value} 阶段**\n"
            lines.append(stage_hint)

        # 添加推荐的工具提示
        if self.auto_phase_detection:
            tools = self.get_prioritized_tools()
            if tools:
                lines.append(f"\n**此阶段推荐使用的工具：** {', '.join(tools)}\n")

        # 添加 WorkLog
        if work_log_context:
            lines.append(f"\n{work_log_context}\n")

        # 添加原始 prompt
        lines.append(user_prompt)

        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """获取阶段统计信息"""
        import time

        current_duration = 0
        if self.current_phase in self.phase_start_time:
            current_duration = time.time() - self.phase_start_time[self.current_phase]

        return {
            "current_phase": self.current_phase.value,
            "phase_history": [p.value for p in self.phase_history],
            "current_phase_duration": current_duration,
            "phase_stats": {
                phase.value: stats for phase, stats in self.phase_stats.items()
            },
            "auto_phase_detection": self.auto_phase_detection,
        }


# 便捷函数
def create_phase_manager(
    auto_detection: bool = True,
    enable_prompts: bool = True,
) -> PhaseManager:
    """
    创建并初始化阶段管理器

    Args:
        auto_detection: 启用自动阶段检测
        enable_prompts: 启用阶段 prompt

    Returns:
        PhaseManager 实例
    """
    return PhaseManager(
        auto_phase_detection=auto_detection,
        enable_phase_prompts=enable_prompts,
    )


__all__ = [
    "TaskPhase",
    "PhaseContext",
    "PhaseManager",
    "create_phase_manager",
]
