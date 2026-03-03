"""Unified Memory Manager that integrates vector store and file-backed storage."""

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from derisk.core import Embeddings
from derisk.storage.vector_store.base import VectorStoreBase

from .base import (
    MemoryConsolidationResult,
    MemoryItem,
    MemoryType,
    SearchOptions,
    UnifiedMemoryInterface,
)
from .file_backed_storage import FileBackedStorage


class UnifiedMemoryManager(UnifiedMemoryInterface):
    """Unified memory manager combining vector store and file-backed storage.
    
    Features:
    - Vector similarity search via vector store
    - Git-friendly file storage for team sharing
    - Claude Code compatible import syntax
    - Memory consolidation between layers
    """
    
    def __init__(
        self,
        project_root: str,
        vector_store: VectorStoreBase,
        embedding_model: Embeddings,
        session_id: Optional[str] = None,
        auto_sync_to_file: bool = True,
    ):
        """Initialize unified memory manager.
        
        Args:
            project_root: Project root directory
            vector_store: Vector store for semantic search
            embedding_model: Embedding model for vectorization
            session_id: Optional session ID
            auto_sync_to_file: Auto sync shared memories to file
        """
        self.project_root = project_root
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.session_id = session_id
        self.auto_sync_to_file = auto_sync_to_file
        
        self.file_storage = FileBackedStorage(project_root, session_id)
        
        self._memory_cache: Dict[str, MemoryItem] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the memory manager and load shared memory."""
        if self._initialized:
            return
        
        shared_items = await self.file_storage.load_shared_memory()
        
        for item in shared_items:
            if not item.embedding:
                item.embedding = await self.embedding_model.embed([item.content])
            
            self._memory_cache[item.id] = item
            
            await self._add_to_vector_store(item)
        
        if self.session_id:
            session_items = await self.file_storage.load_session_memory(self.session_id)
            for item in session_items:
                self._memory_cache[item.id] = item
        
        self._initialized = True
    
    async def _add_to_vector_store(self, item: MemoryItem) -> None:
        """Add a memory item to the vector store."""
        try:
            await self.vector_store.add([{
                "id": item.id,
                "content": item.content,
                "embedding": item.embedding,
                "metadata": {
                    **item.metadata,
                    "memory_type": item.memory_type.value,
                    "importance": item.importance,
                    "source": item.source,
                    "created_at": item.created_at.isoformat(),
                }
            }])
        except Exception as e:
            import logging
            logging.warning(f"Failed to add to vector store: {e}")
    
    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True,
    ) -> str:
        """Write a memory item."""
        await self.initialize()
        
        memory_id = str(uuid.uuid4())
        
        embedding = await self.embedding_model.embed([content])
        
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            embedding=embedding,
            metadata=metadata or {},
        )
        
        self._memory_cache[memory_id] = item
        
        await self._add_to_vector_store(item)
        
        if sync_to_file and self.auto_sync_to_file:
            if memory_type in [MemoryType.SHARED, MemoryType.SEMANTIC, MemoryType.PREFERENCE]:
                await self.file_storage.save(item, sync_to_shared=True)
            elif memory_type == MemoryType.WORKING and self.session_id:
                await self.file_storage.save(item)
        
        return memory_id
    
    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        """Read memory items matching query."""
        await self.initialize()
        
        options = options or SearchOptions()
        
        if options.memory_types:
            results = []
            for memory_id, item in self._memory_cache.items():
                if item.memory_type not in options.memory_types:
                    continue
                if item.importance < options.min_importance:
                    continue
                if query.lower() in item.content.lower():
                    results.append(item)
            return results[:options.top_k]
        
        return list(self._memory_cache.values())[:options.top_k]
    
    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """Search for similar memories using vector similarity."""
        await self.initialize()
        
        query_embedding = await self.embedding_model.embed([query])
        
        try:
            results = await self.vector_store.similarity_search(
                query_embedding,
                k=top_k,
                filters=filters,
            )
        except Exception:
            return await self.read(query, SearchOptions(top_k=top_k))
        
        items = []
        for result in results:
            memory_id = result.get("id", "")
            if memory_id in self._memory_cache:
                item = self._memory_cache[memory_id]
                item.update_access()
                items.append(item)
            else:
                item = MemoryItem(
                    id=memory_id,
                    content=result.get("content", ""),
                    memory_type=MemoryType(result.get("metadata", {}).get("memory_type", "working")),
                    embedding=result.get("embedding"),
                    importance=result.get("metadata", {}).get("importance", 0.5),
                    metadata=result.get("metadata", {}),
                )
                items.append(item)
        
        return items
    
    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """Get a memory item by ID."""
        await self.initialize()
        
        if memory_id in self._memory_cache:
            item = self._memory_cache[memory_id]
            item.update_access()
            return item
        
        return None
    
    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a memory item."""
        await self.initialize()
        
        if memory_id not in self._memory_cache:
            return False
        
        item = self._memory_cache[memory_id]
        
        if content:
            item.content = content
            item.embedding = await self.embedding_model.embed([content])
            
            try:
                await self.vector_store.add([{
                    "id": item.id,
                    "content": item.content,
                    "embedding": item.embedding,
                    "metadata": {
                        **item.metadata,
                        "memory_type": item.memory_type.value,
                        "importance": item.importance,
                    }
                }])
            except Exception:
                pass
        
        if metadata:
            item.metadata.update(metadata)
        
        return True
    
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory item."""
        await self.initialize()
        
        if memory_id not in self._memory_cache:
            return False
        
        del self._memory_cache[memory_id]
        
        try:
            await self.vector_store.delete([memory_id])
        except Exception:
            pass
        
        return True
    
    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> MemoryConsolidationResult:
        """Consolidate memories from one layer to another."""
        await self.initialize()
        
        criteria = criteria or {}
        min_importance = criteria.get("min_importance", 0.5)
        min_access_count = criteria.get("min_access_count", 1)
        max_age_hours = criteria.get("max_age_hours", 24)
        
        items_to_consolidate = []
        items_to_discard = []
        
        for item in self._memory_cache.values():
            if item.memory_type != source_type:
                continue
            
            age_hours = (datetime.now() - item.created_at).total_seconds() / 3600
            
            if (item.importance >= min_importance and 
                item.access_count >= min_access_count and
                age_hours >= max_age_hours):
                items_to_consolidate.append(item)
            else:
                items_to_discard.append(item)
        
        for item in items_to_consolidate:
            item.memory_type = target_type
            
            if target_type in [MemoryType.SHARED, MemoryType.SEMANTIC]:
                await self.file_storage.save(item, sync_to_shared=True)
        
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
        """Export memories to a specific format."""
        await self.initialize()
        
        items = list(self._memory_cache.values())
        
        if memory_types:
            items = [i for i in items if i.memory_type in memory_types]
        
        if format == "json":
            import json
            return json.dumps([i.to_dict() for i in items], indent=2, ensure_ascii=False)
        
        content = "# Exported Memory\n\n"
        for item in items:
            content += f"\n## [{item.memory_type.value}] {item.id}\n"
            content += f"Importance: {item.importance}\n"
            content += f"Created: {item.created_at.isoformat()}\n"
            content += f"Source: {item.source}\n\n"
            content += f"{item.content}\n"
            content += "---\n"
        
        return content
    
    async def import_from_file(
        self,
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED,
    ) -> int:
        """Import memories from a file."""
        await self.initialize()
        
        items = await self.file_storage.load(file_path, resolve_imports=True)
        
        for item in items:
            item.memory_type = memory_type
            
            if not item.embedding:
                item.embedding = await self.embedding_model.embed([item.content])
            
            self._memory_cache[item.id] = item
            await self._add_to_vector_store(item)
        
        return len(items)
    
    async def clear(
        self,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> int:
        """Clear memories."""
        await self.initialize()
        
        if not memory_types:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            return count
        
        ids_to_remove = [
            id for id, item in self._memory_cache.items()
            if item.memory_type in memory_types
        ]
        
        for id in ids_to_remove:
            del self._memory_cache[id]
        
        return len(ids_to_remove)
    
    async def archive_session(self) -> Dict[str, Any]:
        """Archive current session memory."""
        if not self.session_id:
            return {"archived": False, "reason": "No session ID"}
        
        return await self.file_storage.archive_session(self.session_id)
    
    async def reload_shared_memory(self) -> int:
        """Reload shared memory from files."""
        self._initialized = False
        await self.initialize()
        return len([i for i in self._memory_cache.values() if i.memory_type == MemoryType.SHARED])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        stats = {
            "total_items": len(self._memory_cache),
            "by_type": {},
            "by_source": {},
            "avg_importance": 0.0,
            "total_access_count": 0,
        }
        
        if not self._memory_cache:
            return stats
        
        for item in self._memory_cache.values():
            mt = item.memory_type.value
            stats["by_type"][mt] = stats["by_type"].get(mt, 0) + 1
            
            src = item.source
            stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
            
            stats["total_access_count"] += item.access_count
        
        stats["avg_importance"] = sum(i.importance for i in self._memory_cache.values()) / len(self._memory_cache)
        
        return stats