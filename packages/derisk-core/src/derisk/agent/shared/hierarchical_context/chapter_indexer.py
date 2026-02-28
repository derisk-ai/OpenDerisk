"""
章节索引器 (Chapter Indexer)

管理任务执行的结构化索引，将历史按章节组织。

核心职责：
1. 创建和管理章节（任务阶段）
2. 记录节（执行步骤）到章节
3. 自动将完整内容归档到文件系统
4. 生成分层上下文用于prompt
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .hierarchical_context_index import (
    Chapter,
    ContentPriority,
    HierarchicalContextConfig,
    Section,
    TaskPhase,
)

if TYPE_CHECKING:
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem

logger = logging.getLogger(__name__)


class ChapterIndexer:
    """
    章节索引器 - 管理任务执行的结构化索引
    
    使用示例:
        indexer = ChapterIndexer(file_system=afs)
        
        # 创建章节（任务阶段）
        chapter = indexer.create_chapter(
            phase=TaskPhase.EXPLORATION,
            title="需求分析",
            description="分析用户需求"
        )
        
        # 添加节（执行步骤）
        section = await indexer.add_section(
            step_name="read_requirements",
            content="读取需求文档...",
            priority=ContentPriority.HIGH,
        )
        
        # 获取分层上下文
        context = indexer.get_context_for_prompt(token_budget=5000)
        
        # 回溯历史
        content = await indexer.recall_section(section_id="section_1")
    """
    
    def __init__(
        self,
        file_system: Optional[AgentFileSystem] = None,
        config: Optional[HierarchicalContextConfig] = None,
        session_id: Optional[str] = None,
    ):
        self.file_system = file_system
        self.config = config or HierarchicalContextConfig()
        self.session_id = session_id or "default"
        
        self._chapters: List[Chapter] = []
        self._current_chapter: Optional[Chapter] = None
        self._section_counter: int = 0
        self._chapter_counter: int = 0
        
        self._section_index: Dict[str, Section] = {}
        self._chapter_index: Dict[str, Chapter] = {}
    
    def create_chapter(
        self,
        phase: TaskPhase,
        title: str,
        description: str = "",
    ) -> Chapter:
        """
        创建新章节（任务阶段开始）
        
        Args:
            phase: 任务阶段
            title: 章节标题
            description: 章节描述
            
        Returns:
            创建的章节对象
        """
        self._chapter_counter += 1
        chapter_id = f"chapter_{self._chapter_counter}_{int(time.time())}"
        
        chapter = Chapter(
            chapter_id=chapter_id,
            phase=phase,
            title=title,
            summary=description or f"Start {phase.value} phase",
        )
        
        self._chapters.append(chapter)
        self._chapter_index[chapter_id] = chapter
        self._current_chapter = chapter
        
        logger.info(f"[ChapterIndexer] Created chapter: {chapter_id} ({phase.value})")
        
        return chapter
    
    async def add_section(
        self,
        step_name: str,
        content: str,
        priority: ContentPriority = ContentPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Section:
        """
        添加节（执行步骤）到当前章节
        
        完整内容归档到文件系统，只保留摘要
        
        Args:
            step_name: 步骤名称
            content: 步骤内容
            priority: 内容优先级
            metadata: 元数据
            
        Returns:
            创建的节对象
        """
        if not self._current_chapter:
            self.create_chapter(
                phase=TaskPhase.EXPLORATION,
                title="Default Phase",
            )
        
        self._section_counter += 1
        section_id = f"section_{self._section_counter}_{int(time.time())}"
        
        tokens = len(content) // 4
        
        detail_ref = None
        if self.file_system and tokens > self.config.max_section_tokens:
            detail_ref = await self._archive_section_content(
                section_id=section_id,
                content=content,
                metadata=metadata,
            )
            content = content[:500] + f"\n... [详见 {section_id}]"
        
        section = Section(
            section_id=section_id,
            step_name=step_name,
            content=content,
            detail_ref=detail_ref,
            priority=priority,
            timestamp=time.time(),
            tokens=tokens,
            metadata=metadata or {},
        )
        
        self._current_chapter.sections.append(section)
        self._current_chapter.tokens += tokens
        self._section_index[section_id] = section
        
        logger.debug(f"[ChapterIndexer] Added section: {section_id} ({priority.value})")
        
        return section
    
    async def _archive_section_content(
        self,
        section_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """归档节内容到文件系统"""
        if not self.file_system:
            return None
        
        try:
            file_key = f"hierarchical/{self.session_id}/sections/{section_id}"
            from derisk.agent.core.memory.gpts import FileType
            
            await self.file_system.save_file(
                file_key=file_key,
                data=content,
                file_type=FileType.TOOL_OUTPUT,
                metadata={
                    "section_id": section_id,
                    "timestamp": time.time(),
                    "session_id": self.session_id,
                    **(metadata or {}),
                },
            )
            return f"file://{file_key}"
        except Exception as e:
            logger.error(f"[ChapterIndexer] Failed to archive section: {e}")
            return None
    
    def get_context_for_prompt(
        self,
        token_budget: int = 30000,
    ) -> str:
        """
        生成分层上下文用于prompt
        
        策略：
        - 最新N章：完整展示章节内容
        - 中间N章：展示章节总结+节目录
        - 早期章节：只展示章节总结
        
        Args:
            token_budget: token预算
            
        Returns:
            格式化的上下文字符串
        """
        if not self._chapters:
            return ""
        
        lines = ["# Task Execution History\n"]
        total_tokens = 0
        
        chapters_reversed = list(reversed(self._chapters))
        
        for i, chapter in enumerate(chapters_reversed):
            if i < self.config.recent_chapters_full:
                context = self._format_chapter_full(chapter)
            elif i < self.config.recent_chapters_full + self.config.middle_chapters_index:
                context = self._format_chapter_index(chapter)
            else:
                context = self._format_chapter_summary(chapter)
            
            estimated_tokens = len(context) // 4
            
            if total_tokens + estimated_tokens > token_budget:
                summary = f"[{chapter.chapter_id[:8]}] {chapter.title}: {chapter.summary[:200]}"
                lines.append(summary)
                break
            
            lines.append(context)
            lines.append("\n---\n")
            total_tokens += estimated_tokens
        
        return "\n".join(lines)
    
    def _format_chapter_full(self, chapter: Chapter) -> str:
        """完整展示章节（包含 section_id 供回溯）"""
        lines = [f"## {chapter.title} ({chapter.phase.value})"]
        if chapter.summary:
            lines.append(f"Summary: {chapter.summary}\n")
        
        for section in chapter.sections:
            # 关键：包含 section_id，Agent可用此调用回溯工具
            lines.append(f"### {section.step_name}")
            lines.append(f"[ID: {section.section_id}]")
            if section.detail_ref:
                lines.append(f"[已归档，可使用 recall_section(\"{section.section_id}\") 查看详情]")
            lines.append(f"{section.content}\n")
        
        return "\n".join(lines)
    
    def _format_chapter_index(self, chapter: Chapter) -> str:
        """展示章节总结+节目录（包含 section_id 供回溯）"""
        lines = [f"## {chapter.title} ({chapter.phase.value})"]
        if chapter.summary:
            lines.append(f"Summary: {chapter.summary}\n")
        lines.append("\nSections:")
        for sec in chapter.sections:
            # 包含 section_id
            detail_hint = ""
            if sec.detail_ref:
                detail_hint = " [已归档]"
            lines.append(f"  - [{sec.section_id[:12]}] {sec.step_name}: {sec.content[:80]}...{detail_hint}")
        return "\n".join(lines)
    
    def _format_chapter_summary(self, chapter: Chapter) -> str:
        """只展示章节总结"""
        return chapter.to_chapter_summary()
    
    async def recall_section(self, section_id: str) -> Optional[str]:
        """
        回溯节的完整内容
        
        Args:
            section_id: 节ID
            
        Returns:
            完整内容，如果未找到返回None
        """
        section = self._section_index.get(section_id)
        if not section:
            for chapter in self._chapters:
                for sec in chapter.sections:
                    if sec.section_id == section_id:
                        section = sec
                        break
                if section:
                    break
        
        if not section:
            logger.warning(f"[ChapterIndexer] Section not found: {section_id}")
            return None
        
        if section.detail_ref:
            return await self._load_archived_content(section.detail_ref)
        return section.content
    
    async def recall_chapter(self, chapter_id: str) -> Optional[Chapter]:
        """
        回溯整个章节
        
        Args:
            chapter_id: 章节ID，可以是 "latest"
            
        Returns:
            章节对象
        """
        if chapter_id == "latest":
            return self._chapters[-1] if self._chapters else None
        
        return self._chapter_index.get(chapter_id)
    
    async def _load_archived_content(self, ref: str) -> Optional[str]:
        """从文件系统加载归档内容"""
        if not self.file_system or not ref.startswith("file://"):
            return None
        
        file_key = ref[7:]
        try:
            return await self.file_system.read_file(file_key)
        except Exception as e:
            logger.error(f"[ChapterIndexer] Failed to load archived content: {e}")
            return None
    
    async def search_by_query(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        关键词搜索历史
        
        Args:
            query: 搜索关键词
            limit: 最大返回数量
            
        Returns:
            匹配结果列表
        """
        matches = []
        query_lower = query.lower()
        
        for chapter in self._chapters:
            if query_lower in chapter.title.lower() or query_lower in chapter.summary.lower():
                matches.append({
                    "type": "chapter",
                    "id": chapter.chapter_id,
                    "title": chapter.title,
                    "preview": chapter.summary[:200],
                })
            
            for section in chapter.sections:
                if query_lower in section.content.lower() or query_lower in section.step_name.lower():
                    matches.append({
                        "type": "section",
                        "id": section.section_id,
                        "chapter_id": chapter.chapter_id,
                        "title": section.step_name,
                        "preview": section.content[:200],
                    })
                
                if len(matches) >= limit:
                    return matches
        
        return matches
    
    def get_current_phase(self) -> Optional[TaskPhase]:
        """获取当前任务阶段"""
        if self._current_chapter:
            return self._current_chapter.phase
        return None
    
    def get_current_chapter(self) -> Optional[Chapter]:
        """获取当前章节"""
        return self._current_chapter
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        phases_stats = {}
        for chapter in self._chapters:
            phase_key = chapter.phase.value
            if phase_key not in phases_stats:
                phases_stats[phase_key] = {
                    "count": 0,
                    "sections": 0,
                    "tokens": 0,
                }
            phases_stats[phase_key]["count"] += 1
            phases_stats[phase_key]["sections"] += len(chapter.sections)
            phases_stats[phase_key]["tokens"] += chapter.tokens
        
        priority_stats = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for section in self._section_index.values():
            priority_key = section.priority.value if isinstance(section.priority, ContentPriority) else section.priority
            priority_stats[priority_key] = priority_stats.get(priority_key, 0) + 1
        
        return {
            "total_chapters": len(self._chapters),
            "total_sections": len(self._section_index),
            "total_tokens": sum(c.tokens for c in self._chapters),
            "current_phase": self._current_chapter.phase.value if self._current_chapter else None,
            "phases": phases_stats,
            "priority_distribution": priority_stats,
        }
    
    def mark_chapter_compacted(self, chapter_id: str) -> bool:
        """标记章节已压缩"""
        chapter = self._chapter_index.get(chapter_id)
        if chapter:
            chapter.is_compacted = True
            return True
        return False
    
    def get_uncompacted_chapters(self) -> List[Chapter]:
        """获取未压缩的章节"""
        return [c for c in self._chapters if not c.is_compacted]
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "config": self.config.to_dict(),
            "chapters": [c.to_dict() for c in self._chapters],
            "section_counter": self._section_counter,
            "chapter_counter": self._chapter_counter,
        }
    
    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        file_system: Optional[AgentFileSystem] = None,
    ) -> "ChapterIndexer":
        """从字典反序列化"""
        config = HierarchicalContextConfig.from_dict(data.get("config", {}))
        indexer = cls(
            file_system=file_system,
            config=config,
            session_id=data.get("session_id", "default"),
        )
        
        indexer._section_counter = data.get("section_counter", 0)
        indexer._chapter_counter = data.get("chapter_counter", 0)
        
        for chapter_data in data.get("chapters", []):
            chapter = Chapter.from_dict(chapter_data)
            indexer._chapters.append(chapter)
            indexer._chapter_index[chapter.chapter_id] = chapter
            
            for section in chapter.sections:
                indexer._section_index[section.section_id] = section
        
        if indexer._chapters:
            indexer._current_chapter = indexer._chapters[-1]
        
        return indexer