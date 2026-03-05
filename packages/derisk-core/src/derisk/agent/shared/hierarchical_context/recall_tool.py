"""
分层上下文索引系统 - 回溯工具

基于 FunctionTool 框架开发：
1. 正确使用 FunctionTool 框架
2. Agent 通过参数传递（section_id/chapter_id/query）
3. 从 AgentFileSystem 读取原内容
4. 动态注入机制
5. 保护机制
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Callable

from derisk.agent import ActionOutput
from derisk.agent.resource.tool.base import FunctionTool

if TYPE_CHECKING:
    from .chapter_indexer import ChapterIndexer
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem

logger = logging.getLogger(__name__)


class RecallSectionTool(FunctionTool):
    """
    回溯特定节的工具
    
    用于从文件系统读取归档的内容。
    Agent 调用时传递 section_id 参数。
    """
    
    def __init__(
        self,
        chapter_indexer: ChapterIndexer,
        file_system: Optional[AgentFileSystem] = None,
        protect_recent_chapters: int = 2,
    ):
        self.chapter_indexer = chapter_indexer
        self.file_system = file_system
        self.protect_recent_chapters = protect_recent_chapters
        
        super().__init__(
            name="recall_section",
            func=self._execute_sync_wrapper,
            description="回顾特定执行步骤的详细内容。当需要查看早期步骤的详细信息时使用。只能回溯已压缩归档的历史步骤。参数: section_id - 要回顾的节ID。",
            args={
                "section_id": {
                    "type": "string",
                    "description": "要回顾的节ID，格式如 'section_123_xxx'",
                },
            },
        )
    
    def _execute_sync_wrapper(self, section_id: str) -> str:
        """同步包装器（FunctionTool要求）"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步环境中，创建新的线程执行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._execute_async(section_id)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._execute_async(section_id))
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _execute_async(self, section_id: str) -> str:
        """异步执行"""
        return await self.execute(section_id)
    
    async def execute(self, section_id: str, **kwargs) -> str:
        """
        执行回溯
        
        Args:
            section_id: 节ID
            
        Returns:
            该步骤的完整内容
        """
        # 保护最近章节
        recent_chapter_ids = [
            c.chapter_id 
            for c in list(self.chapter_indexer._chapters)[-self.protect_recent_chapters:]
        ]
        
        # 查找节
        section = None
        containing_chapter = None
        for chapter in self.chapter_indexer._chapters:
            for sec in chapter.sections:
                if sec.section_id == section_id:
                    section = sec
                    containing_chapter = chapter
                    break
            if section:
                break
        
        if not section:
            return f"Error: Section '{section_id}' not found."
        
        # 检查保护机制
        if containing_chapter and containing_chapter.chapter_id in recent_chapter_ids:
            return f"Error: Section '{section_id}' is in a recent chapter. Use current context instead."
        
        # 从文件系统加载归档内容
        if section.detail_ref:
            content = await self._load_from_filesystem(section.detail_ref)
            if content:
                return self._format_result(section, content)
            return f"Error: Failed to load archived content for '{section_id}'."
        
        # 未归档则直接返回内容
        return self._format_result(section, section.content)
    
    async def _load_from_filesystem(self, ref: str) -> Optional[str]:
        """
        从 AgentFileSystem 读取原内容
        
        Args:
            ref: 文件引用，格式 "file://path/to/file"
            
        Returns:
            原始内容
        """
        if not self.file_system:
            logger.warning("[RecallSectionTool] No file system available")
            return None
        
        if not ref.startswith("file://"):
            logger.warning(f"[RecallSectionTool] Invalid ref format: {ref}")
            return None
        
        file_key = ref[7:]  # 去掉 "file://" 前缀
        
        try:
            content = await self.file_system.read_file(file_key)
            logger.info(f"[RecallSectionTool] Loaded content from: {file_key}")
            return content
        except Exception as e:
            logger.error(f"[RecallSectionTool] Failed to read file {file_key}: {e}")
            return None
    
    def _format_result(self, section: Any, content: str) -> str:
        """格式化输出结果"""
        priority = section.priority.value if hasattr(section.priority, 'value') else str(section.priority)
        return f"""### 步骤详情: {section.step_name}

**ID**: {section.section_id}
**优先级**: {priority}
**Tokens**: {section.tokens}

#### 内容:
{content}

---
*这是归档的历史步骤*"""


class RecallChapterTool(FunctionTool):
    """
    回溯整个章节的工具
    """
    
    def __init__(
        self,
        chapter_indexer: ChapterIndexer,
        protect_recent_chapters: int = 2,
    ):
        self.chapter_indexer = chapter_indexer
        self.protect_recent_chapters = protect_recent_chapters
        
        super().__init__(
            name="recall_chapter",
            func=self._execute_sync_wrapper,
            description="回顾整个任务阶段的执行情况。获取该阶段所有步骤的索引和摘要。参数: chapter_id - 章节ID。",
            args={
                "chapter_id": {
                    "type": "string",
                    "description": "章节ID",
                },
            },
        )
    
    def _execute_sync_wrapper(self, chapter_id: str) -> str:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._execute_async(chapter_id)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._execute_async(chapter_id))
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _execute_async(self, chapter_id: str) -> str:
        return await self.execute(chapter_id)
    
    async def execute(self, chapter_id: str, **kwargs) -> str:
        """执行回溯"""
        # 保护最近章节
        recent_chapter_ids = [
            c.chapter_id 
            for c in list(self.chapter_indexer._chapters)[-self.protect_recent_chapters:]
        ]
        
        if chapter_id in recent_chapter_ids:
            return f"Error: Chapter '{chapter_id}' is recent. Use current context."
        
        # 查找章节
        chapter = None
        for c in self.chapter_indexer._chapters:
            if c.chapter_id == chapter_id:
                chapter = c
                break
        
        if not chapter:
            return f"Error: Chapter '{chapter_id}' not found."
        
        return self._format_result(chapter)
    
    def _format_result(self, chapter: Any) -> str:
        """格式化输出"""
        phase = chapter.phase.value if hasattr(chapter.phase, 'value') else str(chapter.phase)
        
        lines = [
            f"## 阶段详情: {chapter.title}",
            f"**阶段**: {phase}",
            f"**步骤数**: {len(chapter.sections)}",
            f"**摘要**: {chapter.summary}",
            "",
            "### 步骤索引:",
        ]
        
        for section in chapter.sections:
            priority = section.priority.value if hasattr(section.priority, 'value') else str(section.priority)
            lines.append(f"- [{section.section_id[:8]}] {section.step_name} ({priority})")
            if section.detail_ref:
                lines.append(f"  📦 归档内容，使用 recall_section(\"{section.section_id}\") 查看")
            else:
                lines.append(f"  预览: {section.content[:100]}...")
        
        return "\n".join(lines)


