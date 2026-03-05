"""
Simplified Memory Module - Inspired by opencode/openclaw design patterns.

This module provides a simplified memory system with:
- SimpleMemory: Basic in-memory storage
- SessionMemory: Session-scoped memory management
- MemoryManager: Unified memory operations
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class MemoryScope(str, Enum):
    """Memory scope for isolation."""

    GLOBAL = "global"
    SESSION = "session"
    TASK = "task"


class MemoryPriority(str, Enum):
    """Memory entry priority."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MemoryEntry:
    """A single memory entry."""

    content: str
    role: str = "assistant"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: MemoryPriority = MemoryPriority.NORMAL
    scope: MemoryScope = MemoryScope.SESSION
    entry_id: Optional[str] = None
    parent_id: Optional[str] = None
    tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "priority": self.priority.value,
            "scope": self.scope.value,
            "entry_id": self.entry_id,
            "parent_id": self.parent_id,
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            content=data.get("content", ""),
            role=data.get("role", "assistant"),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            priority=MemoryPriority(data.get("priority", "normal")),
            scope=MemoryScope(data.get("scope", "session")),
            entry_id=data.get("entry_id"),
            parent_id=data.get("parent_id"),
            tokens=data.get("tokens", 0),
        )


class BaseMemory(ABC):
    """Abstract base class for memory implementations."""

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry."""
        pass

    @abstractmethod
    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a memory entry by ID."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
        scope: Optional[MemoryScope] = None,
    ) -> List[MemoryEntry]:
        """Search memory entries."""
        pass

    @abstractmethod
    async def clear(self, scope: Optional[MemoryScope] = None) -> int:
        """Clear memory entries."""
        pass

    @abstractmethod
    async def count(self, scope: Optional[MemoryScope] = None) -> int:
        """Count memory entries."""
        pass


class SimpleMemory(BaseMemory):
    """
    Simple in-memory storage implementation.

    Thread-safe for single-process usage.
    Provides basic memory operations without persistence.
    """

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, MemoryEntry] = {}
        self._session_entries: Dict[str, List[str]] = {}
        self._max_entries = max_entries
        self._lock = None

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry."""
        import uuid

        if entry.entry_id is None:
            entry.entry_id = uuid.uuid4().hex

        self._entries[entry.entry_id] = entry

        if entry.scope == MemoryScope.SESSION and entry.metadata.get("session_id"):
            session_id = entry.metadata["session_id"]
            if session_id not in self._session_entries:
                self._session_entries[session_id] = []
            self._session_entries[session_id].append(entry.entry_id)

        if len(self._entries) > self._max_entries:
            await self._evict_old_entries()

        return entry.entry_id

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a memory entry by ID."""
        return self._entries.get(entry_id)

    async def search(
        self,
        query: str,
        limit: int = 10,
        scope: Optional[MemoryScope] = None,
    ) -> List[MemoryEntry]:
        """Search memory entries by content match."""
        results = []
        query_lower = query.lower()

        for entry in self._entries.values():
            if scope and entry.scope != scope:
                continue
            if query_lower in entry.content.lower():
                results.append(entry)
                if len(results) >= limit:
                    break

        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results

    async def clear(self, scope: Optional[MemoryScope] = None) -> int:
        """Clear memory entries."""
        if scope is None:
            count = len(self._entries)
            self._entries.clear()
            self._session_entries.clear()
            return count

        to_remove = [
            eid for eid, entry in self._entries.items() if entry.scope == scope
        ]
        for eid in to_remove:
            del self._entries[eid]

        if scope == MemoryScope.SESSION:
            self._session_entries.clear()

        return len(to_remove)

    async def count(self, scope: Optional[MemoryScope] = None) -> int:
        """Count memory entries."""
        if scope is None:
            return len(self._entries)
        return sum(1 for e in self._entries.values() if e.scope == scope)

    async def _evict_old_entries(self) -> None:
        """Evict oldest entries when capacity is reached."""
        sorted_entries = sorted(self._entries.items(), key=lambda x: x[1].timestamp)

        to_remove = len(self._entries) - self._max_entries + 100
        if to_remove > 0:
            for eid, _ in sorted_entries[:to_remove]:
                del self._entries[eid]


class SessionMemory:
    """
    Session-scoped memory management.

    Provides isolated memory for different sessions/agents.
    Inspired by openclaw's session management.
    """

    def __init__(self, memory: Optional[BaseMemory] = None):
        self._memory = memory or SimpleMemory()
        self._session_id: Optional[str] = None
        self._messages: List[MemoryEntry] = []

    async def start_session(self, session_id: Optional[str] = None) -> str:
        """Start a new session."""
        import uuid

        self._session_id = session_id or uuid.uuid4().hex
        return self._session_id

    async def end_session(self) -> None:
        """End the current session."""
        if self._session_id:
            await self._memory.clear(MemoryScope.SESSION)
        self._session_id = None
        self._messages.clear()

    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID."""
        return self._session_id

    async def add_message(
        self,
        content: str,
        role: str = "assistant",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a message to the session."""
        if self._session_id is None:
            await self.start_session()

        entry = MemoryEntry(
            content=content,
            role=role,
            scope=MemoryScope.SESSION,
            metadata={
                **(metadata or {}),
                "session_id": self._session_id,
            },
        )

        entry_id = await self._memory.add(entry)
        self._messages.append(entry)
        return entry_id

    async def get_messages(
        self,
        limit: Optional[int] = None,
    ) -> List[MemoryEntry]:
        """Get session messages."""
        if limit:
            return self._messages[-limit:]
        return list(self._messages)

    async def get_context_window(
        self,
        max_tokens: int = 4096,
    ) -> List[Dict[str, str]]:
        """
        Get messages within token limit.

        Returns messages formatted for LLM context.
        """
        result = []
        total_tokens = 0

        for entry in reversed(self._messages):
            tokens = entry.tokens or len(entry.content.split()) * 2

            if total_tokens + tokens > max_tokens:
                break

            result.insert(
                0,
                {
                    "role": entry.role,
                    "content": entry.content,
                },
            )
            total_tokens += tokens

        return result

    async def search_history(
        self,
        query: str,
        limit: int = 5,
    ) -> List[MemoryEntry]:
        """Search session history."""
        return await self._memory.search(
            query,
            limit=limit,
            scope=MemoryScope.SESSION,
        )


class MemoryManager:
    """
    Unified memory management.

    Coordinates between global and session memory.
    """

    def __init__(
        self,
        global_memory: Optional[BaseMemory] = None,
        session_memory: Optional[SessionMemory] = None,
    ):
        self._global_memory = global_memory or SimpleMemory()
        self._session_memory = session_memory or SessionMemory(self._global_memory)

    @property
    def session(self) -> SessionMemory:
        """Get session memory."""
        return self._session_memory

    @property
    def global_memory(self) -> BaseMemory:
        """Get global memory."""
        return self._global_memory

    async def add_global_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        priority: MemoryPriority = MemoryPriority.NORMAL,
    ) -> str:
        """Add to global memory."""
        entry = MemoryEntry(
            content=content,
            scope=MemoryScope.GLOBAL,
            priority=priority,
            metadata=metadata or {},
        )
        return await self._global_memory.add(entry)

    async def search_all(
        self,
        query: str,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Search both global and session memory."""
        results = await self._global_memory.search(query, limit=limit)
        session_results = await self._session_memory.search_history(query, limit=limit)

        seen = {r.entry_id for r in results}
        for r in session_results:
            if r.entry_id not in seen:
                results.append(r)

        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    async def clear_all(self) -> int:
        """Clear all memory."""
        global_count = await self._global_memory.clear()
        await self._session_memory.end_session()
        return global_count


def create_memory(
    max_entries: int = 10000,
    session_id: Optional[str] = None,
) -> MemoryManager:
    """Factory function to create a memory manager."""
    memory = SimpleMemory(max_entries=max_entries)
    session_memory = SessionMemory(memory)
    manager = MemoryManager(memory, session_memory)
    return manager
