"""Memory Processor abstract interface.

This module defines the MemoryProcessor ABC that provides LLM-based
memory processing capabilities independent of the storage backend.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedMemory:
    """Memory content extracted from conversation."""

    content: str
    room: str = "general"
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsolidationResult:
    """Result of memory consolidation operation."""

    new_memories: List[ExtractedMemory] = field(default_factory=list)
    updated_memories: List[Dict[str, Any]] = field(default_factory=list)
    discarded_ids: List[str] = field(default_factory=list)


class MemoryProcessor(ABC):
    """Abstract interface for LLM-based memory processing.

    Implementations handle:
    - Extracting key content from conversations
    - Consolidating new content with existing memories
    - Scoring importance of memory content
    - Extracting knowledge graph triples
    """

    @abstractmethod
    async def extract_key_content(
        self,
        conversation: str,
        extraction_prompt: Optional[str] = None,
    ) -> List[ExtractedMemory]:
        """Extract key content from conversation.

        Args:
            conversation: The conversation text (user + assistant)
            extraction_prompt: Optional custom extraction prompt

        Returns:
            List of extracted memory items
        """
        pass

    @abstractmethod
    async def consolidate_memories(
        self,
        existing: List[Any],
        new: List[ExtractedMemory],
        consolidation_threshold: float = 0.7,
    ) -> ConsolidationResult:
        """Consolidate new content with existing memories.

        Args:
            existing: Existing memory entries from the store
            new: Newly extracted content
            consolidation_threshold: Similarity threshold for merging

        Returns:
            Consolidation result with new/updated/discarded memories
        """
        pass

    @abstractmethod
    async def score_importance(
        self,
        content: str,
        context: Optional[str] = None,
    ) -> float:
        """Score importance of memory content.

        Args:
            content: The memory content
            context: Optional context for scoring

        Returns:
            Importance score (0.0 - 1.0)
        """
        pass

    @abstractmethod
    async def extract_triples(
        self,
        content: str,
    ) -> List[Dict[str, Any]]:
        """Extract knowledge graph triples from content.

        Args:
            content: The content to extract triples from

        Returns:
            List of triple dicts with subject, predicate, object
        """
        pass
