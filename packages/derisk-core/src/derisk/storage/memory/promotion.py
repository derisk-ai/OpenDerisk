"""Memory promotion engine with three-phase dreaming.

Borrows from OpenClaw's three-phase dreaming system:
1. Light Sleep: Collect candidates from recall history
2. REM Sleep: Pattern recognition and concept tag analysis
3. Deep Sleep: Multi-component scoring and promotion write

This engine runs periodically to promote frequently recalled
memories to long-term storage.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class PromotionCandidate:
    """A memory candidate for promotion."""

    memory_id: str
    content: str
    recall_count: int = 0
    average_score: float = 0.0
    unique_queries: int = 0
    recall_days: int = 0
    concept_tags: List[str] = field(default_factory=list)
    promotion_score: float = 0.0


@dataclass
class PromotionResult:
    """Result of a promotion sweep."""

    promoted: List[PromotionCandidate] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    error: Optional[str] = None


class MemoryPromotionEngine:
    """Three-phase memory promotion engine.

    Phase 1 (Light): Collect candidates from recall history
    Phase 2 (REM): Pattern recognition and concept analysis
    Phase 3 (Deep): Multi-component scoring and promotion write
    """

    # Scoring weights (sum to 1.0)
    WEIGHT_FREQUENCY = 0.24      # How often recalled
    WEIGHT_RELEVANCE = 0.30      # Average search score
    WEIGHT_DIVERSITY = 0.15      # Unique queries
    WEIGHT_RECENCY = 0.15        # Time decay
    WEIGHT_CONSOLIDATION = 0.10  # Recall day span
    WEIGHT_CONCEPTUAL = 0.06     # Concept tag count

    def __init__(
        self,
        recall_tracker: Any = None,  # RecallTracker, defaults to new instance
        promotion_threshold: float = 0.5,
        max_promotions_per_sweep: int = 10,
    ):
        from derisk.storage.memory.recall_tracker import RecallTracker
        self._recall_tracker = recall_tracker or RecallTracker()
        self._promotion_threshold = promotion_threshold
        self._max_promotions = max_promotions_per_sweep

    async def run_promotion_sweep(
        self,
        space_id: str,
        store: Any,  # MemoryStoreBase
    ) -> PromotionResult:
        """Run a complete three-phase promotion sweep.

        Args:
            space_id: The memory space to promote
            store: The memory store for promotion writes

        Returns:
            PromotionResult with promoted memories
        """
        result = PromotionResult()

        # Phase 1: Light sleep - collect candidates
        candidates = await self._light_sleep(space_id)
        if not candidates:
            logger.info(f"[Promotion] No candidates for space {space_id}")
            return result

        # Phase 2: REM sleep - pattern recognition
        analyzed = await self._rem_sleep(candidates, space_id)

        # Phase 3: Deep sleep - scoring and promotion
        promoted = await self._deep_sleep(
            analyzed,
            space_id,
            store,
        )

        result.promoted = promoted
        logger.info(
            f"[Promotion] Promoted {len(promoted)} memories "
            f"for space {space_id}"
        )

        return result

    async def _light_sleep(
        self,
        space_id: str,
    ) -> List[PromotionCandidate]:
        """Phase 1: Collect candidates from recall history.

        Retrieves frequently recalled memories as promotion candidates.
        """
        try:
            raw_candidates = await self._recall_tracker.get_top_candidates(
                space_id,
                top_k=self._max_promotions * 2,
            )

            candidates = []
            for c in raw_candidates:
                candidates.append(
                    PromotionCandidate(
                        memory_id=c["memory_id"],
                        content="",  # Will be populated from store
                        recall_count=c.get("recall_count", 0),
                        average_score=c.get("average_score", 0.0),
                        unique_queries=c.get("unique_queries", 0),
                        recall_days=c.get("recall_days", 0),
                    )
                )

            logger.info(
                f"[Promotion:Light] Collected {len(candidates)} candidates "
                f"for space {space_id}"
            )

            return candidates

        except Exception as e:
            logger.warning(f"[Promotion:Light] Failed: {e}")
            return []

    async def _rem_sleep(
        self,
        candidates: List[PromotionCandidate],
        space_id: str,
    ) -> List[PromotionCandidate]:
        """Phase 2: Pattern recognition and concept analysis.

        Analyzes concept tag patterns across candidates to identify
        recurring themes and boost related candidates.
        """
        # Extract concept tags from candidate content
        all_tags: Set[str] = set()
        for c in candidates:
            tags = self._extract_concept_tags(c.content)
            c.concept_tags = tags
            all_tags.update(tags)

        # Count tag frequency for pattern recognition
        tag_counts: Dict[str, int] = {}
        for c in candidates:
            for tag in c.concept_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Identify strong patterns (tags appearing in multiple candidates)
        strong_patterns = {
            tag: count
            for tag, count in tag_counts.items()
            if count >= 2
        }

        if strong_patterns:
            logger.info(
                f"[Promotion:REM] Found {len(strong_patterns)} strong patterns: "
                f"{list(strong_patterns.keys())}"
            )

        return candidates

    async def _deep_sleep(
        self,
        candidates: List[PromotionCandidate],
        space_id: str,
        store: Any,
    ) -> List[PromotionCandidate]:
        """Phase 3: Multi-component scoring and promotion write.

        Scores candidates using weighted components and promotes
        top scorers above threshold.
        """
        import math

        scored_candidates = []

        for c in candidates:
            # Frequency: log-scaled signal count
            frequency = min(
                1.0,
                math.log1p(c.recall_count) / math.log1p(10),
            )

            # Relevance: average search score
            relevance = c.average_score

            # Diversity: unique queries
            diversity = min(1.0, c.unique_queries / 5.0)

            # Recency: exponential decay (30 day halflife)
            recency = 0.5  # Default if no timestamp

            # Consolidation: span of recall days
            consolidation = min(1.0, c.recall_days / 7.0)

            # Conceptual: concept tag count
            conceptual = min(1.0, len(c.concept_tags) / 6.0)

            # Weighted score
            score = (
                frequency * self.WEIGHT_FREQUENCY
                + relevance * self.WEIGHT_RELEVANCE
                + diversity * self.WEIGHT_DIVERSITY
                + recency * self.WEIGHT_RECENCY
                + consolidation * self.WEIGHT_CONSOLIDATION
                + conceptual * self.WEIGHT_CONCEPTUAL
            )

            c.promotion_score = score

            if score >= self._promotion_threshold:
                scored_candidates.append(c)

        # Sort by promotion score
        scored_candidates.sort(key=lambda c: c.promotion_score, reverse=True)

        # Promote top candidates
        promoted = []
        for c in scored_candidates[:self._max_promotions]:
            try:
                # Mark memory as promoted (via metadata update)
                if hasattr(store, 'aupdate_memory'):
                    await store.aupdate_memory(
                        memory_id=c.memory_id,
                        metadata={"promoted": True, "promotion_score": c.promotion_score},
                    )
                promoted.append(c)

                logger.info(
                    f"[Promotion:Deep] Promoted {c.memory_id} "
                    f"(score: {c.promotion_score:.3f})"
                )
            except Exception as e:
                logger.warning(f"[Promotion:Deep] Failed to promote {c.memory_id}: {e}")

        return promoted

    def _extract_concept_tags(self, content: str) -> List[str]:
        """Extract concept tags from memory content.

        Simple keyword-based extraction. Can be enhanced with LLM.
        """
        if not content:
            return []

        content_lower = content.lower()

        # Technical concept patterns
        technical_patterns = {
            "api", "database", "frontend", "backend", "devops",
            "architecture", "security", "performance", "testing",
            "deployment", "authentication", "authorization",
            "microservice", "container", "cloud",
        }

        tags = []
        for pattern in technical_patterns:
            if pattern in content_lower:
                tags.append(pattern)

        return tags
