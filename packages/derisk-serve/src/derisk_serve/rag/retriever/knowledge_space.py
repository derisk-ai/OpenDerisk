from typing import List, Optional

from derisk.component import ComponentType, SystemApp
from derisk.core import Chunk
from derisk.rag.embedding.embedding_factory import EmbeddingFactory
from derisk.rag.retriever import EmbeddingRetriever, QueryRewrite, Ranker
from derisk.rag.retriever.base import BaseRetriever
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util.executor_utils import ExecutorFactory, blocking_func_to_async
from derisk_serve.rag.models.models import KnowledgeSpaceDao
from derisk_serve.rag.retriever.qa_retriever import QARetriever
from derisk_serve.rag.retriever.retriever_chain import RetrieverChain
from derisk_serve.rag.storage_manager import StorageManager


class KnowledgeSpaceRetriever(BaseRetriever):
    """Knowledge Space retriever."""

    def __init__(
        self,
        space_id: str = None,
        top_k: Optional[int] = 4,
        query_rewrite: Optional[QueryRewrite] = None,
        rerank: Optional[Ranker] = None,
        llm_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        system_app: SystemApp = None,
    ):
        """
        Args:
            space_id (str): knowledge space name
            top_k (Optional[int]): top k
            query_rewrite: (Optional[QueryRewrite]) query rewrite
            rerank: (Optional[Ranker]) rerank
        """
        if space_id is None:
            raise ValueError("space_id is required")
        self._space_id = space_id
        self._query_rewrite = query_rewrite
        self._rerank = rerank
        self._llm_model = llm_model
        app_config = system_app.config.configs.get("app_config")
        self._top_k = top_k or app_config.rag.similarity_top_k
        self._embedding_model = embedding_model or app_config.models.default_embedding
        self._system_app = system_app
        embedding_factory = self._system_app.get_component(
            "embedding_factory", EmbeddingFactory
        )
        embedding_fn = embedding_factory.create()

        space_dao = KnowledgeSpaceDao()
        space = space_dao.get_one({"id": space_id})
        if space is None:
            space = space_dao.get_one({"knowledge_id": space_id})
        if space is None:
            space = space_dao.get_one({"name": space_id})
        if space is None:
            raise ValueError(f"Knowledge space {space_id} not found")
        storage_connector = self.storage_manager.get_storage_connector(
            space.knowledge_id,
            space.storage_type,
            self._llm_model,
        )
        self._executor = self._system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()

        self._retriever_chain = RetrieverChain(
            retrievers=[
                QARetriever(
                    space_id=space.knowledge_id,
                    top_k=self._top_k,
                    embedding_fn=embedding_fn,
                    system_app=system_app,
                ),
                EmbeddingRetriever(
                    index_store=storage_connector,
                    top_k=self._top_k,
                    query_rewrite=self._query_rewrite,
                    rerank=self._rerank,
                ),
            ],
            executor=self._executor,
        )

    @property
    def storage_manager(self):
        return StorageManager.get_instance(self._system_app)

    def _retrieve(
        self, query: str, filters: Optional[MetadataFilters] = None
    ) -> List[Chunk]:
        """Retrieve knowledge chunks.

        Args:
            query (str): query text.
            filters: (Optional[MetadataFilters]) metadata filters.

        Return:
            List[Chunk]: list of chunks
        """
        candidates = self._retriever_chain.retrieve(query=query, filters=filters)
        return candidates

    def _retrieve_with_score(
        self,
        query: str,
        score_threshold: float,
        filters: Optional[MetadataFilters] = None,
    ) -> List[Chunk]:
        """Retrieve knowledge chunks with score.

        Args:
            query (str): query text
            score_threshold (float): score threshold
            filters: (Optional[MetadataFilters]) metadata filters.

        Return:
            List[Chunk]: list of chunks with score
        """
        candidates_with_scores = self._retriever_chain.retrieve_with_scores(
            query, score_threshold, filters
        )
        return candidates_with_scores

    async def _aretrieve(
        self, query: str, filters: Optional[MetadataFilters] = None
    ) -> List[Chunk]:
        """Retrieve knowledge chunks.

        Args:
            query (str): query text.
            filters: (Optional[MetadataFilters]) metadata filters.

        Return:
            List[Chunk]: list of chunks
        """
        candidates = await blocking_func_to_async(
            self._executor, self._retrieve, query, filters
        )
        return candidates

    async def _aretrieve_with_score(
        self,
        query: str,
        score_threshold: float,
        filters: Optional[MetadataFilters] = None,
    ) -> List[Chunk]:
        """Retrieve knowledge chunks with score.

        Args:
            query (str): query text.
            score_threshold (float): score threshold.
            filters: (Optional[MetadataFilters]) metadata filters.

        Return:
            List[Chunk]: list of chunks with score.
        """
        return await self._retriever_chain.aretrieve_with_scores(
            query, score_threshold, filters
        )
