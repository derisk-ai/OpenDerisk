from abc import ABC, abstractmethod
from typing import Optional

from derisk.core import Chunk
from derisk.rag.knowledge.base import Knowledge
from derisk.storage.full_text.base import FullTextStoreBase
from derisk.storage.knowledge_graph.base import KnowledgeGraphBase
from derisk.storage.vector_store.base import VectorStoreBase
from derisk_ext.rag import ChunkParameters


class DomainKnowledgeIndex(ABC):
    @abstractmethod
    async def extract(
        self, knowledge: Knowledge, chunk_parameter: ChunkParameters, **kwargs
    ) -> list[Chunk]:
        raise NotImplementedError

    @abstractmethod
    async def transform(self, chunks: list[Chunk], **kwargs) -> list[Chunk]:
        raise NotImplementedError

    @abstractmethod
    async def load(
        self,
        chunks: list[Chunk],
        vector_store: Optional[VectorStoreBase] = None,
        full_text_store: Optional[FullTextStoreBase] = None,
        kg_store: Optional[KnowledgeGraphBase] = None,
        keywords: bool = True,
        **kwargs,
    ):
        raise NotImplementedError

    async def clean(
        self,
        Chunks: list[Chunk],
        node_ids: Optional[list[str]],
        with_keywords: bool = True,
        **kwargs,
    ):
        raise NotImplementedError

    @property
    def domain_type(self):
        raise NotImplementedError
