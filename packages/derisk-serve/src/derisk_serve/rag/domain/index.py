from abc import abstractmethod
from typing import List, Optional

from derisk.core import Chunk
from derisk.rag.knowledge.base import Knowledge
from derisk.storage.full_text.base import FullTextStoreBase
from derisk.storage.knowledge_graph.base import KnowledgeGraphBase
from derisk.storage.vector_store.base import VectorStoreBase
from derisk.util.tracer import root_tracer
from derisk_ext.rag import ChunkParameters
from derisk_ext.rag.chunk_manager import ChunkManager
from derisk_serve.rag.domain.base import DomainKnowledgeIndex


class DomainGeneralIndex(DomainKnowledgeIndex):
    async def extract(
        self, knowledge: Knowledge, chunk_parameter: ChunkParameters, **kwargs
    ) -> list[Chunk]:
        if not knowledge:
            raise ValueError("knowledge must be provided.")
        with root_tracer.start_span("DomainGeneralIndex.knowledge.load"):
            documents = knowledge.load()
        with root_tracer.start_span("DomainGeneralIndex.chunk_manager.split"):
            chunk_manager = ChunkManager(
                knowledge=knowledge, chunk_parameter=chunk_parameter
            )
            chunks = chunk_manager.split(documents)
            return chunks

    async def transform(self, chunks: list[Chunk], **kwargs) -> list[Chunk]:
        raise NotImplementedError

    async def load(
        self,
        chunks: list[Chunk],
        vector_store: Optional[VectorStoreBase] = None,
        full_text_store: Optional[FullTextStoreBase] = None,
        kg_store: Optional[KnowledgeGraphBase] = None,
        keywords: bool = True,
        max_chunks_once_load: int = 10,
        max_threads: int = 1,
        **kwargs,
    ) -> list[Chunk]:
        """Load knowledge chunks into storage."""
        if vector_store:
            vector_ids = await vector_store.aload_document_with_limit(
                chunks, max_chunks_once_load, max_threads
            )
            for chunk, vector_id in zip(chunks, vector_ids):
                chunk.vector_id = vector_id
        if full_text_store:
            await full_text_store.aload_document_with_limit(
                chunks, max_chunks_once_load, max_threads
            )
        if kg_store:
            await kg_store.aload_document_with_limit(
                chunks, max_chunks_once_load, max_threads
            )
        return chunks

    async def clean(
        self,
        chunks: list[Chunk],
        node_ids: Optional[list[str]],
        with_keywords: bool = True,
        **kwargs,
    ):
        raise NotImplementedError

    @property
    def domain_type(self):
        return "general"
