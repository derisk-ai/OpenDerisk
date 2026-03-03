"""
MemoryFactory - 统一记忆管理工厂

为所有Agent提供简单易用的记忆管理能力
支持内存模式（默认）和持久化模式
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .unified_memory.base import (
    MemoryItem,
    MemoryType,
    SearchOptions,
    UnifiedMemoryInterface,
    MemoryConsolidationResult,
)

logger = __import__('logging').getLogger(__name__)


class InMemoryStorage(UnifiedMemoryInterface):
    """内存存储实现 - 默认使用，无需外部依赖"""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self._storage: Dict[str, MemoryItem] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
    
    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True,
    ) -> str:
        await self.initialize()
        
        memory_id = str(uuid.uuid4())
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
        )
        
        self._storage[memory_id] = item
        return memory_id
    
    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        await self.initialize()
        
        options = options or SearchOptions()
        results = []
        
        for item in self._storage.values():
            if options.memory_types and item.memory_type not in options.memory_types:
                continue
            if item.importance < options.min_importance:
                continue
            if query and query.lower() not in item.content.lower():
                continue
            results.append(item)
        
        return results[:options.top_k]
    
    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        await self.initialize()
        items = list(self._storage.values())[:top_k]
        for item in items:
            item.update_access()
        return items
    
    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        await self.initialize()
        item = self._storage.get(memory_id)
        if item:
            item.update_access()
        return item
    
    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        await self.initialize()
        
        if memory_id not in self._storage:
            return False
        
        item = self._storage[memory_id]
        if content:
            item.content = content
        if metadata:
            item.metadata.update(metadata)
        
        return True
    
    async def delete(self, memory_id: str) -> bool:
        await self.initialize()
        
        if memory_id not in self._storage:
            return False
        
        del self._storage[memory_id]
        return True
    
    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> MemoryConsolidationResult:
        await self.initialize()
        
        criteria = criteria or {}
        min_importance = criteria.get("min_importance", 0.5)
        min_access_count = criteria.get("min_access_count", 1)
        
        items_to_consolidate = []
        items_to_discard = []
        
        for item in self._storage.values():
            if item.memory_type != source_type:
                continue
            
            if item.importance >= min_importance and item.access_count >= min_access_count:
                items_to_consolidate.append(item)
            else:
                items_to_discard.append(item)
        
        for item in items_to_consolidate:
            item.memory_type = target_type
        
        tokens_saved = sum(len(i.content) // 4 for i in items_to_discard)
        
        return MemoryConsolidationResult(
            success=True,
            source_type=source_type,
            target_type=target_type,
            items_consolidated=len(items_to_consolidate),
            items_discarded=len(items_to_discard),
            tokens_saved=tokens_saved,
        )
    
    async def export(
        self,
        format: str = "markdown",
        memory_types: Optional[List[MemoryType]] = None,
    ) -> str:
        await self.initialize()
        
        items = list(self._storage.values())
        
        if memory_types:
            items = [i for i in items if i.memory_type in memory_types]
        
        if format == "json":
            import json
            return json.dumps([i.to_dict() for i in items], indent=2, ensure_ascii=False)
        
        content = "# Memory Export\n\n"
        for item in items:
            content += f"## [{item.memory_type.value}] {item.id}\n"
            content += f"{item.content}\n\n---\n\n"
        
        return content
    
    async def import_from_file(
        self,
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED,
    ) -> int:
        await self.initialize()
        return 0
    
    async def clear(
        self,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> int:
        await self.initialize()
        
        if not memory_types:
            count = len(self._storage)
            self._storage.clear()
            return count
        
        ids_to_remove = [
            id for id, item in self._storage.items()
            if item.memory_type in memory_types
        ]
        
        for id in ids_to_remove:
            del self._storage[id]
        
        return len(ids_to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_items": len(self._storage),
            "by_type": {
                mt.value: len([i for i in self._storage.values() if i.memory_type == mt])
                for mt in MemoryType
            },
        }


class MemoryFactory:
    """统一记忆管理工厂

    支持多种存储后端:
    1. GptsMemory 后端 (推荐用于生产环境，支持数据库持久化)
    2. InMemoryStorage 后端 (默认，适用于测试和简单场景)
    3. UnifiedMemoryManager 后端 (支持向量存储，适用于需要语义搜索的场景)
    """

    @staticmethod
    def create(
        session_id: Optional[str] = None,
        use_persistent: bool = False,
        project_root: Optional[str] = None,
        vector_store: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        gpts_memory: Optional[Any] = None,
        conv_id: Optional[str] = None,
        use_gpts_backend: bool = True,
    ) -> UnifiedMemoryInterface:
        """
        创建统一记忆管理器

        Args:
            session_id: 会话 ID
            use_persistent: 是否使用持久化存储
            project_root: 项目根目录 (用于持久化存储)
            vector_store: 向量存储 (用于语义搜索)
            embedding_model: 嵌入模型 (用于语义搜索)
            gpts_memory: GptsMemory 实例 (Core V1 的记忆管理器)
            conv_id: 会话 ID (用于 GptsMemory 后端)
            use_gpts_backend: 是否优先使用 GptsMemory 后端

        Returns:
            UnifiedMemoryInterface 实例

        优先级:
        1. 如果提供了 gpts_memory 且 use_gpts_backend=True，使用 GptsMemoryAdapter
        2. 如果 use_persistent=True 且提供了向量存储，使用 UnifiedMemoryManager
        3. 否则使用 InMemoryStorage
        """
        # 优先使用 GptsMemory 后端（支持数据库持久化）
        if use_gpts_backend and gpts_memory:
            try:
                from .unified_memory.gpts_adapter import GptsMemoryAdapter

                actual_conv_id = conv_id or session_id or str(uuid.uuid4())
                adapter = GptsMemoryAdapter(
                    gpts_memory=gpts_memory,
                    conv_id=actual_conv_id,
                    session_id=session_id,
                )
                logger.info(
                    f"[MemoryFactory] 创建 GptsMemoryAdapter: "
                    f"conv_id={actual_conv_id[:8] if actual_conv_id else 'N/A'}"
                )
                return adapter
            except Exception as e:
                logger.warning(
                    f"[MemoryFactory] 创建 GptsMemoryAdapter 失败: {e}, "
                    f"回退到 InMemoryStorage"
                )

        # 使用持久化存储（带向量搜索）
        if use_persistent:
            try:
                from .unified_memory import UnifiedMemoryManager

                if not project_root:
                    project_root = os.getcwd()

                if not vector_store or not embedding_model:
                    logger.warning(
                        "[MemoryFactory] Persistent memory requires vector_store and "
                        "embedding_model, falling back to in-memory"
                    )
                    return InMemoryStorage(session_id)

                return UnifiedMemoryManager(
                    project_root=project_root,
                    vector_store=vector_store,
                    embedding_model=embedding_model,
                    session_id=session_id,
                )
            except Exception as e:
                logger.warning(
                    f"[MemoryFactory] Failed to create persistent memory: {e}, "
                    f"falling back to in-memory"
                )
                return InMemoryStorage(session_id)

        # 默认使用内存存储
        return InMemoryStorage(session_id)

    @staticmethod
    def create_default(session_id: Optional[str] = None) -> UnifiedMemoryInterface:
        """创建默认的内存存储"""
        return MemoryFactory.create(session_id=session_id, use_persistent=False)

    @staticmethod
    def create_with_gpts(
        gpts_memory: Any,
        conv_id: str,
        session_id: Optional[str] = None,
    ) -> UnifiedMemoryInterface:
        """
        使用 GptsMemory 后端创建记忆管理器

        Args:
            gpts_memory: GptsMemory 实例
            conv_id: 会话 ID
            session_id: 可选的 session ID

        Returns:
            GptsMemoryAdapter 实例
        """
        return MemoryFactory.create(
            session_id=session_id,
            gpts_memory=gpts_memory,
            conv_id=conv_id,
            use_gpts_backend=True,
        )


def create_agent_memory(
    agent_name: str = "agent",
    session_id: Optional[str] = None,
    use_persistent: bool = False,
    gpts_memory: Optional[Any] = None,
    conv_id: Optional[str] = None,
    **kwargs,
) -> UnifiedMemoryInterface:
    """
    为 Agent 创建记忆管理器

    Args:
        agent_name: Agent 名称
        session_id: 会话 ID
        use_persistent: 是否使用持久化存储
        gpts_memory: GptsMemory 实例 (优先使用)
        conv_id: 会话 ID (用于 GptsMemory 后端)
        **kwargs: 其他参数

    Returns:
        UnifiedMemoryInterface 实例
    """
    actual_session_id = session_id or f"{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    memory = MemoryFactory.create(
        session_id=actual_session_id,
        use_persistent=use_persistent,
        gpts_memory=gpts_memory,
        conv_id=conv_id,
        **kwargs,
    )

    session_info = memory.session_id if hasattr(memory, 'session_id') else 'N/A'
    backend_type = type(memory).__name__
    logger.info(
        f"[MemoryFactory] Created memory for agent '{agent_name}': "
        f"session={session_info}, backend={backend_type}"
    )

    return memory