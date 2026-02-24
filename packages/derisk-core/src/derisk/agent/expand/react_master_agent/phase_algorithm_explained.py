"""
阶段管理器核心算法详解

本文档详细解释自动阶段切换的算法逻辑和决策过程。
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


class TaskPhase(str, Enum):
    """任务阶段枚举"""

    EXPLORATION = "exploration"
    PLANNING = "planning"
    EXECUTION = "execution"
    REFINEMENT = "refinement"
    VERIFICATION = "verification"
    REPORTING = "_reporting"
    COMPLETE = "complete"


@dataclass
class PhaseDecisionCriteria:
    """
    阶段决策标准

    每个阶段都有特定的转换标准
    """

    # 探索阶段 → 规划阶段
    exploration_to_planning: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_actions": 5,  # 最少调用次数
            "min_success_rate": 0.6,  # 最低成功率
            "min_unique_tools": 2,  # 至少使用2种不同工具
            "require_summary": False,  # 是否需要总结
        }
    )

    # 规划阶段 → 执行阶段
    planning_to_execution: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_planning_actions": 3,  # 最少规划活动
            "has_plan_document": False,  # 是否有计划文档
            "max_duration": 600,  # 最长时间（秒）
        }
    )

    # 执行阶段 → 优化/验证阶段
    execution_branch: Dict[str, Any] = field(
        default_factory=lambda: {
            "max_actions": 50,  # 最大调用次数
            "error_threshold": 0.2,  # 错误阈值（比率）
            "stagnation_threshold": 10,  # 停滞阈值（相同工具连续调用次数）
            "success_refine_threshold": 0.3,  # 成功则优化（特定工具）
        }
    )

    # 优化阶段 → 验证阶段
    refinement_to_verification: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_optimize_actions": 5,  # 最少优化活动
            "error_free_count": 3,  # 连续无错误次数
        }
    )

    # 验证阶段 → 报告阶段
    verification_to_reporting: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_validate_actions": 3,  # 最少验证活动
            "all_validated": False,  # 是否全部验证通过
        }
    )

    # 报告阶段 → 完成
    reporting_to_complete: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_export_actions": 2,  # 最少导出活动
            "has_final_report": False,  # 是否有最终报告
        }
    )


class PhaseStateTracker:
    """
    阶段状态跟踪器

    记录每个阶段的详细状态，用于决策
    """

    def __init__(self):
        self.tool_history: List[str] = []
        self.success_pattern: List[bool] = []
        self.phase_start_time: Dict[TaskPhase, float] = {}
        self.tool_usage_count: Dict[str, int] = {}
        self.error_count: int = 0
        self.last_error_time: Optional[float] = None
        self.consecutive_success: int = 0
        self.consecutive_errors: int = 0
        self.stagnation_count: int = 0

    def record_action(self, tool_name: str, success: bool):
        """记录动作"""
        # 记录历史
        self.tool_history.append(tool_name)
        self.success_pattern.append(success)

        # 更新工具计数
        self.tool_usage_count[tool_name] = self.tool_usage_count.get(tool_name, 0) + 1

        # 更新错误统计
        if success:
            self.consecutive_success += 1
            self.consecutive_errors = 0
        else:
            self.consecutive_errors += 1
            self.consecutive_success = 0
            self.error_count += 1
            self.last_error_time = time.time()

        # 检测停滞（连续使用相同工具）
        self._check_stagnation(tool_name)

    def _check_stagnation(self, tool_name: str):
        """检测是否停滞"""
        if len(self.tool_history) >= 3:
            recent_3 = self.tool_history[-3:]
            if all(t == tool_name for t in recent_3):
                self.stagnation_count += 1
            else:
                self.stagnation_count = 0

    def get_phase_stats(self, phase: TaskPhase) -> Dict[str, Any]:
        """获取阶段统计"""
        start_time = self.phase_start_time.get(phase, time.time())
        duration = time.time() - start_time

        return {
            "duration": duration,
            "total_actions": len(self.tool_history),
            "success_count": sum(1 for s in self.success_pattern if s),
            "error_count": self.error_count,
            "unique_tools": len(set(self.tool_history)),
            "most_used_tool": self._get_most_used_tool(),
            "consecutive_success": self.consecutive_success,
            "consecutive_errors": self.consecutive_errors,
            "stagnation_count": self.stagnation_count,
        }

    def _get_most_used_tool(self) -> Optional[str]:
        """获取最常用的工具"""
        if not self.tool_usage_count:
            return None
        return max(self.tool_usage_count, key=self.tool_usage_count.get)


class PhaseTransitionAlgorithm:
    """
    阶段转换算法

    核心决策逻辑
    """

    def __init__(
        self,
        criteria: Optional[PhaseDecisionCriteria] = None,
        enable_adaptive: bool = True,
    ):
        """
        初始化算法

        Args:
            criteria: 决策标准
            enable_adaptive: 启用自适应调整
        """
        self.criteria = criteria or PhaseDecisionCriteria()
        self.enable_adaptive = enable_adaptive
        self.transition_history: List[Dict] = []
        self.adaptive_factors: Dict[TaskPhase, float] = {}

        logger.info("PhaseTransitionAlgorithm initialized")

    def evaluate_transition(
        self,
        current_phase: TaskPhase,
        state_tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估是否应该转换阶段

        这是核心算法！

        Args:
            current_phase: 当前阶段
            state_tracker: 状态跟踪器

        Returns:
            建议的下一阶段，如果不需要转换则返回 None
        """
        # 获取当前阶段统计
        stats = state_tracker.get_phase_stats(current_phase)

        # 应用自适应因子
        if self.enable_adaptive:
            stats = self._apply_adaptive_factors(current_phase, stats)

        # 根据当前阶段调用不同的评估函数
        if current_phase == TaskPhase.EXPLORATION:
            return self._evaluate_exploration(stats, state_tracker)
        elif current_phase == TaskPhase.PLANNING:
            return self._evaluate_planning(stats, state_tracker)
        elif current_phase == TaskPhase.EXECUTION:
            return self._evaluate_execution(stats, state_tracker)
        elif current_phase == TaskPhase.REFINEMENT:
            return self._evaluate_refinement(stats, state_tracker)
        elif current_phase == TaskPhase.VERIFICATION:
            return self._evaluate_verification(stats, state_tracker)
        elif current_phase == TaskPhase.REPORTING:
            return self._evaluate_reporting(stats, state_tracker)

        return None

    def _apply_adaptive_factors(
        self,
        phase: TaskPhase,
        stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        应用自适应因子

        根据历史表现动态调整阈值
        """
        factor = self.adaptive_factors.get(phase, 1.0)

        if factor != 1.0:
            logger.info(f"Apply adaptive factor {factor:.2f} for phase {phase.value}")

        return stats

    # ==================== 各阶段的评估函数 ====================

    def _evaluate_exploration(
        self,
        stats: Dict[str, Any],
        tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估探索阶段

        转换到规划阶段的条件：
        1. 至少 N 次工具调用
        2. 成功率达到阈值
        3. 使用了足够的工具种类
        4. 没有严重错误
        """
        criteria = self.criteria.exploration_to_planning

        min_actions = criteria["min_actions"]
        min_success_rate = criteria["min_success_rate"]
        min_unique_tools = criteria["min_unique_tools"]

        # 条件 1: 最少调用次数
        if stats["total_actions"] < min_actions:
            self._log_decision(
                "exploration",
                "pending",
                f"Need {min_actions - stats['total_actions']} more actions",
            )
            return None

        # 条件 2: 成功率
        success_rate = stats["success_count"] / stats["total_actions"]
        if success_rate < min_success_rate:
            self._log_decision(
                "exploration",
                "pending",
                f"Success rate {success_rate:.1%} < {min_success_rate:.1%}",
            )
            return None

        # 条件 3: 工具多样性
        if stats["unique_tools"] < min_unique_tools:
            self._log_decision(
                "exploration",
                "pending",
                f"Need more diverse tools (currently {stats['unique_tools']})",
            )
            return None

        # 条件 4: 没有严重错误
        if stats["consecutive_errors"] >= 3:
            self._log_decision("exploration", "pending", "Too many consecutive errors")
            return None

        # 所有条件满足，可以转换
        self._log_decision(
            "exploration", "ready_to_transition", "All criteria met, ready for planning"
        )
        self._record_transition(TaskPhase.EXPLORATION, TaskPhase.PLANNING, stats)
        return TaskPhase.PLANNING

    def _evaluate_planning(
        self,
        stats: Dict[str, Any],
        tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估规划阶段

        转换到执行阶段的条件：
        1. 有足够的规划活动
        2. 或者耗时过长（防止过度规划）
        """
        criteria = self.criteria.planning_to_execution

        min_planning = criteria["min_planning_actions"]
        max_duration = criteria["max_duration"]

        # 条件 1: 足够的规划活动
        if stats["total_actions"] >= min_planning:
            self._log_decision(
                "planning",
                "ready_to_transition",
                f"Completed {min_planning} planning activities",
            )
            self._record_transition(TaskPhase.PLANNING, TaskPhase.EXECUTION, stats)
            return TaskPhase.EXECUTION

        # 条件 2: 防止过度规划
        if stats["duration"] > max_duration:
            self._log_decision(
                "planning",
                "ready_to_transition",
                f"Planning duration exceeded {max_duration}s",
            )
            self._record_transition(TaskPhase.PLANNING, TaskPhase.EXECUTION, stats)
            return TaskPhase.EXECUTION

        return None

    def _evaluate_execution(
        self,
        stats: Dict[str, Any],
        tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估执行阶段

        这个是分支决策：
        - 有错误 → 优化阶段
        - 无错误但达到上限 → 验证阶段
        - 停滞 detected →优化阶段
        """
        criteria = self.criteria.execution_branch

        max_actions = criteria["max_actions"]
        error_threshold = criteria["error_threshold"]
        stagnation_threshold = criteria["stagnation_threshold"]

        # 分支 1: 有错误需要优化
        error_rate = stats["error_count"] / stats["total_actions"]
        if stats["consecutive_errors"] >= 2 or error_rate >= error_threshold:
            self._log_decision(
                "execution",
                "to_refinement",
                f"Error rate {error_rate:.1%}, need refinement",
            )
            self._record_transition(TaskPhase.EXECUTION, TaskPhase.REFINEMENT, stats)
            return TaskPhase.REFINEMENT

        # 分支 2: 停滞检测
        if tracker.stagnation_count >= stagnation_threshold:
            self._log_decision(
                "execution",
                "to_refinement",
                f"Stagnation detected ({tracker.stagnation_count} consecutive same tool)",
            )
            self._record_transition(TaskPhase.EXECUTION, TaskPhase.REFINEMENT, stats)
            return TaskPhase.REFINEMENT

        # 分支 3: 执行完成或达到上限
        if stats["total_actions"] >= max_actions:
            self._log_decision(
                "execution", "to_verification", f"Completed {max_actions} actions"
            )
            self._record_transition(TaskPhase.EXECUTION, TaskPhase.VERIFICATION, stats)
            return TaskPhase.VERIFICATION

        return None

    def _evaluate_refinement(
        self,
        stats: Dict[str, Any],
        tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估优化阶段

        转换到验证阶段的条件：
        1. 完成足够的优化
        2. 连续成功，没有错误
        """
        criteria = self.criteria.refinement_to_verification

        min_optimize = criteria["min_optimize_actions"]
        error_free_count = criteria["error_free_count"]

        # 条件 1: 足够的优化活动
        if stats["total_actions"] < min_optimize:
            return None

        # 条件 2: 连续无错误
        if stats["consecutive_success"] < error_free_count:
            self._log_decision(
                "refinement",
                "pending",
                f"Need {error_free_count} consecutive successes",
            )
            return None

        # 满足条件，进入验证
        self._log_decision(
            "refinement",
            "ready_to_transition",
            f"Completed refinement with {stats['consecutive_success']} consecutive successes",
        )
        self._record_transition(TaskPhase.REFINEMENT, TaskPhase.VERIFICATION, stats)
        return TaskPhase.VERIFICATION

    def _evaluate_verification(
        self,
        stats: Dict[str, Any],
        tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估验证阶段

        转换到报告阶段的条件：
        1. 完成足够的验证活动
        2. 或者所有验证通过（如果有标记）
        """
        criteria = self.criteria.verification_to_reporting

        min_validate = criteria["min_validate_actions"]

        if stats["total_actions"] >= min_validate:
            self._log_decision(
                "verification",
                "ready_to_transition",
                f"Completed {min_validate} validation activities",
            )
            self._record_transition(TaskPhase.VERIFICATION, TaskPhase.REPORTING, stats)
            return TaskPhase.REPORTING

        return None

    def _evaluate_reporting(
        self,
        stats: Dict[str, Any],
        tracker: PhaseStateTracker,
    ) -> Optional[TaskPhase]:
        """
        评估报告阶段

        转换到完成的条件：
        1. 完成报告生成
        2. 或者至少有导出活动
        """
        criteria = self.criteria.reporting_to_complete

        min_export = criteria["min_export_actions"]

        if stats["total_actions"] >= min_export:
            self._log_decision(
                "reporting",
                "ready_to_transition",
                f"Completed reporting with {stats['total_actions']} activities",
            )
            self._record_transition(TaskPhase.REPORTING, TaskPhase.COMPLETE, stats)
            return TaskPhase.COMPLETE

        return None

    # ==================== 辅助方法 ====================

    def _log_decision(
        self,
        phase: str,
        status: str,
        reason: str,
    ):
        """记录决策日志"""
        logger.debug(f"Phase Decision [{phase} - {status}]: {reason}")

    def _record_transition(
        self,
        from_phase: TaskPhase,
        to_phase: TaskPhase,
        stats: Dict[str, Any],
    ):
        """记录转换历史"""
        self.transition_history.append(
            {
                "from_phase": from_phase.value,
                "to_phase": to_phase.value,
                "timestamp": time.time(),
                "stats": stats.copy(),
            }
        )

    def get_transition_history(self) -> List[Dict]:
        """获取转换历史"""
        return self.transition_history.copy()

    def adapt_criteria(
        self,
        phase: TaskPhase,
        factor: float,
    ):
        """
        自适应调整阈值

        根据性能动态调整标准
        """
        self.adaptive_factors[phase] = factor
        logger.info(f"Adapted criteria for phase {phase.value} by factor {factor:.2f}")


# ==================== 完整的 PhaseManager 实现（带算法） ====================


class PhaseManagerWithAlgorithm:
    """
    带完整算法的阶段管理器
    """

    def __init__(
        self,
        auto_phase_detection: bool = True,
        enable_phase_prompts: bool = True,
        enable_adaptive: bool = True,
    ):
        self.auto_phase_detection = auto_phase_detection
        self.enable_phase_prompts = enable_phase_prompts

        # 初始化组件
        self.current_phase = TaskPhase.EXPLORATION
        self.phase_history: List[TaskPhase] = []
        self.phase_start_time: Dict[TaskPhase, float] = {}

        # 状态跟踪器
        self.state_tracker = PhaseStateTracker()
        self.phase_start_time[self.current_phase] = time.time()

        # 转换算法
        self.algorithm = PhaseTransitionAlgorithm(enable_adaptive=enable_adaptive)

        logger.info(f"PhaseManager initialized, starting phase: {self.current_phase}")

    def set_phase(self, phase: TaskPhase, reason: str = ""):
        """手动设置阶段"""
        if self.current_phase != phase:
            old_phase = self.current_phase
            self.phase_history.append(self.current_phase)
            self.current_phase = phase
            self.phase_start_time[phase] = time.time()
            self.state_tracker.phase_start_time[phase] = time.time()

            logger.info(
                f"Phase transition: {old_phase.value} -> {phase.value} "
                f"(reason: {reason})"
            )

    def record_action(self, tool_name: str, success: bool):
        """记录动作"""
        # 更新状态跟踪器
        self.state_tracker.record_action(tool_name, success)

        # 尝试自动转换
        if self.auto_phase_detection:
            suggested_phase = self.algorithm.evaluate_transition(
                self.current_phase,
                self.state_tracker,
            )

            if suggested_phase and suggested_phase != self.current_phase:
                stats = self.state_tracker.get_phase_stats(self.current_phase)
                reason = f"Automatic: {stats}"
                self.set_phase(suggested_phase, reason)

    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            "current_phase": self.current_phase.value,
            "phase_history": [p.value for p in self.phase_history],
            "current_stats": self.state_tracker.get_phase_stats(self.current_phase),
            "transition_history": self.algorithm.get_transition_history(),
        }

    def get_phase_prompt(self) -> str:
        """获取阶段 prompt"""
        # 从 PhaseContext 获取
        from .phase_manager import PhaseContext

        return PhaseContext.PHASE_PROMPTS.get(
            self.current_phase, f"## Current Phase: {self.current_phase}"
        )

    def diagnose_state(self) -> Dict[str, Any]:
        """
        诊断当前状态

        返回详细的诊断信息，用于调试
        """
        current_stats = self.state_tracker.get_phase_stats(self.current_phase)

        # 检查每个转换条件
        logic = {
            phase: {
                "can_transition": False,
                "reason": "",
            }
            for phase in TaskPhase
            if phase != self.current_phase and phase != TaskPhase.COMPLETE
        }

        # 运行评估但不实际转换
        suggested = self.algorithm.evaluate_transition(
            self.current_phase,
            self.state_tracker,
        )

        return {
            "current_phase": self.current_phase.value,
            "current_stats": current_stats,
            "suggested_next_phase": suggested.value if suggested else None,
            "tool_history": self.state_tracker.tool_history[-10:],  # 最近10次
            "state_tracker": {
                "consecutive_success": self.state_tracker.consecutive_success,
                "consecutive_errors": self.state_tracker.consecutive_errors,
                "stagnation_count": self.state_tracker.stagnation_count,
                "error_count": self.state_tracker.error_count,
            },
        }


__all__ = [
    "TaskPhase",
    "PhaseDecisionCriteria",
    "PhaseStateTracker",
    "PhaseTransitionAlgorithm",
    "PhaseManagerWithAlgorithm",
]
