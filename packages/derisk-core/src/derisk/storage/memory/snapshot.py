"""Frozen snapshot pattern for memory recall.

Borrows from Claude-Code and Hermes-Agent's approach:
- System prompt gets memory content captured at session start
- Mid-session writes update disk but NOT the snapshot
- This preserves prefix cache for the entire session
- Snapshot refreshes on next session start
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemorySnapshot:
    """Frozen snapshot of memory content.

    Captures memory retrieval results at session start.
    Subsequent writes to memory stores do NOT modify this snapshot.
    This ensures system prompt prefix cache is preserved.
    """

    def __init__(self):
        self._content: str = ""
        self._captured_at: Optional[str] = None
        self._memory_count: int = 0
        self._is_frozen: bool = False

    def capture(self, content: str, memory_count: int, captured_at: Optional[str] = None):
        """Capture a snapshot of memory content.

        Args:
            content: Formatted memory text for context injection
            memory_count: Number of memories captured
            captured_at: Timestamp of capture
        """
        from datetime import datetime

        self._content = content
        self._memory_count = memory_count
        self._captured_at = captured_at or datetime.now().isoformat()
        self._is_frozen = True

        logger.info(
            f"[MemorySnapshot] Captured {memory_count} memories at {self._captured_at}"
        )

    @property
    def content(self) -> str:
        """Get the frozen snapshot content."""
        return self._content

    @property
    def is_frozen(self) -> bool:
        """Check if snapshot is frozen."""
        return self._is_frozen

    @property
    def memory_count(self) -> int:
        """Number of memories in snapshot."""
        return self._memory_count

    @property
    def captured_at(self) -> Optional[str]:
        """Timestamp of capture."""
        return self._captured_at

    def refresh(self) -> bool:
        """Mark snapshot for refresh on next retrieval.

        Returns True if refresh is needed.
        """
        if self._is_frozen:
            self._is_frozen = False
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "content": self._content,
            "memory_count": self._memory_count,
            "captured_at": self._captured_at,
            "is_frozen": self._is_frozen,
        }


class FrozenSnapshotManager:
    """Manages frozen snapshots for multiple memory spaces.

    Each memory space has its own snapshot.
    Snapshots are captured at session start and frozen until session switch.
    """

    def __init__(self):
        self._snapshots: Dict[str, MemorySnapshot] = {}

    def get_snapshot(self, space_id: str) -> Optional[MemorySnapshot]:
        """Get the snapshot for a space.

        Args:
            space_id: Memory space ID

        Returns:
            MemorySnapshot or None if not captured
        """
        return self._snapshots.get(space_id)

    def capture_snapshot(
        self,
        space_id: str,
        content: str,
        memory_count: int,
    ) -> MemorySnapshot:
        """Capture a new snapshot for a space.

        Args:
            space_id: Memory space ID
            content: Formatted memory text
            memory_count: Number of memories

        Returns:
            The captured snapshot
        """
        snapshot = MemorySnapshot()
        snapshot.capture(content, memory_count)
        self._snapshots[space_id] = snapshot
        return snapshot

    def refresh_all(self) -> List[str]:
        """Mark all snapshots for refresh.

        Returns:
            List of space IDs that were refreshed
        """
        refreshed = []
        for space_id, snapshot in self._snapshots.items():
            if snapshot.refresh():
                refreshed.append(space_id)
        return refreshed

    def get_combined_content(self, space_ids: Optional[List[str]] = None) -> str:
        """Get combined content from all (or specified) snapshots.

        Args:
            space_ids: Optional list of space IDs to include

        Returns:
            Combined memory content string
        """
        ids = space_ids or list(self._snapshots.keys())
        contents = []

        for space_id in ids:
            snapshot = self._snapshots.get(space_id)
            if snapshot and snapshot.content:
                contents.append(f"### Memory Space: {space_id}\n\n{snapshot.content}")

        if not contents:
            return ""

        return "## Long-Term Memory Context\n\n" + "\n\n".join(contents)

    def clear(self, space_id: Optional[str] = None) -> None:
        """Clear snapshots.

        Args:
            space_id: If provided, only clear this space
        """
        if space_id:
            self._snapshots.pop(space_id, None)
        else:
            self._snapshots.clear()