class SearchHistoryTool(FunctionTool):
    """
    搜索历史记录的工具
    """
    
    def __init__(self, chapter_indexer: ChapterIndexer):
        self.chapter_indexer = chapter_indexer
        
        super().__init__(
            name="search_history",
            func=self._execute_sync_wrapper,
            description="搜索历史执行记录中的关键词。在节标题、内容和章节标题中搜索。参数: query - 搜索关键词, limit - 最大返回数。",
            args={
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "最大返回数量，默认10",
                },
            },
        )
    
    def _execute_sync_wrapper(self, query: str, limit: int = 10) -> str:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._execute_async(query, limit)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._execute_async(query, limit))
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _execute_async(self, query: str, limit: int = 10) -> str:
        return await self.execute(query, limit)
    
    async def execute(self, query: str, limit: int = 10, **kwargs) -> str:
        """执行搜索"""
        matches = await self.chapter_indexer.search_by_query(query, limit)
        
        if not matches:
            return f"No results found for '{query}'."
        
        lines = [f"### 搜索结果: '{query}'", f"找到 {len(matches)} 条匹配:\n"]
        
        for i, match in enumerate(matches, 1):
            type_label = "章节" if match["type"] == "chapter" else "步骤"
            lines.append(f"{i}. [{type_label}] {match['title']}")
            lines.append(f"   ID: {match['id']}")
            lines.append(f"   预览: {match['preview'][:150]}...")
            lines.append("")
        
        return "\n".join(lines)


class RecallToolManager:
    """
    回溯工具管理器
    
    负责动态注入和管理回溯工具。
    只在有压缩章节记录时才启用回溯工具。
    """
    
    def __init__(
        self,
        chapter_indexer: ChapterIndexer,
        file_system: Optional[AgentFileSystem] = None,
        protect_recent_chapters: int = 2,
    ):
        self.chapter_indexer = chapter_indexer
        self.file_system = file_system
        self.protect_recent_chapters = protect_recent_chapters
        
        self._tools: List[FunctionTool] = []
        self._is_injected = False
    
    def should_inject_tools(self) -> bool:
        """判断是否应该注入回溯工具"""
        if not self.chapter_indexer._chapters:
            return False
        
        # 检查是否有归档内容或超过一定数量的章节
        has_archived_content = False
        for chapter in self.chapter_indexer._chapters:
            for section in chapter.sections:
                if section.detail_ref:
                    has_archived_content = True
                    break
            if has_archived_content:
                break
        
        # 或者有多个章节时也启用
        if len(self.chapter_indexer._chapters) > 1:
            return True
        
        return has_archived_content
    
    def get_tools(self) -> List[FunctionTool]:
        """获取回溯工具列表"""
        if not self.should_inject_tools():
            logger.info("[RecallToolManager] No archived content, tools not injected")
            return []
        
        if not self._tools:
            self._create_tools()
        
        self._is_injected = True
        logger.info(f"[RecallToolManager] Injected {len(self._tools)} recall tools")
        
        return self._tools
    
    def _create_tools(self) -> None:
        """创建回溯工具"""
        self._tools = [
            RecallSectionTool(
                chapter_indexer=self.chapter_indexer,
                file_system=self.file_system,
                protect_recent_chapters=self.protect_recent_chapters,
            ),
            RecallChapterTool(
                chapter_indexer=self.chapter_indexer,
                protect_recent_chapters=self.protect_recent_chapters,
            ),
            SearchHistoryTool(
                chapter_indexer=self.chapter_indexer,
            ),
        ]
    
    def update_file_system(self, file_system: AgentFileSystem) -> None:
        """更新文件系统引用"""
        self.file_system = file_system
        for tool in self._tools:
            if isinstance(tool, RecallSectionTool):
                tool.file_system = file_system
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "tools_count": len(self._tools),
            "is_injected": self._is_injected,
            "should_inject": self.should_inject_tools(),
            "protect_recent_chapters": self.protect_recent_chapters,
            "file_system_available": self.file_system is not None,
        }


# 便捷函数
def create_recall_tools(
    chapter_indexer: ChapterIndexer,
    file_system: Optional[AgentFileSystem] = None,
    protect_recent_chapters: int = 2,
) -> List[FunctionTool]:
    """
    创建回溯工具列表
    
    Args:
        chapter_indexer: 章节索引器
        file_system: Agent文件系统（用于读取归档内容）
        protect_recent_chapters: 保护最近N章
        
    Returns:
        工具列表
    """
    manager = RecallToolManager(
        chapter_indexer=chapter_indexer,
        file_system=file_system,
        protect_recent_chapters=protect_recent_chapters,
    )
    return manager.get_tools()