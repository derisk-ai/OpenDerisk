import json
import logging
from typing import List, Optional

from derisk.component import ComponentType, SystemApp
from derisk.core import Chunk, LLMClient, Document
from derisk.model import DefaultLLMClient
from derisk.model.cluster import WorkerManagerFactory
from derisk.rag.embedding.embedding_factory import EmbeddingFactory
from derisk.rag.retriever import EmbeddingRetriever, QueryRewrite, Ranker
from derisk.rag.retriever.base import BaseRetriever, RetrieverStrategy
from derisk.rag.transformer.keyword_extractor import KeywordExtractor
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util.executor_utils import ExecutorFactory, blocking_func_to_async
from derisk_ext.rag.retriever.doc_tree import TreeNode
from derisk_serve.rag.models.models import KnowledgeSpaceDao
from derisk_serve.rag.retriever.qa_retriever import QARetriever
from derisk_serve.rag.retriever.retriever_chain import RetrieverChain
from derisk_serve.rag.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class KnowledgeSpaceRetriever(BaseRetriever):
    """Knowledge Space retriever."""

    def __init__(
        self,
        space_id: str = None,
        top_k: Optional[int] = 4,
        query_rewrite: Optional[QueryRewrite] = None,
        rerank: Optional[Ranker] = None,
        llm_model: Optional[str] = None,
        retrieve_mode: Optional[str] = None,
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
        self._llm_model = llm_model or "aistudio/Qwen2-72B-Instruct"
        app_config = system_app.config.configs.get("app_config")
        self._top_k = top_k or app_config.rag.similarity_top_k
        self._retrieve_mode = retrieve_mode or RetrieverStrategy.SEMANTIC.value
        self._embedding_model = embedding_model or app_config.models.default_embedding
        self._system_app = system_app
        embedding_factory = self._system_app.get_component(
            "embedding_factory", EmbeddingFactory
        )
        embedding_fn = embedding_factory.create()

        space_dao = KnowledgeSpaceDao()
        space = space_dao.get_one({"knowledge_id": space_id})
        if space is None:
            space = space_dao.get_one({"id": space_id})
        if space is None:
            space = space_dao.get_one({"name": space_id})
        if space is None:
            raise ValueError(f"Knowledge space {space_id} not found")
        self._knowledge_id = space.knowledge_id
        self._storage_connector = self.storage_manager.get_storage_connector(
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
                    index_store=self._storage_connector,
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

    @property
    def rag_service(self):
        from derisk_serve.rag.service.service import Service as RagService

        return RagService.get_instance(self._system_app)

    @property
    def llm_client(self) -> LLMClient:
        worker_manager = self._system_app.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        return DefaultLLMClient(worker_manager, True)

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
        if self._retrieve_mode == RetrieverStrategy.SEMANTIC.value:
            logger.info("Starting Semantic retrieval")
            return await self.semantic_retrieve(query, score_threshold, filters)
        elif self._retrieve_mode == RetrieverStrategy.KEYWORD.value:
            logger.info("Starting Full Text retrieval")
            return await self.full_text_retrieve(query, self._top_k, filters)
        elif self._retrieve_mode == RetrieverStrategy.HYBRID.value:
            logger.info("Starting Hybrid retrieval")
            tasks = []
            import asyncio

            tasks.append(self.semantic_retrieve(query, score_threshold, filters))
            tasks.append(self.full_text_retrieve(query, self._top_k, filters))
            # tasks.append(self.tree_index_retrieve(query, self._top_k, filters))
            results = await asyncio.gather(*tasks)
            semantic_candidates = results[0]
            full_text_candidates = results[1]
            # tree_candidates = results[2]
            logger.info(
                f"Hybrid retrieval completed. "
                f"Found {len(semantic_candidates)} semantic candidates "
                f"and Found {len(full_text_candidates)} full text candidates."
                # f"and Found {len(tree_candidates)} tree candidates."
            )
            candidates = semantic_candidates + full_text_candidates
            # Remove duplicates
            unique_candidates = {chunk.content: chunk for chunk in candidates}
            for chunk in unique_candidates.values():
                chunk.query = query
            return list(unique_candidates.values())

    async def semantic_retrieve(
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

    async def full_text_retrieve(
        self,
        query: str,
        top_k: int,
        filters: Optional[MetadataFilters] = None,
    ) -> List[Chunk]:
        """Full Text Retrieve knowledge chunks with score.
        refer https://www.elastic.co/guide/en/elasticsearch/reference/8.9/
        index-modules-similarity.html;
        TF/IDF based similarity that has built-in tf normalization and is supposed to
        work better for short fields (like names). See Okapi_BM25 for more details.

        Args:
            query (str): query text.
            top_k (int): top k limit.
            filters: (Optional[MetadataFilters]) metadata filters.

        Return:
            List[Chunk]: list of chunks with score.
        """
        if self._storage_connector.is_support_full_text_search():
            return await self._storage_connector.afull_text_search(
                query, top_k, filters
            )
        else:
            logger.warning(
                "Full text search is not supported for this storage connector."
            )
            return []

    async def tree_index_retrieve(
        self, query: str, top_k: int, filters: Optional[MetadataFilters] = None
    ):
        """Search for keywords in the tree index."""
        # Check if the keyword is in the node title
        # If the node has children, recursively search in them
        # If the node is a leaf, check if it contains the keyword
        try:
            docs_res = self.rag_service.get_document_list(
                {
                    "knowledge_id": self._knowledge_id,
                }
            )
            docs = []
            for doc_res in docs_res:
                doc = Document(
                    content=doc_res.content,
                )
                chunks_res = self.rag_service.get_chunk_list(
                    {
                        "doc_id": doc_res.doc_id,
                    }
                )
                chunks = [
                    Chunk(
                        chunk_id=chunk_res.chunk_id,
                        content=chunk_res.content,
                        metadata=json.loads(chunk_res.meta_data),
                    )
                    for chunk_res in chunks_res
                ]
                doc.chunks = chunks
                docs.append(doc)
            keyword_extractor = KeywordExtractor(
                llm_client=self.llm_client, model_name=self._llm_model
            )
            from derisk_ext.rag.retriever.doc_tree import DocTreeRetriever

            tree_retriever = DocTreeRetriever(
                docs=docs,
                keywords_extractor=keyword_extractor,
                top_k=self._top_k,
                query_rewrite=self._query_rewrite,
                rerank=self._rerank,
            )
            candidates = []
            tree_nodes = await tree_retriever.aretrieve_with_scores(query, top_k, filters)
            # Convert tree nodes to chunks
            for node in tree_nodes:
                chunks = self._traverse(node)
                candidates.extend(chunks)
            return candidates
        except Exception as e:
            logger.error(f"Error in tree index retrieval: {e}")
            return []

    def _traverse(self, node: TreeNode):
        """Traverse the tree and search for the keyword."""
        # Check if the node has children
        result = []
        if node.children:
            for child in node.children:
                result.extend(self._traverse(child))
        else:
            # If the node is a leaf, check if it contains the keyword
            chunk_res = self.rag_service.get_chunk_list(
                {
                    "chunk_id": node.node_id,
                }
            )
            if chunk_res:
                result.append(
                    Chunk(
                        chunk_id=chunk_res[0].chunk_id,
                        content=chunk_res[0].content,
                        metadata=json.loads(chunk_res[0].meta_data),
                        retriever=node.retriever,
                    )
                )
        return result
