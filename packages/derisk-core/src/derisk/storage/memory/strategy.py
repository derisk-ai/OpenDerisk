"""Memory space strategy configuration.

This module defines per-space processing strategies that control
how each memory space extracts, consolidates, and manages memories.
"""

from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class MemorySpaceStrategy:
    """Processing strategy for a single memory space.

    Each memory space can have its own:
    - Extraction prompt (what to extract from conversations)
    - Consolidation threshold (when to merge similar memories)
    - Importance keywords (what content is considered important)
    - KG extraction toggle (whether to extract knowledge graph triples)
    """

    space_id: str
    extraction_prompt: Optional[str] = None
    consolidation_threshold: float = 0.7
    importance_keywords: Set[str] = field(default_factory=set)
    auto_extraction: bool = True
    kg_extraction: bool = False
    max_memories_per_room: int = 100
    temporal_decay_enabled: bool = True
    temporal_decay_halflife: int = 30

    def matches_importance_keywords(self, content: str) -> bool:
        """Check if content contains importance keywords."""
        if not self.importance_keywords:
            return True
        content_lower = content.lower()
        return any(kw in content_lower for kw in self.importance_keywords)
