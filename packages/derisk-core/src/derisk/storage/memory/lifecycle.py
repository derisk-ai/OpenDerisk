"""Memory lifecycle hooks for session-level events.

Borrows from Hermes-Agent's MemoryProvider lifecycle hooks:
- on_turn_start: Pre-warm retrieval before each turn
- on_session_end: Final memory extraction at session boundary
- on_session_switch: Reset caches on session rotation
- on_pre_compress: Extract insights before context compression
- on_memory_write: Mirror built-in writes to external providers
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MemoryLifecycleHooks(ABC):
    """Abstract interface for memory lifecycle events.

    Implementations handle:
    - Session-level event processing
    - Memory synchronization across providers
    - Pre-compression insight extraction
    """

    @abstractmethod
    async def on_turn_start(
        self,
        turn_number: int,
        user_message: str,
        **kwargs,
    ) -> None:
        """Called at the start of each turn.

        Use for:
        - Pre-warming retrieval cache
        - Periodic maintenance
        """
        pass

    @abstractmethod
    async def on_turn_end(
        self,
        turn_number: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Called at the end of each turn.

        Use for:
        - Auto-writing memories
        - Sync to external providers
        """
        pass

    @abstractmethod
    async def on_session_end(
        self,
        conversation_history: List[Dict[str, Any]],
    ) -> None:
        """Called when a session ends.

        Use for:
        - Final memory extraction
        - Summarization
        - Cleanup
        """
        pass

    @abstractmethod
    async def on_session_switch(
        self,
        new_session_id: str,
        parent_session_id: str = "",
        reset: bool = False,
    ) -> None:
        """Called when switching sessions.

        Fires on /resume, /branch, /reset, context compression.

        Args:
            new_session_id: The session being switched to
            parent_session_id: Previous session (for lineage)
            reset: True if this is a genuinely new conversation
        """
        pass

    @abstractmethod
    async def on_pre_compress(
        self,
        messages_to_compress: List[Dict[str, Any]],
    ) -> str:
        """Called before context compression.

        Use to extract insights from messages about to be
        summarized/discarded.

        Returns:
            Text to include in the compression summary
        """
        pass


class DefaultLifecycleHooks(MemoryLifecycleHooks):
    """Default implementation with no-op handlers."""

    async def on_turn_start(
        self,
        turn_number: int,
        user_message: str,
        **kwargs,
    ) -> None:
        pass

    async def on_turn_end(
        self,
        turn_number: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        pass

    async def on_session_end(
        self,
        conversation_history: List[Dict[str, Any]],
    ) -> None:
        pass

    async def on_session_switch(
        self,
        new_session_id: str,
        parent_session_id: str = "",
        reset: bool = False,
    ) -> None:
        pass

    async def on_pre_compress(
        self,
        messages_to_compress: List[Dict[str, Any]],
    ) -> str:
        return ""
