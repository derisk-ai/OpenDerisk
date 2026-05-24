"""Enhanced memory search with hybrid retrieval, temporal decay, and MMR re-ranking.

Borrows from OpenClaw's search architecture:
1. Hybrid search: Vector KNN + FTS5 BM25 merged with configurable weights
2. Temporal decay: exp(-lambda * ageDays) for time-sensitive memories
3. MMR re-ranking: diversity-aware result ordering
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SearchResult:
    """Unified search result."""

    id: str
    content: str
    score: float  # 0.0 - 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    wing: str = ""
    room: str = ""
    created_at: Optional[str] = None


@dataclass
class HybridSearchConfig:
    """Configuration for hybrid search."""

    # Weights for merging vector and keyword results
    vector_weight: float = 0.6
    keyword_weight: float = 0.4

    # Temporal decay
    temporal_decay_enabled: bool = True
    temporal_decay_halflife: int = 30  # days

    # MMR re-ranking
    mmr_enabled: bool = True
    mmr_diversity: float = 0.5  # 0 = no diversity, 1 = max diversity

    # Filters
    min_score: float = 0.0


class HybridSearchEngine:
    """Enhanced search with hybrid retrieval, temporal decay, and MMR."""

    async def search(
        self,
        query: str,
        store: Any,  # MemoryStoreBase
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        config: Optional[HybridSearchConfig] = None,
    ) -> List[SearchResult]:
        """Search with enhanced retrieval.

        Args:
            query: Search query
            store: MemoryStoreBase instance
            top_k: Number of results
            wing: Optional wing filter
            room: Optional room filter
            config: Search configuration

        Returns:
            Ranked list of search results
        """
        config = config or HybridSearchConfig()

        # Step 1: Vector search (existing)
        vector_results = await self._vector_search(
            query, store, top_k * 2, wing, room,
        )

        # Step 2: Keyword search (FTS if available)
        keyword_results = await self._keyword_search(
            query, store, top_k * 2, wing, room,
        )

        # Step 3: Merge hybrid results
        merged = self._merge_hybrid(
            vector_results,
            keyword_results,
            config,
        )

        # Step 4: Apply temporal decay
        if config.temporal_decay_enabled:
            merged = self._apply_temporal_decay(
                merged,
                halflife_days=config.temporal_decay_halflife,
            )

        # Step 5: MMR re-ranking for diversity
        if config.mmr_enabled:
            merged = self._mmr_rerank(
                merged,
                diversity=config.mmr_diversity,
                top_k=top_k,
            )
        else:
            merged = merged[:top_k]

        # Step 6: Filter by min score
        return [r for r in merged if r.score >= config.min_score][:top_k]

    async def _vector_search(
        self,
        query: str,
        store: Any,
        top_k: int,
        wing: Optional[str],
        room: Optional[str],
    ) -> List[SearchResult]:
        """Vector similarity search."""
        try:
            entries = await store.asearch_memory(
                query=query,
                top_k=top_k,
                wing=wing,
                room=room,
            )
            return [
                SearchResult(
                    id=e.id,
                    content=e.content,
                    score=e.score or 0.5,
                    metadata=e.metadata or {},
                    wing=getattr(e, "wing", wing or ""),
                    room=getattr(e, "room", room or ""),
                    created_at=getattr(e, "created_at", None),
                )
                for e in entries
            ]
        except Exception:
            return []

    async def _keyword_search(
        self,
        query: str,
        store: Any,
        top_k: int,
        wing: Optional[str],
        room: Optional[str],
    ) -> List[SearchResult]:
        """Keyword search (BM25-style).

        Falls back to simple text matching if FTS is not available.
        """
        try:
            # Check if store supports full_text_search
            if hasattr(store, "full_text_search"):
                results = store.full_text_search(query, top_k)
                return [
                    SearchResult(
                        id=r.get("id", ""),
                        content=r.get("content", ""),
                        score=r.get("score", 0.3),
                        wing=r.get("wing", wing or ""),
                        room=r.get("room", room or ""),
                    )
                    for r in results
                ]

            # Fallback: simple text matching
            all_entries = await store.asearch_memory(
                query=query,
                top_k=top_k * 3,
                wing=wing,
                room=room,
            )

            query_lower = query.lower()
            keyword_results = []
            for e in all_entries:
                content_lower = e.content.lower()
                # Simple keyword overlap score
                overlap = sum(1 for word in query_lower.split() if word in content_lower)
                score = overlap / max(1, len(query_lower.split()))
                if score > 0:
                    keyword_results.append(
                        SearchResult(
                            id=e.id,
                            content=e.content,
                            score=score * 0.5,  # Lower weight than vector
                            wing=getattr(e, "wing", wing or ""),
                            room=getattr(e, "room", room or ""),
                        )
                    )

            keyword_results.sort(key=lambda r: r.score, reverse=True)
            return keyword_results[:top_k]

        except Exception:
            return []

    def _merge_hybrid(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        config: HybridSearchConfig,
    ) -> List[SearchResult]:
        """Merge vector and keyword results with configurable weights."""
        # Index by id
        seen: Dict[str, SearchResult] = {}

        for r in vector_results:
            seen[r.id] = SearchResult(
                id=r.id,
                content=r.content,
                score=r.score * config.vector_weight,
                metadata=r.metadata,
                wing=r.wing,
                room=r.room,
                created_at=r.created_at,
            )

        for r in keyword_results:
            if r.id in seen:
                # Combine scores
                seen[r.id].score += r.score * config.keyword_weight
            else:
                seen[r.id] = SearchResult(
                    id=r.id,
                    content=r.content,
                    score=r.score * config.keyword_weight,
                    wing=r.wing,
                    room=r.room,
                )

        merged = list(seen.values())
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged

    def _apply_temporal_decay(
        self,
        results: List[SearchResult],
        halflife_days: int = 30,
    ) -> List[SearchResult]:
        """Apply exponential temporal decay based on creation time.

        decay = exp(-lambda * ageDays) where lambda = ln(2) / halflife
        """
        from datetime import datetime

        lambda_decay = math.log(2) / halflife_days
        now = datetime.now()

        for r in results:
            if r.created_at:
                try:
                    if isinstance(r.created_at, str):
                        created = datetime.fromisoformat(r.created_at)
                    else:
                        created = r.created_at

                    age_days = (now - created).total_seconds() / 86400
                    decay = math.exp(-lambda_decay * age_days)
                    r.score *= decay
                except (ValueError, TypeError):
                    pass  # Keep original score if parsing fails

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _mmr_rerank(
        self,
        results: List[SearchResult],
        diversity: float = 0.5,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Maximal Marginal Relevance re-ranking for diversity.

        MMR = argmax [ λ * relevance - (1-λ) * max_similarity_to_selected ]
        """
        if not results or len(results) <= 1:
            return results

        # Tokenize content for Jaccard similarity
        def tokenize(text: str) -> set:
            return set(text.lower().split())

        selected = []
        remaining = list(results)

        while len(selected) < top_k and remaining:
            best_score = -float("inf")
            best_idx = 0

            for i, r in enumerate(remaining):
                # Relevance score
                rel_score = r.score

                # Max similarity to already selected
                max_sim = 0.0
                if selected:
                    r_tokens = tokenize(r.content)
                    max_sim = max(
                        len(r_tokens & tokenize(s.content)) / max(1, len(r_tokens | tokenize(s.content)))
                        for s in selected
                    )

                # MMR score
                mmr_score = diversity * rel_score - (1 - diversity) * max_sim

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected
