from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from derisk.core import Chunk
from derisk.storage.vector_store.filters import MetadataFilter, MetadataFilters
from derisk_serve.mcp.memory_case.models import CandidateCase
from derisk_serve.rag.storage_manager import StorageManager

logger = logging.getLogger(__name__)

MEMORY_CASE_VECTOR_NAME = "memory_case_candidate"


class CandidateCaseVectorIndex(ABC):
    @abstractmethod
    async def upsert(self, case: CandidateCase) -> None:
        pass

    @abstractmethod
    async def search(self, query: str, case_scope: dict, top_k: int) -> List[str]:
        pass

    @abstractmethod
    async def invalidate(self, case_id: str) -> None:
        pass


class ChromaCandidateCaseVectorIndex(CandidateCaseVectorIndex):
    def __init__(self, storage_manager: StorageManager):
        self._storage_manager = storage_manager
        self._vector_store = storage_manager.create_vector_store(MEMORY_CASE_VECTOR_NAME)

    async def upsert(self, case: CandidateCase) -> None:
        chunk = Chunk(
            chunk_id=case.case_id,
            content=case.markdown_summary or case.symptom_summary,
            metadata={
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "team_id": case.team_id,
                "app_code": case.app_code,
                "environment": case.environment,
            },
        )
        await self._vector_store.aload_document([chunk])

    async def search(self, query: str, case_scope: dict, top_k: int) -> List[str]:
        filters = MetadataFilters(
            filters=[
                MetadataFilter(key="app_code", value=case_scope.get("app_code")),
                MetadataFilter(key="environment", value=case_scope.get("environment")),
            ]
        )
        if case_scope.get("tenant_id"):
            filters.filters.append(
                MetadataFilter(key="tenant_id", value=case_scope.get("tenant_id"))
            )
        if case_scope.get("team_id"):
            filters.filters.append(
                MetadataFilter(key="team_id", value=case_scope.get("team_id"))
            )
        chunks = self._vector_store.similar_search_with_scores(
            query=query, topk=top_k, filters=filters
        )
        return [chunk.metadata.get("case_id") for chunk in chunks if chunk.metadata]

    async def invalidate(self, case_id: str) -> None:
        try:
            await self._vector_store.update_by_chunk_ids(
                [case_id], {"metadata.lifecycle": "stale"}
            )
        except Exception:
            logger.warning("failed to mark memory case stale in vector index: %s", case_id)


class EmptyCandidateCaseVectorIndex(CandidateCaseVectorIndex):
    async def upsert(self, case: CandidateCase) -> None:
        return None

    async def search(self, query: str, case_scope: dict, top_k: int) -> List[str]:
        return []

    async def invalidate(self, case_id: str) -> None:
        return None


def build_vector_index(storage_manager: Optional[StorageManager]) -> CandidateCaseVectorIndex:
    if not storage_manager:
        return EmptyCandidateCaseVectorIndex()
    try:
        return ChromaCandidateCaseVectorIndex(storage_manager)
    except Exception:
        logger.warning("failed to init memory vector index, fallback to empty", exc_info=True)
        return EmptyCandidateCaseVectorIndex()

