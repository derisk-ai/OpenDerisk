"""
阶段转换检测器 (Phase Transition Detector)

通过分析工具调用序列和执行结果判断任务阶段转换。

阶段定义：
- EXPLORATION: 探索期 - 需求分析、调研
- DEVELOPMENT: 开发期 - 编码、实现
- DEBUGGING: 调试期 - 修复问题
- REFINEMENT: 优化期 - 改进、完善
- DELIVERY: 收尾期 - 总结、交付
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .hierarchical_context_index import TaskPhase

if TYPE_CHECKING:
    from derisk.agent import ActionOutput

logger = logging.getLogger(__name__)


class PhaseTransitionDetector:
    """
    阶段转换检测器
    
    通过分析工具调用序列和执行结果判断任务阶段转换
    
    使用示例:
        detector = PhaseTransitionDetector()
        
        # 每次执行后调用
        new_phase = detector.detect_phase(action_out)
        if new_phase:
            print(f"Phase transition detected: {new_phase.value}")
    """
    
    PHASE_KEYWORDS: Dict[TaskPhase, List[str]] = {
        TaskPhase.EXPLORATION: [
            "探索", "了解", "分析", "调研", "explore", "understand", "analyze",
            "搜索", "查询", "查看", "search", "query", "read", "investigate",
            "需求", "requirement", "研究", "research",
        ],
        TaskPhase.DEVELOPMENT: [
            "开发", "实现", "编写", "创建", "develop", "implement", "write", "create",
            "修改", "更新", "edit", "update", "执行", "execute", "编码", "coding",
            "构建", "build", "部署", "deploy",
        ],
        TaskPhase.DEBUGGING: [
            "调试", "修复", "解决", "debug", "fix", "solve", "troubleshoot",
            "错误", "异常", "失败", "error", "exception", "failed", "bug",
            "问题", "issue", "排查", "diagnose",
        ],
        TaskPhase.REFINEMENT: [
            "优化", "改进", "完善", "optimize", "improve", "refine",
            "重构", "清理", "refactor", "clean", "增强", "enhance",
            "性能", "performance", "调整", "adjust",
        ],
        TaskPhase.DELIVERY: [
            "完成", "交付", "总结", "complete", "deliver", "summary",
            "报告", "文档", "report", "document", "terminate", "结束",
            "验收", "acceptance", "测试通过", "test passed",
        ],
    }
    
    TOOL_PATTERNS: Dict[TaskPhase, List[str]] = {
        TaskPhase.EXPLORATION: [
            "read_file", "search", "query", "explore", "list_files",
            "check_status", "analyze", "investigate",
        ],
        TaskPhase.DEVELOPMENT: [
            "write_file", "execute_code", "bash", "edit_file",
            "create_file", "build", "deploy",
        ],
        TaskPhase.DEBUGGING: [
            "bash", "read_file", "execute_code", "debug",
            "fix", "test", "check_logs",
        ],
        TaskPhase.REFINEMENT: [
            "edit_file", "execute_code", "optimize",
            "refactor", "improve", "enhance",
        ],
        TaskPhase.DELIVERY: [
            "write_file", "terminate", "summarize",
            "generate_report", "create_document",
        ],
    }
    
    PHASE_SEQUENCE: List[TaskPhase] = [
        TaskPhase.EXPLORATION,
        TaskPhase.DEVELOPMENT,
        TaskPhase.DEBUGGING,
        TaskPhase.REFINEMENT,
        TaskPhase.DELIVERY,
    ]
    
    def __init__(self, history_window: int = 5, threshold: float = 0.6):
        """
        初始化检测器
        
        Args:
            history_window: 历史窗口大小
            threshold: 阶段转换阈值
        """
        self.history_window = history_window
        self.threshold = threshold
        
        self._tool_history: deque = deque(maxlen=history_window)
        self._phase_scores: Dict[TaskPhase, float] = {
            phase: 0.0 for phase in TaskPhase
        }
        self._current_phase: TaskPhase = TaskPhase.EXPLORATION
        self._phase_history: List[Tuple[TaskPhase, float]] = []
        self._transition_count: Dict[TaskPhase, int] = {
            phase: 0 for phase in TaskPhase
        }
    
    def detect_phase(self, action_out: Any) -> Optional[TaskPhase]:
        """
        检测当前阶段
        
        Args:
            action_out: 动作输出
            
        Returns:
            检测到的新阶段，如果未转换返回None
        """
        tool_name = self._extract_tool_name(action_out)
        if tool_name:
            self._tool_history.append(tool_name)
        
        self._update_phase_scores(action_out)
        
        new_phase = self._determine_phase()
        
        if new_phase and new_phase != self._current_phase:
            if self._is_valid_transition(new_phase):
                logger.info(
                    f"[PhaseTransitionDetector] Phase transition: "
                    f"{self._current_phase.value} -> {new_phase.value}"
                )
                self._phase_history.append((self._current_phase, self._phase_scores.copy()))
                self._current_phase = new_phase
                self._transition_count[new_phase] += 1
                return new_phase
        
        return None
    
    def _extract_tool_name(self, action_out: Any) -> Optional[str]:
        """提取工具名称"""
        tool_name = getattr(action_out, "name", None) or getattr(action_out, "action", None)
        if tool_name:
            return tool_name.lower()
        return None
    
    def _update_phase_scores(self, action_out: Any) -> None:
        """更新阶段分数"""
        content = getattr(action_out, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        content_lower = content.lower()
        
        tool_name = self._extract_tool_name(action_out)
        success = getattr(action_out, "is_exe_success", True)
        
        for phase, keywords in self.PHASE_KEYWORDS.items():
            keyword_matches = sum(1 for kw in keywords if kw in content_lower)
            self._phase_scores[phase] += keyword_matches * 0.05
        
        for phase, tools in self.TOOL_PATTERNS.items():
            if tool_name and tool_name in [t.lower() for t in tools]:
                self._phase_scores[phase] += 0.15
        
        if success:
            self._phase_scores[TaskPhase.DEVELOPMENT] += 0.05
        else:
            self._phase_scores[TaskPhase.DEBUGGING] += 0.1
        
        total = sum(self._phase_scores.values())
        if total > 0:
            for phase in self._phase_scores:
                self._phase_scores[phase] /= total
    
    def _determine_phase(self) -> Optional[TaskPhase]:
        """确定当前阶段"""
        max_phase = max(self._phase_scores.items(), key=lambda x: x[1])
        
        if max_phase[1] > self.threshold:
            return max_phase[0]
        
        return None
    
    def _is_valid_transition(self, new_phase: TaskPhase) -> bool:
        """检查阶段转换是否有效"""
        current_idx = self.PHASE_SEQUENCE.index(self._current_phase)
        new_idx = self.PHASE_SEQUENCE.index(new_phase)
        
        return new_idx >= current_idx - 1
    
    def get_current_phase(self) -> TaskPhase:
        """获取当前阶段"""
        return self._current_phase
    
    def get_phase_scores(self) -> Dict[str, float]:
        """获取阶段分数"""
        return {
            phase.value: score
            for phase, score in self._phase_scores.items()
        }
    
    def get_phase_history(self) -> List[Dict[str, Any]]:
        """获取阶段历史"""
        return [
            {
                "phase": phase.value,
                "scores": {p.value: s for p, s in scores.items()},
            }
            for phase, scores in self._phase_history
        ]
    
    def force_phase(self, phase: TaskPhase) -> None:
        """强制设置阶段"""
        logger.info(f"[PhaseTransitionDetector] Force phase: {phase.value}")
        self._current_phase = phase
        self._transition_count[phase] += 1
    
    def suggest_next_phase(self) -> Optional[TaskPhase]:
        """建议下一个阶段"""
        current_idx = self.PHASE_SEQUENCE.index(self._current_phase)
        if current_idx < len(self.PHASE_SEQUENCE) - 1:
            return self.PHASE_SEQUENCE[current_idx + 1]
        return None
    
    def reset(self) -> None:
        """重置状态"""
        self._tool_history.clear()
        self._phase_scores = {phase: 0.0 for phase in TaskPhase}
        self._current_phase = TaskPhase.EXPLORATION
        self._phase_history.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "current_phase": self._current_phase.value,
            "phase_scores": self.get_phase_scores(),
            "transition_counts": {
                phase.value: count
                for phase, count in self._transition_count.items()
            },
            "history_length": len(self._phase_history),
            "tool_history_size": len(self._tool_history),
        }


class PhaseAwareCompactor:
    """
    阶段感知压缩器
    
    根据任务阶段决定压缩策略
    """
    
    PHASE_COMPACTION_PRIORITY: Dict[TaskPhase, List[str]] = {
        TaskPhase.EXPLORATION: ["low", "medium"],
        TaskPhase.DEVELOPMENT: ["low"],
        TaskPhase.DEBUGGING: ["low", "medium"],
        TaskPhase.REFINEMENT: ["low"],
        TaskPhase.DELIVERY: ["low", "medium", "high"],
    }
    
    def __init__(self, detector: PhaseTransitionDetector):
        self.detector = detector
    
    def get_compaction_priorities(self) -> List[str]:
        """获取当前阶段应压缩的优先级"""
        current_phase = self.detector.get_current_phase()
        return self.PHASE_COMPACTION_PRIORITY.get(current_phase, ["low"])
    
    def should_compact(self, priority: str) -> bool:
        """判断是否应该压缩"""
        priorities = self.get_compaction_priorities()
        return priority in priorities