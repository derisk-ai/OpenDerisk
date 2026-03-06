"""
Skill Task Monitor - Skill任务监控器

解决关键问题：如何判断Skill任务完成？

提供的机制：
1. 显式触发：外部调用exit_skill()
2. 自动检测：基于Skill内置标记
3. 超时检测：执行时间过长自动退出
4. 目标检测：检测目标达成
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .skill_lifecycle import SkillLifecycleManager, SkillExitResult
    from .orchestrator import ContextLifecycleOrchestrator

logger = logging.getLogger(__name__)


class CompletionTrigger(str, Enum):
    """完成触发类型"""
    EXPLICIT = "explicit"           # 显式调用退出
    SKILL_MARKER = "skill_marker"   # Skill内置标记
    GOAL_ACHIEVED = "goal_achieved" # 目标达成
    TIMEOUT = "timeout"             # 超时
    ERROR = "error"                 # 错误导致退出
    NEW_SKILL = "new_skill"         # 新Skill加载触发
    PRESSURE = "pressure"           # 上下文压力


@dataclass
class SkillExecutionState:
    """Skill执行状态"""
    skill_name: str
    started_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    tools_used: Set[str] = field(default_factory=set)
    messages_count: int = 0
    errors_count: int = 0
    
    goals: List[str] = field(default_factory=list)
    completed_goals: List[str] = field(default_factory=list)
    
    exit_signals: List[str] = field(default_factory=list)
    is_completed: bool = False
    
    def add_tool_usage(self, tool_name: str) -> None:
        self.tools_used.add(tool_name)
        self.last_activity = datetime.now()
    
    def add_message(self) -> None:
        self.messages_count += 1
        self.last_activity = datetime.now()
    
    def mark_goal_completed(self, goal: str) -> None:
        if goal in self.goals and goal not in self.completed_goals:
            self.completed_goals.append(goal)


@dataclass
class CompletionCheckResult:
    """完成检测结果"""
    should_exit: bool
    trigger: CompletionTrigger
    reason: str
    confidence: float = 1.0
    summary: Optional[str] = None
    key_outputs: Optional[List[str]] = None


class SkillTaskMonitor:
    """
    Skill任务监控器
    
    监控Skill执行状态，判断任务完成时机
    """
    
    # Skill内容中标记任务完成的模式
    COMPLETION_MARKERS = [
        r"<task-complete\s*/>",
        r"<task-complete>(.*?)</task-complete>",
        r"<!-- TASK COMPLETE -->",
        r"\[TASK COMPLETE\]",
        r"任务完成",
        r"Task completed",
    ]
    
    # Skill内容中标记需要下一个Skill的模式
    HANDOFF_MARKERS = [
        r"<handoff\s+to=\"([^\"]+)\".*?/>",
        r"<next-skill>([^<]+)</next-skill>",
        r"<!-- NEXT SKILL: (\w+) -->",
    ]
    
    def __init__(
        self,
        orchestrator: "ContextLifecycleOrchestrator",
        timeout_seconds: int = 600,  # 10分钟超时
        auto_exit_on_marker: bool = True,
        auto_exit_on_goal_complete: bool = True,
    ):
        self._orchestrator = orchestrator
        self._timeout_seconds = timeout_seconds
        self._auto_exit_on_marker = auto_exit_on_marker
        self._auto_exit_on_goal_complete = auto_exit_on_goal_complete
        
        self._execution_states: Dict[str, SkillExecutionState] = {}
        self._completion_handlers: List[Callable] = []
        
        self._completion_patterns = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in self.COMPLETION_MARKERS
        ]
        self._handoff_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.HANDOFF_MARKERS
        ]
    
    def start_skill_monitoring(
        self,
        skill_name: str,
        goals: Optional[List[str]] = None,
    ) -> SkillExecutionState:
        """开始监控Skill执行"""
        state = SkillExecutionState(
            skill_name=skill_name,
            goals=goals or [],
        )
        self._execution_states[skill_name] = state
        
        logger.info(f"[TaskMonitor] Started monitoring: {skill_name}")
        return state
    
    def stop_skill_monitoring(self, skill_name: str) -> Optional[SkillExecutionState]:
        """停止监控"""
        return self._execution_states.pop(skill_name, None)
    
    def record_tool_usage(self, skill_name: str, tool_name: str) -> None:
        """记录工具使用"""
        state = self._execution_states.get(skill_name)
        if state:
            state.add_tool_usage(tool_name)
    
    def record_message(self, skill_name: str) -> None:
        """记录消息"""
        state = self._execution_states.get(skill_name)
        if state:
            state.add_message()
    
    def record_output(
        self,
        skill_name: str,
        output: str,
    ) -> List[CompletionCheckResult]:
        """
        记录Skill输出，检测完成信号
        
        这是最关键的检测方法
        """
        state = self._execution_states.get(skill_name)
        if not state:
            return []
        
        results = []
        
        # 1. 检测完成标记
        if self._auto_exit_on_marker:
            marker_result = self._check_completion_markers(skill_name, output)
            if marker_result:
                results.append(marker_result)
        
        # 2. 检测交接标记（需要另一个Skill）
        handoff_result = self._check_handoff_markers(skill_name, output)
        if handoff_result:
            results.append(handoff_result)
        
        # 3. 检测目标完成
        if self._auto_exit_on_goal_complete and state.goals:
            goal_result = self._check_goal_completion(skill_name, output)
            if goal_result:
                results.append(goal_result)
        
        return results
    
    def check_should_exit(self, skill_name: str) -> Optional[CompletionCheckResult]:
        """
        检查Skill是否应该退出
        
        综合检查各种条件
        """
        state = self._execution_states.get(skill_name)
        if not state:
            return None
        
        # 1. 检查超时
        elapsed = (datetime.now() - state.started_at).total_seconds()
        if elapsed > self._timeout_seconds:
            return CompletionCheckResult(
                should_exit=True,
                trigger=CompletionTrigger.TIMEOUT,
                reason=f"Skill exceeded timeout of {self._timeout_seconds}s",
                confidence=1.0,
            )
        
        # 2. 检查是否已标记完成
        if state.is_completed:
            return CompletionCheckResult(
                should_exit=True,
                trigger=CompletionTrigger.SKILL_MARKER,
                reason="Skill marked as completed",
                confidence=1.0,
            )
        
        # 3. 检查目标完成
        if state.goals and len(state.completed_goals) == len(state.goals):
            return CompletionCheckResult(
                should_exit=True,
                trigger=CompletionTrigger.GOAL_ACHIEVED,
                reason="All goals completed",
                confidence=0.9,
            )
        
        # 4. 检查错误次数
        if state.errors_count >= 5:
            return CompletionCheckResult(
                should_exit=True,
                trigger=CompletionTrigger.ERROR,
                reason=f"Too many errors: {state.errors_count}",
                confidence=0.8,
            )
        
        return None
    
    async def auto_exit_if_needed(
        self,
        skill_name: str,
    ) -> Optional["SkillExitResult"]:
        """
        自动退出（如果需要）
        
        返回退出结果，或None
        """
        check_result = self.check_should_exit(skill_name)
        
        if check_result and check_result.should_exit:
            from .skill_lifecycle import ExitTrigger
            
            trigger_map = {
                CompletionTrigger.TIMEOUT: ExitTrigger.TIMEOUT,
                CompletionTrigger.SKILL_MARKER: ExitTrigger.TASK_COMPLETE,
                CompletionTrigger.GOAL_ACHIEVED: ExitTrigger.TASK_COMPLETE,
                CompletionTrigger.ERROR: ExitTrigger.ERROR_OCCURRED,
            }
            
            state = self._execution_states.get(skill_name)
            summary = check_result.summary or f"Auto-exit: {check_result.reason}"
            
            result = await self._orchestrator.complete_skill(
                skill_name=skill_name,
                task_summary=summary,
                key_outputs=list(state.tools_used) if state else None,
                trigger=trigger_map.get(check_result.trigger, ExitTrigger.TASK_COMPLETE),
            )
            
            self.stop_skill_monitoring(skill_name)
            
            # 调用完成处理器
            for handler in self._completion_handlers:
                try:
                    await handler(skill_name, check_result, result)
                except Exception as e:
                    logger.error(f"[TaskMonitor] Handler error: {e}")
            
            return result
        
        return None
    
    def _check_completion_markers(
        self,
        skill_name: str,
        output: str,
    ) -> Optional[CompletionCheckResult]:
        """检查完成标记"""
        for pattern in self._completion_patterns:
            match = pattern.search(output)
            if match:
                state = self._execution_states.get(skill_name)
                if state:
                    state.is_completed = True
                
                summary = None
                if match.groups():
                    summary = match.group(1).strip()
                
                return CompletionCheckResult(
                    should_exit=True,
                    trigger=CompletionTrigger.SKILL_MARKER,
                    reason="Found completion marker in output",
                    confidence=1.0,
                    summary=summary,
                )
        
        return None
    
    def _check_handoff_markers(
        self,
        skill_name: str,
        output: str,
    ) -> Optional[CompletionCheckResult]:
        """检查交接标记"""
        for pattern in self._handoff_patterns:
            match = pattern.search(output)
            if match:
                next_skill = match.group(1).strip()
                
                return CompletionCheckResult(
                    should_exit=True,
                    trigger=CompletionTrigger.NEW_SKILL,
                    reason=f"Handoff requested to: {next_skill}",
                    confidence=1.0,
                    summary=f"Handoff to {next_skill}",
                    key_outputs=[f"next_skill:{next_skill}"],
                )
        
        return None
    
    def _check_goal_completion(
        self,
        skill_name: str,
        output: str,
    ) -> Optional[CompletionCheckResult]:
        """检查目标完成"""
        state = self._execution_states.get(skill_name)
        if not state or not state.goals:
            return None
        
        for goal in state.goals:
            if goal not in state.completed_goals:
                # 简单检查：output中是否包含goal关键词
                # 实际应用中可以用LLM判断
                if goal.lower() in output.lower():
                    state.mark_goal_completed(goal)
        
        if len(state.completed_goals) == len(state.goals):
            return CompletionCheckResult(
                should_exit=True,
                trigger=CompletionTrigger.GOAL_ACHIEVED,
                reason="All goals achieved",
                confidence=0.85,
                summary=f"Completed goals: {', '.join(state.completed_goals)}",
            )
        
        return None
    
    def add_completion_handler(
        self,
        handler: Callable,
    ) -> None:
        """添加完成处理器"""
        self._completion_handlers.append(handler)
    
    def get_execution_state(self, skill_name: str) -> Optional[SkillExecutionState]:
        """获取执行状态"""
        return self._execution_states.get(skill_name)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_monitoring": len(self._execution_states),
            "skills": list(self._execution_states.keys()),
            "timeout_seconds": self._timeout_seconds,
        }


class SkillTransitionManager:
    """
    Skill转换管理器
    
    管理多Skill任务的转换逻辑
    """
    
    def __init__(
        self,
        orchestrator: "ContextLifecycleOrchestrator",
        monitor: SkillTaskMonitor,
    ):
        self._orchestrator = orchestrator
        self._monitor = monitor
        
        self._skill_sequence: List[str] = []
        self._current_index: int = 0
    
    def set_skill_sequence(self, skills: List[str]) -> None:
        """设置Skill执行序列"""
        self._skill_sequence = skills
        self._current_index = 0
    
    def get_next_skill(self) -> Optional[str]:
        """获取下一个要执行的Skill"""
        if self._current_index < len(self._skill_sequence) - 1:
            return self._skill_sequence[self._current_index + 1]
        return None
    
    def advance_to_next(self) -> Optional[str]:
        """前进到下一个Skill"""
        self._current_index += 1
        if self._current_index < len(self._skill_sequence):
            return self._skill_sequence[self._current_index]
        return None
    
    async def handle_skill_transition(
        self,
        current_skill: str,
        result: "SkillExitResult",
    ) -> Optional[str]:
        """
        处理Skill转换
        
        返回下一个Skill名称（如果有）
        """
        from .skill_lifecycle import ExitTrigger
        
        # 检查是否有Handoff指定的下一个Skill
        if result.key_outputs:
            for output in result.key_outputs:
                if output.startswith("next_skill:"):
                    next_skill = output.split(":", 1)[1]
                    logger.info(f"[Transition] Handoff to: {next_skill}")
                    return next_skill
        
        # 检查序列中是否有下一个
        next_in_sequence = self.get_next_skill()
        if next_in_sequence:
            logger.info(f"[Transition] Next in sequence: {next_in_sequence}")
            return next_in_sequence
        
        return None
    
    def get_current_position(self) -> tuple:
        """获取当前位置"""
        return (self._current_index, len(self._skill_sequence))


# ============================================================
# 使用示例：集成到Agent执行流程
# ============================================================

async def example_integration():
    """
    展示如何在Agent执行流程中集成
    """
    from .orchestrator import create_context_lifecycle
    
    # 创建编排器
    orchestrator = create_context_lifecycle()
    await orchestrator.initialize(session_id="example")
    
    # 创建监控器
    monitor = SkillTaskMonitor(
        orchestrator=orchestrator,
        timeout_seconds=300,
        auto_exit_on_marker=True,
    )
    
    # 创建转换管理器
    transition_manager = SkillTransitionManager(orchestrator, monitor)
    transition_manager.set_skill_sequence([
        "requirement_analysis",
        "design",
        "implementation",
        "testing",
    ])
    
    # 执行第一个Skill
    current_skill = "requirement_analysis"
    
    # 准备上下文
    await orchestrator.prepare_skill_context(
        skill_name=current_skill,
        skill_content="... skill content with <task-complete/> marker ...",
    )
    
    # 开始监控
    monitor.start_skill_monitoring(
        skill_name=current_skill,
        goals=["Understand requirements", "Write spec"],
    )
    
    # 模拟执行过程
    outputs = [
        "Working on understanding requirements...",
        "Analyzed 3 features",
        "Writing specification document...",
        "<task-complete>Requirements analyzed and documented</task-complete>",
    ]
    
    for output in outputs:
        # 记录输出
        results = monitor.record_output(current_skill, output)
        
        # 检查是否应该退出
        for check_result in results:
            if check_result.should_exit:
                exit_result = await orchestrator.complete_skill(
                    skill_name=current_skill,
                    task_summary=check_result.summary or "Task completed",
                )
                
                # 处理转换
                next_skill = await transition_manager.handle_skill_transition(
                    current_skill, exit_result
                )
                
                if next_skill:
                    print(f"Transitioning to: {next_skill}")
                    # 加载下一个Skill...
                
                break