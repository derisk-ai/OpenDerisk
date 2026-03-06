"""
内容优先级分类器 (Content Prioritizer)

基于多维度判断内容优先级：
1. 消息角色
2. 内容关键词
3. 工具类型
4. 执行状态
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

from .hierarchical_context_index import ContentPriority

if TYPE_CHECKING:
    from derisk.agent import AgentMessage, ActionOutput

logger = logging.getLogger(__name__)


class ContentPrioritizer:
    """
    内容优先级分类器
    
    使用示例:
        prioritizer = ContentPrioritizer()
        
        # 分类消息
        priority = prioritizer.classify_message(msg)
        
        # 获取压缩因子
        factor = prioritizer.get_compression_factor(priority)
    """
    
    CRITICAL_KEYWORDS: Set[str] = {
        "目标", "任务", "goal", "task", "objective",
        "决定", "决策", "decision", "decided",
        "重要", "critical", "important", "must",
        "完成", "completed", "done", "finish",
        "结果", "result", "outcome",
        "关键", "key", "core",
    }
    
    HIGH_KEYWORDS: Set[str] = {
        "步骤", "step", "阶段", "phase",
        "成功", "success", "succeeded",
        "执行", "executed", "ran",
        "输出", "output", "结果", "result",
        "实现", "implement", "implementing",
        "修复", "fix", "fixed",
    }
    
    LOW_KEYWORDS: Set[str] = {
        "重试", "retry", "retrying",
        "探索", "explore", "exploring", "尝试", "try",
        "失败", "failed", "error",
        "等待", "waiting", "pending",
        "调度", "schedule", "scheduled",
        "重复", "duplicate", "repeat",
    }
    
    TOOL_PRIORITY_MAP: Dict[str, ContentPriority] = {
        "plan": ContentPriority.HIGH,
        "execute_code": ContentPriority.HIGH,
        "write_file": ContentPriority.HIGH,
        "make_decision": ContentPriority.CRITICAL,
        "think": ContentPriority.CRITICAL,
        "analyze": ContentPriority.HIGH,
        
        "read_file": ContentPriority.MEDIUM,
        "search": ContentPriority.MEDIUM,
        "query": ContentPriority.MEDIUM,
        "bash": ContentPriority.MEDIUM,
        "list_files": ContentPriority.MEDIUM,
        
        "explore": ContentPriority.LOW,
        "retry": ContentPriority.LOW,
        "schedule": ContentPriority.LOW,
        "check_status": ContentPriority.LOW,
    }
    
    def __init__(self):
        self._priority_history: Dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
    
    def classify_message(self, msg: Any) -> ContentPriority:
        """
        分类消息优先级
        
        综合考虑：
        1. 角色权重 (user/assistant > system > tool)
        2. 内容关键词
        3. 关联的工具类型
        4. 执行状态
        """
        score = 0.5
        
        role = getattr(msg, "role", "") or ""
        content = getattr(msg, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        
        role = role.lower()
        if role in ["user", "human"]:
            score += 0.2
        elif role in ["assistant", "agent"]:
            score += 0.15
        elif role == "system":
            score += 0.1
        elif role in ["tool", "function"]:
            score -= 0.1
        
        content_lower = content.lower()
        
        critical_matches = sum(1 for kw in self.CRITICAL_KEYWORDS if kw in content_lower)
        high_matches = sum(1 for kw in self.HIGH_KEYWORDS if kw in content_lower)
        low_matches = sum(1 for kw in self.LOW_KEYWORDS if kw in content_lower)
        
        score += critical_matches * 0.1
        score += high_matches * 0.05
        score -= low_matches * 0.05
        
        tool_name = ""
        context = getattr(msg, "context", None)
        if context and isinstance(context, dict):
            tool_name = context.get("tool_name", "") or context.get("action", "")
        
        if tool_name and tool_name in self.TOOL_PRIORITY_MAP:
            priority = self.TOOL_PRIORITY_MAP[tool_name]
            if priority == ContentPriority.CRITICAL:
                score += 0.3
            elif priority == ContentPriority.HIGH:
                score += 0.2
            elif priority == ContentPriority.LOW:
                score -= 0.2
        
        if context and isinstance(context, dict):
            success = context.get("success", True)
            if not success:
                score -= 0.1
            
            retry_count = context.get("retry_count", 0)
            score -= retry_count * 0.05
        
        priority = self._score_to_priority(score)
        self._priority_history[priority.value] += 1
        
        return priority
    
    def classify_message_from_action(self, action_out: Any) -> ContentPriority:
        """
        从 ActionOutput 分类优先级
        """
        action_name = getattr(action_out, "name", "") or getattr(action_out, "action", "") or ""
        content = getattr(action_out, "content", "") or ""
        success = getattr(action_out, "is_exe_success", True)
        
        score = 0.5
        
        if action_name in self.TOOL_PRIORITY_MAP:
            priority = self.TOOL_PRIORITY_MAP[action_name]
            if priority == ContentPriority.CRITICAL:
                score += 0.3
            elif priority == ContentPriority.HIGH:
                score += 0.2
            elif priority == ContentPriority.LOW:
                score -= 0.2
        
        if success:
            score += 0.1
        else:
            score -= 0.15
        
        content_lower = content.lower() if isinstance(content, str) else ""
        critical_matches = sum(1 for kw in self.CRITICAL_KEYWORDS if kw in content_lower)
        score += critical_matches * 0.1
        
        return self._score_to_priority(score)
    
    def _score_to_priority(self, score: float) -> ContentPriority:
        """将分数映射到优先级"""
        if score >= 0.8:
            return ContentPriority.CRITICAL
        elif score >= 0.6:
            return ContentPriority.HIGH
        elif score >= 0.4:
            return ContentPriority.MEDIUM
        else:
            return ContentPriority.LOW
    
    def get_compression_factor(self, priority: ContentPriority) -> float:
        """
        获取压缩因子
        
        CRITICAL: 几乎不压缩 (保留90%)
        HIGH: 轻度压缩 (保留70%)
        MEDIUM: 中度压缩 (保留50%)
        LOW: 高度压缩 (保留20%)
        """
        factors = {
            ContentPriority.CRITICAL: 0.9,
            ContentPriority.HIGH: 0.7,
            ContentPriority.MEDIUM: 0.5,
            ContentPriority.LOW: 0.2,
        }
        return factors.get(priority, 0.5)
    
    def get_should_compact(self, priority: ContentPriority) -> bool:
        """
        判断是否应该压缩
        """
        return priority != ContentPriority.CRITICAL
    
    def get_compaction_order(self) -> list:
        """
        获取压缩顺序（从最早压缩到最晚）
        """
        return [
            ContentPriority.LOW,
            ContentPriority.MEDIUM,
            ContentPriority.HIGH,
        ]
    
    def register_tool_priority(
        self,
        tool_name: str,
        priority: ContentPriority,
    ) -> None:
        """注册工具优先级"""
        self.TOOL_PRIORITY_MAP[tool_name] = priority
        logger.debug(f"[ContentPrioritizer] Registered tool '{tool_name}' as {priority.value}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = sum(self._priority_history.values())
        if total == 0:
            return {
                "total": 0,
                "distribution": {},
            }
        
        return {
            "total": total,
            "distribution": {
                k: {
                    "count": v,
                    "percentage": f"{v / total * 100:.1f}%",
                }
                for k, v in self._priority_history.items()
            },
        }
    
    def reset_statistics(self) -> None:
        """重置统计"""
        self._priority_history = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }