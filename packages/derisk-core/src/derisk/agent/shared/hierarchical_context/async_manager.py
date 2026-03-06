"""
异步分层上下文管理器

确保全流程异步，无阻塞：
1. 使用asyncio实现并发安全
2. 支持大规模并发场景
3. 锁机制保护共享资源
4. 批量操作优化
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, AsyncIterator

from .hierarchical_context_index import (
    Chapter,
    ContentPriority,
    Section,
    TaskPhase,
    HierarchicalContextConfig,
)
from .chapter_indexer import ChapterIndexer
from .content_prioritizer import ContentPrioritizer
from .hierarchical_compactor import HierarchicalCompactor, CompactionScheduler
from .memory_prompt_config import MemoryPromptConfig

if TYPE_CHECKING:
    from derisk.core import LLMClient
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem

logger = logging.getLogger(__name__)


@dataclass
class AsyncContextStats:
    """异步上下文统计"""
    active_sessions: int = 0
    total_sections_recorded: int = 0
    total_compactions: int = 0
    total_tokens_saved: int = 0
    pending_operations: int = 0
    lock_waits: int = 0


class AsyncLockManager:
    """
    异步锁管理器
    
    管理不同层级的锁，避免全局锁竞争
    """
    
    def __init__(self):
        self._session_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._chapter_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()
        self._lock_stats: Dict[str, int] = defaultdict(int)
    
    @asynccontextmanager
    async def session_lock(self, session_id: str):
        """会话级锁"""
        lock = self._session_locks[session_id]
        self._lock_stats[f"session:{session_id}"] += 1
        async with lock:
            yield
    
    @asynccontextmanager
    async def chapter_lock(self, chapter_id: str):
        """章节级锁"""
        lock = self._chapter_locks[chapter_id]
        self._lock_stats[f"chapter:{chapter_id}"] += 1
        async with lock:
            yield
    
    @asynccontextmanager
    async def global_lock(self):
        """全局锁（仅用于关键操作）"""
        self._lock_stats["global"] += 1
        async with self._global_lock:
            yield
    
    def get_stats(self) -> Dict[str, int]:
        return dict(self._lock_stats)


class AsyncBatchProcessor:
    """
    异步批量处理器
    
    优化批量操作的并发执行
    """
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._pending_tasks: List[asyncio.Task] = []
    
    async def submit(self, coro, name: str = "") -> asyncio.Task:
        """提交异步任务"""
        task = asyncio.create_task(self._run_with_semaphore(coro, name))
        self._pending_tasks.append(task)
        return task
    
    async def _run_with_semaphore(self, coro, name: str):
        """带信号量限制的执行"""
        async with self._semaphore:
            try:
                return await coro
            except Exception as e:
                logger.error(f"[AsyncBatchProcessor] Task {name} failed: {e}")
                raise
    
    async def wait_all(self) -> List[Any]:
        """等待所有任务完成"""
        if not self._pending_tasks:
            return []
        
        results = await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()
        return results
    
    async def wait_and_collect(self) -> Dict[str, Any]:
        """等待并收集结果"""
        results = await self.wait_all()
        return {
            f"task_{i}": r if not isinstance(r, Exception) else f"Error: {r}"
            for i, r in enumerate(results)
        }


class AsyncHierarchicalContextManager:
    """
    异步分层上下文管理器
    
    全异步设计，确保：
    1. 所有I/O操作异步执行
    2. 锁机制保护共享资源
    3. 批量操作并发优化
    4. 高并发无阻塞
    
    使用示例:
        manager = AsyncHierarchicalContextManager(llm_client=client)
        
        # 开始任务
        await manager.start_task("session_1", "构建上下文系统")
        
        # 记录步骤（异步，不阻塞主流程）
        await manager.record_step("session_1", action_out)
        
        # 批量记录
        await manager.record_steps_batch("session_1", [action1, action2])
        
        # 触发压缩（异步后台执行）
        await manager.schedule_compaction("session_1")
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        file_system: Optional[AgentFileSystem] = None,
        config: Optional[HierarchicalContextConfig] = None,
        memory_prompt_config: Optional[MemoryPromptConfig] = None,
        max_concurrent_sessions: int = 100,
        max_concurrent_operations: int = 20,
    ):
        self.llm_client = llm_client
        self.file_system = file_system
        self.config = config or HierarchicalContextConfig()
        self.memory_prompt_config = memory_prompt_config or MemoryPromptConfig()
        
        self._lock_manager = AsyncLockManager()
        self._batch_processor = AsyncBatchProcessor(max_concurrent_operations)
        
        self._sessions: Dict[str, ChapterIndexer] = {}
        self._compactors: Dict[str, HierarchicalCompactor] = {}
        self._prioritizers: Dict[str, ContentPrioritizer] = {}
        
        self._stats = AsyncContextStats()
        self._max_concurrent_sessions = max_concurrent_sessions
        
        self._compaction_queue: asyncio.Queue = asyncio.Queue()
        self._compaction_worker_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """初始化管理器"""
        self._compaction_worker_task = asyncio.create_task(
            self._compaction_worker()
        )
        logger.info("[AsyncHierarchicalContextManager] Initialized")
    
    async def shutdown(self) -> None:
        """关闭管理器"""
        if self._compaction_worker_task:
            self._compaction_worker_task.cancel()
            try:
                await self._compaction_worker_task
            except asyncio.CancelledError:
                pass
        
        await self._batch_processor.wait_all()
        logger.info("[AsyncHierarchicalContextManager] Shutdown complete")
    
    async def start_task(
        self,
        session_id: str,
        task: str,
    ) -> ChapterIndexer:
        """
        开始新任务
        
        Args:
            session_id: 会话ID
            task: 任务描述
            
        Returns:
            章节索引器
        """
        async with self._lock_manager.session_lock(session_id):
            if session_id in self._sessions:
                return self._sessions[session_id]
            
            if len(self._sessions) >= self._max_concurrent_sessions:
                await self._cleanup_old_sessions()
            
            indexer = ChapterIndexer(
                file_system=self.file_system,
                config=self.config,
                session_id=session_id,
            )
            
            indexer.create_chapter(
                phase=TaskPhase.EXPLORATION,
                title="任务开始",
                description=task,
            )
            
            self._sessions[session_id] = indexer
            self._compactors[session_id] = HierarchicalCompactor(
                llm_client=self.llm_client,
            )
            self._prioritizers[session_id] = ContentPrioritizer()
            
            self._stats.active_sessions += 1
            
            logger.info(f"[AsyncHierarchicalContextManager] Started task: {session_id}")
            
            return indexer
    
    async def record_step(
        self,
        session_id: str,
        action_out: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        记录执行步骤（异步）
        
        Args:
            session_id: 会话ID
            action_out: 动作输出
            metadata: 元数据
            
        Returns:
            section_id
        """
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            if not indexer:
                logger.warning(f"[AsyncHierarchicalContextManager] Session not found: {session_id}")
                return None
            
            prioritizer = self._prioritizers.get(session_id)
            priority = ContentPriority.MEDIUM
            if prioritizer:
                priority = prioritizer.classify_message_from_action(action_out)
            
            action_name = getattr(action_out, "name", "") or getattr(action_out, "action", "") or "unknown"
            content = getattr(action_out, "content", "") or ""
            success = getattr(action_out, "is_exe_success", True)
            
            section = await indexer.add_section(
                step_name=action_name,
                content=str(content),
                priority=priority,
                metadata={
                    "success": success,
                    **(metadata or {}),
                },
            )
            
            self._stats.total_sections_recorded += 1
            
            if indexer.tokens > self.config.max_chapter_tokens:
                await self._compaction_queue.put((session_id, "auto"))
            
            return section.section_id
    
    async def record_steps_batch(
        self,
        session_id: str,
        actions: List[Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Optional[str]]:
        """
        批量记录步骤（并发优化）
        
        Args:
            session_id: 会话ID
            actions: 动作列表
            metadata: 元数据
            
        Returns:
            section_id列表
        """
        results = []
        
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            if not indexer:
                return [None] * len(actions)
            
            prioritizer = self._prioritizers.get(session_id)
            
            for action_out in actions:
                priority = ContentPriority.MEDIUM
                if prioritizer:
                    priority = prioritizer.classify_message_from_action(action_out)
                
                action_name = getattr(action_out, "name", "") or getattr(action_out, "action", "") or "unknown"
                content = getattr(action_out, "content", "") or ""
                success = getattr(action_out, "is_exe_success", True)
                
                section = await indexer.add_section(
                    step_name=action_name,
                    content=str(content),
                    priority=priority,
                    metadata={
                        "success": success,
                        **(metadata or {}),
                    },
                )
                
                results.append(section.section_id)
                self._stats.total_sections_recorded += 1
        
        return results
    
    async def get_context_for_prompt(
        self,
        session_id: str,
        token_budget: int = 30000,
    ) -> str:
        """
        获取分层上下文（异步读取）
        
        Args:
            session_id: 会话ID
            token_budget: token预算
            
        Returns:
            格式化的上下文
        """
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            if not indexer:
                return ""
            
            return indexer.get_context_for_prompt(token_budget)
    
    async def schedule_compaction(
        self,
        session_id: str,
        force: bool = False,
    ) -> None:
        """
        调度压缩任务（异步后台执行）
        
        Args:
            session_id: 会话ID
            force: 是否强制压缩
        """
        await self._compaction_queue.put((session_id, "force" if force else "manual"))
    
    async def _compaction_worker(self):
        """压缩工作线程（后台异步执行）"""
        while True:
            try:
                session_id, trigger = await self._compaction_queue.get()
                
                self._stats.pending_operations += 1
                
                try:
                    await self._do_compaction(session_id)
                except Exception as e:
                    logger.error(f"[AsyncHierarchicalContextManager] Compaction failed: {e}")
                finally:
                    self._stats.pending_operations -= 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AsyncHierarchicalContextManager] Worker error: {e}")
    
    async def _do_compaction(self, session_id: str) -> Dict[str, Any]:
        """执行压缩（内部方法）"""
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            compactor = self._compactors.get(session_id)
            
            if not indexer or not compactor:
                return {"error": "Session not found"}
            
            results = []
            total_saved = 0
            
            for chapter in indexer.get_uncompacted_chapters():
                result = await compactor.compact_chapter(chapter)
                if result.success:
                    results.append({
                        "chapter_id": chapter.chapter_id,
                        "tokens_saved": result.original_tokens - result.compacted_tokens,
                    })
                    total_saved += result.original_tokens - result.compacted_tokens
            
            self._stats.total_compactions += 1
            self._stats.total_tokens_saved += total_saved
            
            return {
                "compacted_chapters": len(results),
                "total_tokens_saved": total_saved,
                "details": results,
            }
    
    async def recall_section(
        self,
        session_id: str,
        section_id: str,
    ) -> Optional[str]:
        """
        回溯节内容（异步文件读取）
        
        Args:
            session_id: 会话ID
            section_id: 节ID
            
        Returns:
            节内容
        """
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            if not indexer:
                return None
            
            return await indexer.recall_section(section_id)
    
    async def search_history(
        self,
        session_id: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        搜索历史（异步）
        
        Args:
            session_id: 会话ID
            query: 搜索关键词
            limit: 最大返回数量
            
        Returns:
            匹配结果列表
        """
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            if not indexer:
                return []
            
            return await indexer.search_by_query(query, limit)
    
    async def _cleanup_old_sessions(self) -> None:
        """清理旧会话（当达到上限时）"""
        async with self._lock_manager.global_lock():
            if len(self._sessions) < self._max_concurrent_sessions:
                return
            
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1]._chapters[-1].created_at if x[1]._chapters else 0
            )
            
            to_remove = len(self._sessions) - self._max_concurrent_sessions // 2
            
            for session_id, _ in sorted_sessions[:to_remove]:
                del self._sessions[session_id]
                self._compactors.pop(session_id, None)
                self._prioritizers.pop(session_id, None)
                self._stats.active_sessions -= 1
            
            logger.info(f"[AsyncHierarchicalContextManager] Cleaned up {to_remove} old sessions")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_sessions": self._stats.active_sessions,
            "total_sections_recorded": self._stats.total_sections_recorded,
            "total_compactions": self._stats.total_compactions,
            "total_tokens_saved": self._stats.total_tokens_saved,
            "pending_operations": self._stats.pending_operations,
            "lock_stats": self._lock_manager.get_stats(),
        }
    
    async def get_session_statistics(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话统计"""
        async with self._lock_manager.session_lock(session_id):
            indexer = self._sessions.get(session_id)
            if not indexer:
                return None
            
            return indexer.get_statistics()


# 全局单例管理
_global_manager: Optional[AsyncHierarchicalContextManager] = None
_manager_lock = asyncio.Lock()


async def get_global_manager() -> AsyncHierarchicalContextManager:
    """获取全局管理器（单例）"""
    global _global_manager
    
    if _global_manager is None:
        async with _manager_lock:
            if _global_manager is None:
                _global_manager = AsyncHierarchicalContextManager()
                await _global_manager.initialize()
    
    return _global_manager


async def create_async_manager(
    llm_client: Optional[LLMClient] = None,
    file_system: Optional[AgentFileSystem] = None,
    **kwargs,
) -> AsyncHierarchicalContextManager:
    """创建异步管理器"""
    manager = AsyncHierarchicalContextManager(
        llm_client=llm_client,
        file_system=file_system,
        **kwargs,
    )
    await manager.initialize()
    return manager