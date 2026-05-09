from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, Tuple

from derisk.core import Chunk
from derisk.storage.vector_store.base import VectorStoreBase
from derisk.storage.vector_store.filters import MetadataFilter, MetadataFilters

from .case_context import (
    KEY_APP_CODE,
    KEY_ENVIRONMENT,
    is_memory_search_scope_app_wildcard,
    is_memory_search_scope_env_wildcard,
    vector_metadata_from_case,
)
from .models import CandidateCase

logger = logging.getLogger(__name__)

MEMORY_CASE_VECTOR_NAME = "memory_case_candidate"


class MemoryCaseVectorStoreSource(Protocol):
    """Vends a vector store by logical index name (implemented by serve ``StorageManager``)."""

    def create_vector_store(
        self,
        index_name: str,
        extra_indexes: Optional[List[str]] = None,
    ) -> Optional[VectorStoreBase]:
        ...


class CandidateCaseVectorIndex(ABC):
    @abstractmethod
    async def upsert(self, case: CandidateCase) -> None:
        pass

    @abstractmethod
    async def search(self, query: str, case_scope: dict, top_k: int) -> List[str]:
        pass

    @abstractmethod
    async def search_with_scores(
        self, query: str, case_scope: dict, top_k: int
    ) -> List[Tuple[str, float]]:
        pass

    @abstractmethod
    async def invalidate(self, case_id: str) -> None:
        pass


class LazyCandidateCaseVectorIndex(CandidateCaseVectorIndex):
    """Defers vector store creation until first use, so WorkerManagerFactory
    has time to be registered (it is initialised *after* serve ``init_app``).
    """

    def __init__(self, storage_manager: Optional[MemoryCaseVectorStoreSource]) -> None:
        self._storage_manager = storage_manager
        self._real: Optional[CandidateCaseVectorIndex] = None

    def _ensure(self) -> CandidateCaseVectorIndex:
        if self._real is not None:
            return self._real
        self._real = _build_real_index(self._storage_manager)
        return self._real

    async def upsert(self, case: CandidateCase) -> None:
        await self._ensure().upsert(case)

    async def search(
        self, query: str, case_scope: dict, top_k: int
    ) -> List[str]:
        return await self._ensure().search(query, case_scope, top_k)

    async def search_with_scores(
        self, query: str, case_scope: dict, top_k: int
    ) -> List[Tuple[str, float]]:
        return await self._ensure().search_with_scores(query, case_scope, top_k)

    async def invalidate(self, case_id: str) -> None:
        await self._ensure().invalidate(case_id)


class EmptyCandidateCaseVectorIndex(CandidateCaseVectorIndex):
    async def upsert(self, case: CandidateCase) -> None:
        return None

    async def search(self, query: str, case_scope: dict, top_k: int) -> List[str]:
        return []

    async def search_with_scores(
        self, query: str, case_scope: dict, top_k: int
    ) -> List[Tuple[str, float]]:
        return []

    async def invalidate(self, case_id: str) -> None:
        return None


class ChromaCandidateCaseVectorIndex(CandidateCaseVectorIndex):
    def __init__(self, vector_store: VectorStoreBase):
        self._vector_store = vector_store

    async def upsert(self, case: CandidateCase) -> None:
        chunk = Chunk(
            chunk_id=case.case_id,
            content=case.markdown_summary or case.symptom_summary,
            metadata=vector_metadata_from_case(case.case_id, case.metadata),
        )
        await self._vector_store.aload_document([chunk])

    async def search(self, query: str, case_scope: dict, top_k: int) -> List[str]:
        if self._vector_store is None:
            return []
        fl: List[MetadataFilter] = []
        if not is_memory_search_scope_app_wildcard(case_scope):
            fl.append(
                MetadataFilter(key=KEY_APP_CODE, value=case_scope.get(KEY_APP_CODE)),
            )
        if not is_memory_search_scope_env_wildcard(case_scope):
            fl.append(
                MetadataFilter(
                    key=KEY_ENVIRONMENT, value=case_scope.get(KEY_ENVIRONMENT),
                ),
            )
        filters = MetadataFilters(filters=fl) if fl else None
        chunks = self._vector_store.similar_search_with_scores(
            text=query, topk=top_k, score_threshold=0.0, filters=filters
        )
        return [chunk.metadata.get("case_id") for chunk in chunks if chunk.metadata]

    async def search_with_scores(
        self, query: str, case_scope: dict, top_k: int
    ) -> List[Tuple[str, float]]:
        if self._vector_store is None:
            return []
        fl: List[MetadataFilter] = []
        if not is_memory_search_scope_app_wildcard(case_scope):
            fl.append(
                MetadataFilter(key=KEY_APP_CODE, value=case_scope.get(KEY_APP_CODE)),
            )
        if not is_memory_search_scope_env_wildcard(case_scope):
            fl.append(
                MetadataFilter(
                    key=KEY_ENVIRONMENT, value=case_scope.get(KEY_ENVIRONMENT),
                ),
            )
        filters = MetadataFilters(filters=fl) if fl else None
        chunks = self._vector_store.similar_search_with_scores(
            text=query, topk=top_k, score_threshold=0.0, filters=filters
        )
        return [
            (chunk.metadata.get("case_id", ""), chunk.score)
            for chunk in chunks
            if chunk.metadata and chunk.metadata.get("case_id")
        ]

    async def invalidate(self, case_id: str) -> None:
        if self._vector_store is None:
            return
        try:
            await self._vector_store.update_by_chunk_ids(
                [case_id], {"metadata.lifecycle": "stale"}
            )
        except Exception:
            logger.warning(
                "failed to mark memory case stale in vector index: %s",
                case_id,
            )


def _build_real_index(
    storage_manager: Optional[MemoryCaseVectorStoreSource],
) -> CandidateCaseVectorIndex:
    if not storage_manager:
        return EmptyCandidateCaseVectorIndex()
    try:
        store = storage_manager.create_vector_store(MEMORY_CASE_VECTOR_NAME)
        if store is None:
            logger.warning(
                "memory_case: vector store unavailable (embedding factory or RAG "
                "vector config missing); semantic search disabled, lexical DB search "
                "still works"
            )
            return EmptyCandidateCaseVectorIndex()
        return ChromaCandidateCaseVectorIndex(store)
    except Exception:
        logger.warning(
            "failed to init memory vector index, fallback to empty",
            exc_info=True,
        )
        return EmptyCandidateCaseVectorIndex()


def build_vector_index(
    storage_manager: Optional[MemoryCaseVectorStoreSource],
) -> CandidateCaseVectorIndex:
    """Return a lazy vector index so the real ChromaStore is only created
    on first tool call — by then WorkerManagerFactory is ready.
    """
    return LazyCandidateCaseVectorIndex(storage_manager)
