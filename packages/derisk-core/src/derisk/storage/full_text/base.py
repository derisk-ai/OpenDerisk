"""Full text store base class."""

import logging
from abc import abstractmethod
from concurrent.futures import Executor
from typing import List, Optional, Dict, Any, Union, Tuple

from derisk.core import Chunk, Embeddings
from derisk.storage.base import IndexStoreBase
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util.executor_utils import blocking_func_to_async

logger = logging.getLogger(__name__)


class FullTextStoreBase(IndexStoreBase):
    """Graph store base class."""

    def __init__(self, executor: Optional[Executor] = None):
        """Initialize vector store."""
        super().__init__(executor)

    @abstractmethod
    def load_document(self, chunks: List[Chunk]) -> List[str]:
        """Load document in index database.

        Args:
            chunks(List[Chunk]): document chunks.
        Return:
            List[str]: chunk ids.
        """

    @property
    def embeddings(self) -> Embeddings:
        """Get the embeddings."""
        pass

    async def aload_document(self, chunks: List[Chunk]) -> List[str]:
        """Async load document in index database.

        Args:
            chunks(List[Chunk]): document chunks.
        Return:
            List[str]: chunk ids.
        """
        return await blocking_func_to_async(self._executor, self.load_document, chunks)

    def upsert(self, data: List[Dict]) -> List[str]:
        """Async load document in index database.

        Args:
            data(List[Dict]): document chunks.
        Return:
            List[str]: chunk ids.
        """
        pass

    def update(
            self,
            query_conditions: Dict[str, Any],
            update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Internal helper to perform an update_by_query operation.

        Args:
            query_conditions: Dict[str, Any].
            update_data: A dictionary of key-value pairs representing the fields to update
                         and their new values.

        Returns:
            The response from the Elasticsearch _update_by_query API.
        """


    def search(
        self,
        query_criteria: Union[str, Dict[str, Any]],
        limit: int = 100,
        score_threshold: Optional[float] = None,
        offset: int = 0,
        source_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        sort_fields: Optional[List[Dict[str, Any]]] = None,
        collapse: Optional[Dict[str, Any]] = None,
        highlight_config: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Performs a search against the Zsearch (Elasticsearch) index.

        Args:
            query_criteria: The search query. Can be a simple string (e.g., "faulty server")
                            or a dictionary representing an Elasticsearch query DSL fragment
                            (e.g., {"match": {"content": "error"}}).
            limit: The maximum number of hits to return. Defaults to 100.
            score_threshold: Minimum _score a document must have to be included in results.
                             If None, all scores are included (up to limit).
            offset: The starting offset for results (for pagination). Defaults to 0.
            source_fields: A list of field names to include from the '_source' of each hit.
                           If None, all fields from _source are returned.
            exclude_fields: A list of field names to exclude from the '_source' of each hit.
            sort_fields: A list of dictionaries defining custom sort order,
                         e.g., [{"_score": {"order": "desc"}}] or [{"timestamp": {"order": "desc"}}]
                         If None, results are primarily sorted by relevance score in descending order.
            collapse: A dictionary defining how to collapse results, e.g., {"field": "knowledge_base_id"}.
            highlight_config: A dictionary defining how to highlight search results, e.g., {"fields": {"content": {}}}.

        Returns:
            A list of dictionaries, where each dictionary represents a found document segment
            with its ID, score, content, keywords, and metadata.
        """
        pass


    @abstractmethod
    def similar_search_with_scores(
        self,
        text,
        topk,
        score_threshold: float,
        filters: Optional[MetadataFilters] = None,
    ) -> List[Chunk]:
        """Similar search with scores in index database.

        Args:
            text(str): The query text.
            topk(int): The number of similar documents to return.
            score_threshold(int): score_threshold: Optional, a floating point value
                between 0 to 1
            filters(Optional[MetadataFilters]): metadata filters.
        """

    @abstractmethod
    def delete_by_ids(self, ids: str) -> List[str]:
        """Delete docs.

        Args:
            ids(str): The vector ids to delete, separated by comma.
        """

    def delete_vector_name(self, index_name: str):
        """Delete name."""

    def truncate(self) -> List[str]:
        """Truncate the collection."""
        raise NotImplementedError
