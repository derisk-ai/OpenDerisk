"""
分层上下文索引核心数据结构

定义章节(Chapter)、节(Section)等核心数据模型。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
import json


class TaskPhase(str, Enum):
    """任务阶段"""
    EXPLORATION = "exploration"      # 探索期：需求分析、调研
    DEVELOPMENT = "development"      # 开发期：编码、实现
    DEBUGGING = "debugging"          # 调试期：修复问题
    REFINEMENT = "refinement"        # 优化期：改进、完善
    DELIVERY = "delivery"            # 收尾期：总结、交付


class ContentPriority(str, Enum):
    """内容优先级"""
    CRITICAL = "critical"    # 关键：任务目标、重要决策
    HIGH = "high"           # 高：任务推进步骤、关键结果
    MEDIUM = "medium"       # 中：工具调用、中间结果
    LOW = "low"             # 低：系统调度、探索、重复执行


@dataclass
class Section:
    """
    节 - 具体执行步骤
    
    每个Section代表一个具体的执行步骤，
    完整内容可归档到文件系统，只保留摘要。
    """
    section_id: str
    step_name: str
    content: str
    detail_ref: Optional[str] = None
    priority: ContentPriority = ContentPriority.MEDIUM
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_index_entry(self) -> str:
        """生成索引用的简短条目"""
        content_preview = self.content[:100] if len(self.content) > 100 else self.content
        return f"[{self.section_id[:8]}] {self.step_name}: {content_preview}..."
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "section_id": self.section_id,
            "step_name": self.step_name,
            "content": self.content,
            "detail_ref": self.detail_ref,
            "priority": self.priority.value if isinstance(self.priority, ContentPriority) else self.priority,
            "timestamp": self.timestamp,
            "tokens": self.tokens,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Section":
        """从字典创建"""
        priority = data.get("priority", "medium")
        if isinstance(priority, str):
            priority = ContentPriority(priority)
        
        return cls(
            section_id=data["section_id"],
            step_name=data["step_name"],
            content=data["content"],
            detail_ref=data.get("detail_ref"),
            priority=priority,
            timestamp=data.get("timestamp", datetime.now().timestamp()),
            tokens=data.get("tokens", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Chapter:
    """
    章 - 任务阶段
    
    每个Chapter代表一个任务阶段，
    包含多个Section（具体步骤）。
    """
    chapter_id: str
    phase: TaskPhase
    title: str
    summary: str = ""
    sections: List[Section] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    tokens: int = 0
    is_compacted: bool = False
    
    def get_section_index(self) -> str:
        """获取节目录（二级索引）"""
        lines = [f"## {self.title} ({self.phase.value})"]
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        lines.append("\nSections:")
        for sec in self.sections:
            lines.append(f"  - {sec.to_index_entry()}")
        return "\n".join(lines)
    
    def to_chapter_summary(self) -> str:
        """生成章节总结（一级索引）"""
        summary_preview = self.summary[:200] if len(self.summary) > 200 else self.summary
        return f"[{self.chapter_id[:8]}] {self.title} ({self.phase.value}): {summary_preview}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        phase_value = self.phase.value if isinstance(self.phase, TaskPhase) else self.phase
        return {
            "chapter_id": self.chapter_id,
            "phase": phase_value,
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections],
            "created_at": self.created_at,
            "tokens": self.tokens,
            "is_compacted": self.is_compacted,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chapter":
        """从字典创建"""
        phase = data.get("phase", "exploration")
        if isinstance(phase, str):
            phase = TaskPhase(phase)
        
        sections = [Section.from_dict(s) for s in data.get("sections", [])]
        
        return cls(
            chapter_id=data["chapter_id"],
            phase=phase,
            title=data["title"],
            summary=data.get("summary", ""),
            sections=sections,
            created_at=data.get("created_at", datetime.now().timestamp()),
            tokens=data.get("tokens", 0),
            is_compacted=data.get("is_compacted", False),
        )


@dataclass
class HierarchicalContextConfig:
    """
    分层上下文配置
    
    控制章节索引的行为和阈值。
    """
    max_chapter_tokens: int = 10000
    max_section_tokens: int = 2000
    recent_chapters_full: int = 2      # 最近2章完整展示
    middle_chapters_index: int = 3      # 中间3章展示节目录
    early_chapters_summary: int = 5     # 早期章节只展示总结
    
    priority_thresholds: Dict[str, int] = field(default_factory=lambda: {
        "critical": 50000,
        "high": 20000,
        "medium": 5000,
        "low": 1000,
    })
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "max_chapter_tokens": self.max_chapter_tokens,
            "max_section_tokens": self.max_section_tokens,
            "recent_chapters_full": self.recent_chapters_full,
            "middle_chapters_index": self.middle_chapters_index,
            "early_chapters_summary": self.early_chapters_summary,
            "priority_thresholds": self.priority_thresholds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HierarchicalContextConfig":
        """从字典创建"""
        return cls(
            max_chapter_tokens=data.get("max_chapter_tokens", 10000),
            max_section_tokens=data.get("max_section_tokens", 2000),
            recent_chapters_full=data.get("recent_chapters_full", 2),
            middle_chapters_index=data.get("middle_chapters_index", 3),
            early_chapters_summary=data.get("early_chapters_summary", 5),
            priority_thresholds=data.get("priority_thresholds", {
                "critical": 50000,
                "high": 20000,
                "medium": 5000,
                "low": 1000,
            }),
        )