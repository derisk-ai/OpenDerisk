"""Recall tracking for memory promotion decisions.

This module tracks memory retrieval history to inform promotion
decisions. Similar to OpenClaw's ShortTermRecallEntry pattern,
it records which memories were retrieved, for what queries, and
how often — enabling multi-component scoring for promotion.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RecallEntry:
    """A single recall event."""

    query: str
    space_id: str
    result_ids: List[str]
    result_scores: List[float]
    recalled_at: datetime = field(default_factory=datetime.now)

    @property
    def query_hash(self) -> str:
        return hashlib.md5(self.query.encode()).hexdigest()


@dataclass
class MemoryRecallStats:
    """Aggregated recall statistics for a memory."""

    memory_id: str
    recall_count: int = 0
    total_score: float = 0.0
    unique_queries: int = 0
    recall_days: List[str] = field(default_factory=list)
    last_recalled: Optional[datetime] = None
    concept_tags: List[str] = field(default_factory=list)

    @property
    def average_score(self) -> float:
        return self.total_score / max(1, self.record_count)

    @property
    def record_count(self) -> int:
        return self.recall_count


class RecallTracker:
    """Tracks memory retrieval history for promotion decisions."""

    def __init__(self):
        self._entries: List[RecallEntry] = []
        self._stats: Dict[str, MemoryRecallStats] = {}

    async def record(
        self,
        query: str,
        results: List[Any],
        space_id: str,
    ) -> None:
        """Record a retrieval event.

        Args:
            query: The search query
            results: List of MemoryEntry results
            space_id: The memory space ID
        """
        entry = RecallEntry(
            query=query,
            space_id=space_id,
            result_ids=[r.id for r in results],
            result_scores=[r.score or 0.0 for r in results],
        )
        self._entries.append(entry)

        # Update per-memory stats
        day_str = entry.recalled_at.strftime("%Y-%m-%d")
        for mem_id, score in zip(entry.result_ids, entry.result_scores):
            if mem_id not in self._stats:
                self._stats[mem_id] = MemoryRecallStats(memory_id=mem_id)
            stats = self._stats[mem_id]
            stats.recall_count += 1
            stats.total_score += score
            if day_str not in stats.recall_days:
                stats.recall_days.append(day_str)
            stats.last_recalled = entry.recalled_at

    async def get_recall_stats(
        self,
        space_id: str,
    ) -> Dict[str, MemoryRecallStats]:
        """Get recall statistics for a space.

        Args:
            space_id: The memory space ID

        Returns:
            Dict mapping memory_id to recall stats
        """
        return {
            mid: stats
            for mid, stats in self._stats.items()
            if any(
                e.space_id == space_id and mid in e.result_ids
                for e in self._entries
            )
        }

    async def get_top_candidates(
        self,
        space_id: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get top promotion candidates.

        Multi-component scoring:
        - recall_frequency (0.24): log(recall_count)
        - relevance (0.30): average search score
        - diversity (0.15): unique queries
        - recency (0.15): exponential decay
        - consolidation (0.10): recall day span

        Args:
            space_id: The memory space ID
            top_k: Number of candidates to return

        Returns:
            List of candidate dicts with scores
        """
        import math

        stats = await self.get_recall_stats(space_id)
        candidates = []

        for mid, s in stats.items():
            if s.recall_count == 0:
                continue

            # Frequency: log-scaled
            frequency = min(1.0, math.log1p(s.recall_count) / math.log1p(10))

            # Relevance: average score
            relevance = s.average_score

            # Diversity: unique queries / max
            diversity = min(1.0, s.unique_queries / 5.0)

            # Recency: exponential decay (halflife 30 days)
            if s.last_recalled:
                days_ago = (datetime.now() - s.last_recalled).days
                recency = math.exp(-math.log(2) / 30 * days_ago)
            else:
                recency = 0.0

            # Consolidation: span of recall days
            consolidation = min(1.0, len(s.recall_days) / 7.0)

            # Weighted score
            total = (
                frequency * 0.24
                + relevance * 0.30
                + diversity * 0.15
                + recency * 0.15
                + consolidation * 0.10
            )

            candidates.append({
                "memory_id": mid,
                "recall_count": s.recall_count,
                "average_score": s.average_score,
                "unique_queries": s.unique_queries,
                "recall_days": len(s.recall_days),
                "score": round(total, 4),
            })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:top_k]

    async def clear(self, space_id: Optional[str] = None) -> int:
        """Clear recall history.

        Args:
            space_id: If provided, only clear entries for this space

        Returns:
            Number of entries cleared
        """
        if space_id:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.space_id != space_id]
            return before - len(self._entries)
        else:
            count = len(self._entries)
            self._entries.clear()
            self._stats.clear()
            return count
