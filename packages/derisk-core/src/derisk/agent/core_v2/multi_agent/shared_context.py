"""
Shared Context - Multi-Agent共享上下文

实现产品层统一、资源平面共享的架构设计：
1. 协作黑板 - Agent间数据共享
2. 产出物管理 - Artifact存储与检索
3. 共享记忆 - 跨Agent记忆系统
4. 资源缓存 - 共享资源访问

@see ARCHITECTURE.md#12.4-shared-context-共享上下文
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
import asyncio
import logging
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ResourceScope(str, Enum):
    """资源作用域"""
    AGENT = "agent"        # 单Agent私有
    TEAM = "team"          # 团队共享
    SESSION = "session"    # 会话级共享
    GLOBAL = "global"      # 全局共享


class ResourceBinding(BaseModel):
    """资源绑定配置"""
    resource_type: str
    resource_name: str
    shared_scope: ResourceScope = ResourceScope.TEAM
    access_mode: str = "read"  # read, write, readwrite


class Artifact(BaseModel):
    """产出物定义"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:12])
    name: str
    content: Any
    content_type: str = "text"  # text, code, image, data, document
    produced_by: str            # 产生该产出物的Agent/Task ID
    produced_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    
    class Config:
        arbitrary_types_allowed = True


class MemoryEntry(BaseModel):
    """记忆条目"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:12])
    content: str
    source: str                    # 来源Agent/Task
    task_id: Optional[str] = None
    role: str = "assistant"        # user, assistant, system
    timestamp: datetime = Field(default_factory=datetime.now)
    importance: float = 0.5        # 重要性分数 0-1
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SharedMemory:
    """
    共享记忆系统
    
    提供跨Agent的记忆共享能力，支持：
    - 时间线记忆检索
    - 关键词搜索
    - 向量相似度检索
    """
    
    def __init__(
        self,
        max_entries: int = 1000,
        enable_vector_search: bool = False,
    ):
        self._entries: List[MemoryEntry] = []
        self._max_entries = max_entries
        self._enable_vector_search = enable_vector_search
        self._vector_store: Optional[Any] = None  # VectorMemoryStore
        self._lock = asyncio.Lock()
    
    async def add(self, entry: MemoryEntry) -> str:
        """添加记忆"""
        async with self._lock:
            if len(self._entries) >= self._max_entries:
                await self._evict_oldest()
            
            self._entries.append(entry)
            
            if self._enable_vector_search and self._vector_store:
                await self._vector_store.store_memory(
                    entry.content,
                    {
                        "source": entry.source,
                        "task_id": entry.task_id,
                        "importance": entry.importance
                    }
                )
            
            logger.debug(f"[SharedMemory] Added entry: {entry.id}")
            return entry.id
    
    async def search(
        self,
        query: str,
        k: int = 5,
        source_filter: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """搜索记忆"""
        async with self._lock:
            results = []
            
            for entry in reversed(self._entries):
                if source_filter and entry.source != source_filter:
                    continue
                
                if query.lower() in entry.content.lower():
                    results.append(entry)
                    if len(results) >= k:
                        break
            
            return results
    
    async def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        """获取最近记忆"""
        async with self._lock:
            return self._entries[-limit:]
    
    async def get_by_task(self, task_id: str) -> List[MemoryEntry]:
        """获取任务相关记忆"""
        async with self._lock:
            return [e for e in self._entries if e.task_id == task_id]
    
    async def clear(self) -> int:
        """清空记忆"""
        async with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count
    
    async def _evict_oldest(self, count: int = 100):
        """淘汰最旧记忆"""
        self._entries = self._entries[count:]
        logger.debug(f"[SharedMemory] Evicted {count} oldest entries")


class CollaborationBlackboard:
    """
    协作黑板
    
    提供Agent间的结构化数据共享：
    - 键值对存储
    - 版本控制
    - 变更通知
    """
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._versions: Dict[str, int] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
    
    async def set(
        self,
        key: str,
        value: Any,
        source: Optional[str] = None,
    ) -> int:
        """设置黑板数据"""
        async with self._lock:
            self._data[key] = value
            self._versions[key] = self._versions.get(key, 0) + 1
            self._metadata[key] = {
                "source": source,
                "updated_at": datetime.now().isoformat(),
                "version": self._versions[key]
            }
            
            await self._notify_subscribers(key, value)
            
            return self._versions[key]
    
    async def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """获取黑板数据"""
        async with self._lock:
            return self._data.get(key, default)
    
    async def get_version(self, key: str) -> int:
        """获取数据版本"""
        return self._versions.get(key, 0)
    
    async def get_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """获取数据元信息"""
        return self._metadata.get(key)
    
    async def delete(self, key: str) -> bool:
        """删除数据"""
        async with self._lock:
            if key in self._data:
                del self._data[key]
                del self._versions[key]
                del self._metadata[key]
                return True
            return False
    
    async def keys(self) -> List[str]:
        """获取所有键"""
        async with self._lock:
            return list(self._data.keys())
    
    async def subscribe(self, key: str) -> asyncio.Queue:
        """订阅数据变更"""
        queue = asyncio.Queue()
        async with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = []
            self._subscribers[key].append(queue)
        return queue
    
    async def unsubscribe(self, key: str, queue: asyncio.Queue):
        """取消订阅"""
        async with self._lock:
            if key in self._subscribers:
                try:
                    self._subscribers[key].remove(queue)
                except ValueError:
                    pass
    
    async def _notify_subscribers(self, key: str, value: Any):
        """通知订阅者"""
        if key in self._subscribers:
            for queue in self._subscribers[key]:
                try:
                    queue.put_nowait({
                        "key": key,
                        "value": value,
                        "timestamp": datetime.now().isoformat()
                    })
                except asyncio.QueueFull:
                    logger.warning(f"[Blackboard] Queue full for key: {key}")


class SharedContext:
    """
    共享上下文 - 多Agent协作的数据平面
    
    提供统一的资源访问和数据共享接口：
    - 协作黑板：Agent间临时数据交换
    - 产出物仓库：持久化结果存储
    - 共享记忆：跨会话记忆检索
    - 资源缓存：资源实例共享
    
    @example
    ```python
    context = SharedContext(session_id="session-123")
    
    # 更新任务结果
    await context.update(
        task_id="task-1",
        result={"status": "completed"},
        artifacts={"report": "Analysis Report..."}
    )
    
    # 获取产出物
    artifact = context.get_artifact("report")
    
    # 添加记忆
    await context.add_memory(MemoryEntry(
        content="User wants to build a login module",
        source="coordinator"
    ))
    ```
    """
    
    def __init__(
        self,
        session_id: str,
        workspace: Optional[str] = None,
        max_memory_entries: int = 1000,
    ):
        self.session_id = session_id
        self.workspace = workspace
        self.created_at = datetime.now()
        
        self._blackboard = CollaborationBlackboard()
        self._artifacts: Dict[str, Artifact] = {}
        self._artifacts_by_producer: Dict[str, List[str]] = {}
        self._memory = SharedMemory(max_entries=max_memory_entries)
        self._resource_cache: Dict[str, Any] = {}
        
        self._lock = asyncio.Lock()
        
        logger.info(f"[SharedContext] Created for session: {session_id}")
    
    @property
    def blackboard(self) -> CollaborationBlackboard:
        """获取协作黑板"""
        return self._blackboard
    
    @property
    def memory(self) -> SharedMemory:
        """获取共享记忆"""
        return self._memory
    
    async def update(
        self,
        task_id: str,
        result: Any,
        artifacts: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        更新共享上下文
        
        Args:
            task_id: 任务ID
            result: 任务结果
            artifacts: 产出物字典 {name: content}
            metadata: 额外元数据
        """
        async with self._lock:
            await self._blackboard.set(
                f"task_result:{task_id}",
                result,
                source=task_id
            )
            
            if artifacts:
                for name, content in artifacts.items():
                    artifact_id = f"{task_id}:{name}"
                    artifact = Artifact(
                        name=name,
                        content=content,
                        produced_by=task_id,
                        metadata=metadata or {}
                    )
                    self._artifacts[artifact_id] = artifact
                    
                    if task_id not in self._artifacts_by_producer:
                        self._artifacts_by_producer[task_id] = []
                    self._artifacts_by_producer[task_id].append(artifact_id)
        
        logger.debug(f"[SharedContext] Updated task {task_id}")
    
    def get_artifact(
        self,
        name: str,
        task_id: Optional[str] = None,
    ) -> Optional[Artifact]:
        """
        获取产出物
        
        Args:
            name: 产出物名称
            task_id: 可选的任务ID，用于精确匹配
        
        Returns:
            Artifact或None
        """
        if task_id:
            artifact_id = f"{task_id}:{name}"
            return self._artifacts.get(artifact_id)
        
        for artifact_id, artifact in self._artifacts.items():
            if artifact.name == name:
                return artifact
        
        return None
    
    def get_artifacts_by_task(self, task_id: str) -> List[Artifact]:
        """获取任务的所有产出物"""
        artifact_ids = self._artifacts_by_producer.get(task_id, [])
        return [self._artifacts[aid] for aid in artifact_ids if aid in self._artifacts]
    
    def list_artifacts(self) -> List[Artifact]:
        """列出所有产出物"""
        return list(self._artifacts.values())
    
    async def add_memory(
        self,
        content: str,
        source: str,
        task_id: Optional[str] = None,
        importance: float = 0.5,
    ) -> str:
        """
        添加记忆
        
        Args:
            content: 记忆内容
            source: 来源Agent
            task_id: 关联任务ID
            importance: 重要性分数
        
        Returns:
            记忆条目ID
        """
        entry = MemoryEntry(
            content=content,
            source=source,
            task_id=task_id,
            importance=importance,
        )
        return await self._memory.add(entry)
    
    async def search_memory(
        self,
        query: str,
        k: int = 5,
    ) -> List[MemoryEntry]:
        """搜索记忆"""
        return await self._memory.search(query, k)
    
    def set_resource(
        self,
        resource_type: str,
        resource: Any,
    ) -> None:
        """
        设置共享资源
        
        Args:
            resource_type: 资源类型
            resource: 资源实例
        """
        self._resource_cache[resource_type] = resource
        logger.debug(f"[SharedContext] Cached resource: {resource_type}")
    
    def get_resource(
        self,
        resource_type: str,
    ) -> Optional[Any]:
        """
        获取共享资源
        
        Args:
            resource_type: 资源类型
        
        Returns:
            资源实例或None
        """
        return self._resource_cache.get(resource_type)
    
    def has_resource(self, resource_type: str) -> bool:
        """检查资源是否存在"""
        return resource_type in self._resource_cache
    
    async def set_blackboard_value(
        self,
        key: str,
        value: Any,
    ) -> int:
        """设置黑板值"""
        return await self._blackboard.set(key, value)
    
    async def get_blackboard_value(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """获取黑板值"""
        return await self._blackboard.get(key, default)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "session_id": self.session_id,
            "workspace": self.workspace,
            "created_at": self.created_at.isoformat(),
            "artifact_count": len(self._artifacts),
            "memory_entries": len(self._memory._entries),
            "cached_resources": list(self._resource_cache.keys()),
            "blackboard_keys": len(self._blackboard._data),
        }
    
    async def export_state(self) -> Dict[str, Any]:
        """导出状态"""
        return {
            "session_id": self.session_id,
            "artifacts": {
                aid: {
                    "name": a.name,
                    "content": str(a.content)[:500] if a.content else None,
                    "produced_by": a.produced_by,
                    "produced_at": a.produced_at.isoformat(),
                }
                for aid, a in self._artifacts.items()
            },
            "blackboard": dict(self._blackboard._data),
            "memory": [
                {
                    "content": e.content[:200],
                    "source": e.source,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in self._memory._entries[-20:]
            ],
        }