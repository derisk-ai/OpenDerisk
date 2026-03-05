"""Base interfaces and data structures for Unified Memory Framework."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class MemoryType(str, Enum):
    """Memory type classification."""
    
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    SHARED = "shared"
    PREFERENCE = "preference"


@dataclass
class MemoryItem:
    """Unified memory item representation."""
    
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
        """Update access time and count."""
        self.last_accessed = datetime.now()
        self.access_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
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
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if "last_accessed" in data else datetime.now(),
            access_count=data.get("access_count", 0),
            file_path=data.get("file_path"),
            source=data.get("source", "agent"),
        )


@dataclass
class SearchOptions:
    """Options for memory search."""
    
    top_k: int = 5
    min_importance: float = 0.0
    memory_types: Optional[List[MemoryType]] = None
    time_range: Optional[Tuple[datetime, datetime]] = None
    sources: Optional[List[str]] = None
    include_embeddings: bool = False


@dataclass
class MemoryConsolidationResult:
    """Result of memory consolidation operation."""
    
    success: bool
    source_type: MemoryType
    target_type: MemoryType
    items_consolidated: int
    items_discarded: int
    tokens_saved: int = 0
    error: Optional[str] = None


class UnifiedMemoryInterface(ABC):
    """Abstract base class for unified memory management."""
    
    @abstractmethod
    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True,
    ) -> str:
        """Write a memory item.
        
        Args:
            content: The content to store
            memory_type: Type of memory
            metadata: Optional metadata
            sync_to_file: Whether to sync to file system
            
        Returns:
            Memory item ID
        """
        pass
    
    @abstractmethod
    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        """Read memory items matching query.
        
        Args:
            query: Search query
            options: Search options
            
        Returns:
            List of matching memory items
        """
        pass
    
    @abstractmethod
    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """Search for similar memories using vector similarity.
        
        Args:
            query: Search query
            top_k: Number of results to return
            filters: Optional filters
            
        Returns:
            List of similar memory items
        """
        pass
    
    @abstractmethod
    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """Get a memory item by ID.
        
        Args:
            memory_id: Memory item ID
            
        Returns:
            Memory item or None if not found
        """
        pass
    
    @abstractmethod
    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a memory item.
        
        Args:
            memory_id: Memory item ID
            content: New content (optional)
            metadata: New or updated metadata (optional)
            
        Returns:
            True if updated, False if not found
        """
        pass
    
    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory item.
        
        Args:
            memory_id: Memory item ID
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> MemoryConsolidationResult:
        """Consolidate memories from one layer to another.
        
        Args:
            source_type: Source memory type
            target_type: Target memory type
            criteria: Optional consolidation criteria
            
        Returns:
            Consolidation result
        """
        pass
    
    @abstractmethod
    async def export(
        self,
        format: str = "markdown",
        memory_types: Optional[List[MemoryType]] = None,
    ) -> str:
        """Export memories to a specific format.
        
        Args:
            format: Export format (markdown, json)
            memory_types: Types to export (all if None)
            
        Returns:
            Exported content
        """
        pass
    
    @abstractmethod
    async def import_from_file(
        self,
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED,
    ) -> int:
        """Import memories from a file.
        
        Args:
            file_path: Path to file
            memory_type: Type for imported memories
            
        Returns:
            Number of items imported
        """
        pass
    
    @abstractmethod
    async def clear(
        self,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> int:
        """Clear memories.
        
        Args:
            memory_types: Types to clear (all if None)
            
        Returns:
            Number of items cleared
        """
        pass