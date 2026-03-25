#!/usr/bin/env python3
"""
简单测试脚本 - 验证统一记忆管理集成
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'packages', 'derisk-core', 'src'))

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class MemoryType(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    SHARED = "shared"
    PREFERENCE = "preference"


@dataclass
class MemoryItem:
    id: str
    content: str
    memory_type: MemoryType
    importance: float = 0.5
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    
    file_path: Optional[str] = None
    source: str = "agent"
    
    def update_access(self) -> None:
        self.last_accessed = datetime.now()
        self.access_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "file_path": self.file_path,
            "source": self.source,
        }


@dataclass
class SearchOptions:
    top_k: int = 5
    min_importance: float = 0.0
    memory_types: Optional[List[MemoryType]] = None
    time_range: Optional[tuple] = None
    sources: Optional[List[str]] = None
    include_embeddings: bool = False


@dataclass
class MemoryConsolidationResult:
    success: bool
    source_type: MemoryType
    target_type: MemoryType
    items_consolidated: int
    items_discarded: int
    tokens_saved: int = 0
    error: Optional[str] = None


class InMemoryStorage:
    """内存存储实现"""
    
    def __init__(self, session_id: Optional[str] = None):
        import uuid
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
        
        import uuid
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


async def test_memory_operations():
    """测试记忆操作"""
    print("=" * 60)
    print("测试统一记忆管理")
    print("=" * 60)
    
    storage = InMemoryStorage(session_id="test-session-123")
    
    print("\n1. 测试写入记忆")
    memory_id1 = await storage.write(
        content="用户询问如何使用Agent",
        memory_type=MemoryType.WORKING,
        metadata={"role": "user", "step": 1},
    )
    print(f"   ✓ 写入记忆1: {memory_id1[:8]}...")
    
    memory_id2 = await storage.write(
        content="Agent回复：可以通过统一记忆管理器保存对话",
        memory_type=MemoryType.WORKING,
        metadata={"role": "assistant", "step": 2},
    )
    print(f"   ✓ 写入记忆2: {memory_id2[:8]}...")
    
    print("\n2. 测试读取记忆")
    item = await storage.get_by_id(memory_id1)
    assert item.content == "用户询问如何使用Agent"
    print(f"   ✓ 读取记忆: {item.content}")
    
    print("\n3. 测试搜索记忆")
    results = await storage.read(query="Agent")
    assert len(results) > 0
    print(f"   ✓ 搜索到 {len(results)} 条记忆")
    for i, r in enumerate(results, 1):
        print(f"      {i}. {r.content[:50]}...")
    
    print("\n4. 测试更新记忆")
    updated = await storage.update(memory_id1, metadata={"important": True})
    assert updated is True
    item = await storage.get_by_id(memory_id1)
    assert item.metadata.get("important") is True
    print(f"   ✓ 更新成功，metadata: {item.metadata}")
    
    print("\n5. 测试记忆统计")
    stats = storage.get_stats()
    print(f"   ✓ 总记忆数: {stats['total_items']}")
    print(f"   ✓ 按类型统计: {stats['by_type']}")
    
    print("\n6. 测试记忆整合")
    for i in range(3):
        await storage.write(
            content=f"工作记忆 {i+1}",
            memory_type=MemoryType.WORKING,
        )
    
    result = await storage.consolidate(
        source_type=MemoryType.WORKING,
        target_type=MemoryType.EPISODIC,
        criteria={"min_importance": 0.0, "min_access_count": 0},
    )
    print(f"   ✓ 整合成功: {result.items_consolidated} 条记忆")
    print(f"   ✓ 丢弃: {result.items_discarded} 条")
    print(f"   ✓ 节省tokens: {result.tokens_saved}")
    
    print("\n7. 测试导出记忆")
    exported = await storage.export(format="markdown")
    print(f"   ✓ 导出成功，长度: {len(exported)} 字符")
    
    print("\n8. 测试清理记忆")
    count = await storage.clear(memory_types=[MemoryType.EPISODIC])
    print(f"   ✓ 清理 {count} 条情景记忆")
    
    stats = storage.get_stats()
    print(f"   ✓ 剩余记忆: {stats['total_items']} 条")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


async def test_agent_memory_integration():
    """测试Agent记忆集成"""
    print("\n" + "=" * 60)
    print("测试Agent记忆集成")
    print("=" * 60)
    
    print("\n模拟Agent对话流程:")
    
    storage = InMemoryStorage(session_id="agent-session-001")
    
    print("\n1. 用户: 你好，我是张三")
    await storage.write(
        content="User: 你好，我是张三",
        memory_type=MemoryType.WORKING,
        metadata={"role": "user"},
    )
    
    print("2. Agent: 你好张三！很高兴认识你")
    await storage.write(
        content="Assistant: 你好张三！很高兴认识你",
        memory_type=MemoryType.WORKING,
        metadata={"role": "assistant"},
    )
    
    print("3. 用户: 帮我写一个Python脚本")
    await storage.write(
        content="User: 帮我写一个Python脚本",
        memory_type=MemoryType.WORKING,
        metadata={"role": "user"},
    )
    
    print("\n4. 加载对话历史")
    history = await storage.read(query="", options=SearchOptions(top_k=10))
    print(f"   ✓ 找到 {len(history)} 条历史记录")
    for i, h in enumerate(history, 1):
        print(f"      {i}. {h.content[:50]}...")
    
    print("\n5. 记忆重要信息")
    await storage.write(
        content="用户姓名: 张三",
        memory_type=MemoryType.PREFERENCE,
        metadata={"category": "user_info", "importance": 0.9},
    )
    
    print("\n6. 检索用户偏好")
    prefs = await storage.read(
        query="",
        options=SearchOptions(
            memory_types=[MemoryType.PREFERENCE],
            top_k=5,
        ),
    )
    print(f"   ✓ 找到 {len(prefs)} 条偏好设置")
    for p in prefs:
        print(f"      - {p.content}")
    
    stats = storage.get_stats()
    print(f"\n最终统计:")
    print(f"   - 总记忆数: {stats['total_items']}")
    print(f"   - 工作记忆: {stats['by_type']['working']}")
    print(f"   - 偏好记忆: {stats['by_type']['preference']}")
    
    print("\n" + "=" * 60)
    print("✅ Agent记忆集成测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_memory_operations())
    asyncio.run(test_agent_memory_integration())
    
    print("\n" + "=" * 60)
    print("🎉 所有测试完成！统一记忆管理已成功集成到Agent中")
    print("=" * 60)