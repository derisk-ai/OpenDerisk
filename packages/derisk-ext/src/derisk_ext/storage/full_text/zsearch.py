import json
from dataclasses import dataclass, field
from typing import Union, Optional, Dict, Any, List, Tuple

import requests
import logging

from derisk.core import Chunk, Embeddings
from derisk.storage.base import IndexStoreConfig
from derisk.storage.full_text.base import FullTextStoreBase
from derisk.storage.vector_store.base import VectorStoreConfig
from derisk.storage.vector_store.filters import MetadataFilters

logger = logging.getLogger("derisk_ext.storage.full_text.zsearch")

@dataclass
class ZSearchStoreConfig(VectorStoreConfig):
    """Elasticsearch vector store config."""

    __type__ = "zsearch"

    endpoint: str = field(
        default="http://zsearch-et2.alipay.com:9999",
        metadata={
            "description": "The uri of elasticsearch store, if not set, "
            "will use the default uri."
        },
    )
    secret: str = field(
        default=None,
        metadata={
            "description": "The port of elasticsearch store, if not set, will use the "
            "default port."
        },
    )

    account: str = field(
        default=None,
        metadata={
            "description": "The alias of elasticsearch store, if not set, will use the "
            "default alias."
        },
    )
    index_name: str = field(
        default="index_name_test",
        metadata={
            "description": "The index name of elasticsearch store, if not set, will"
            " use "
            "the default index name."
        },
    )

    def create_store(self, **kwargs) -> "ZsearchStore":
        """Create Elastic store."""
        return ZsearchStore(vector_store_config=self, **kwargs)


class ZsearchStore(FullTextStoreBase):


    def __init__(self, vector_store_config: ZSearchStoreConfig,
                 name: Optional[str],
                 embedding_fn: Optional[Embeddings] = None,
    ):
        self._index_name = name
        self._zsearch_config = vector_store_config
        self._search_url = self._zsearch_config.endpoint + "/" + self._index_name + "/_search"
        self._client = requests.session()
        self._embedding_fn = embedding_fn
        self._client.auth = (self._zsearch_config.account, self._zsearch_config.secret)

    @property
    def embeddings(self) -> Embeddings:
        """Get the embeddings."""
        return self._embedding_fn

    def upsert(self, data: List[Dict], upsert: bool = False) -> List[str]:
        """
        将文档列表导入到 Zsearch。

        Args:
            data: 包含要导入文档数据的字典列表。每个字典应包含 '_id' 字段。
            upsert: 如果为 True，则使用 update + doc_as_upsert 行为（有则更新，无则新增）。
                    如果为 False (默认)，则使用 index 行为（有则替换，无则新增）。
        Returns:
            成功导入的文档 ID 列表。
        """
        logger.info(
            f"Starting document import for {len(data)} documents into index {self._index_name}."
        )
        successful_document_ids = []
        all_errors = []
        BATCH_SIZE = 1000
        if not data:
            logger.warning("No documents provided for import.")
            return []

        documents_to_index: List[Dict[str, Any]] = []
        for doc_dict in data:
            if self._embedding_fn and doc_dict.get("text_to_embed"):
                try:
                    text_to_embed = doc_dict.pop("text_to_embed")
                    embedding = self._embedding_fn.embed_documents([text_to_embed])[0]
                    doc_dict["combined_vector"] = embedding
                except Exception as e:
                    logger.error(
                        f"Failed to generate embedding for document: {doc_dict.get('_id', 'unknown_id')} error: {e}")
                    doc_dict["combined_vector"] = None
            documents_to_index.append(doc_dict)

        total_docs = len(documents_to_index)
        batches = [documents_to_index[i:i + BATCH_SIZE] for i in
                   range(0, total_docs, BATCH_SIZE)]
        total_batches = len(batches)

        # 根据 upsert 参数选择 bulk 操作类型
        bulk_action_type = "upsert" if upsert else "index"
        logger.info(f"Using bulk action type: '{bulk_action_type}' for import.")

        for batch_num, batch_docs in enumerate(batches, 1):
            logger.info(
                f"Processing batch {batch_num}/{total_batches}  - {len(batch_docs)} documents."
            )
            batch_result = self._bulk_import_batch(batch_docs, batch_num, bulk_action_type)
            successful_document_ids.extend(batch_result.get("successful_ids", []))

            if not batch_result["success"] or batch_result["failed"] > 0:
                all_errors.extend(batch_result["errors"])
                logger.error(
                    f"Batch {batch_num} had failures. Processed: {batch_result['processed']}, Failed: {batch_result['failed']}"
                )
                if batch_result.get("error_type"):
                    logger.error(
                        f"Batch {batch_num} error type: {batch_result['error_type']}, Message: {batch_result.get('error')}")

        if all_errors:
            logger.error(
                f"Document import completed with {len(all_errors)} errors.")
        logger.info(
            f"Document import complete for index {self._index_name}: "
            f"{len(successful_document_ids)}/{total_docs} documents processed successfully."
        )
        return successful_document_ids

    def load_document(self, chunks: List[Chunk]) -> List[str]:
        pass

    def similar_search_with_scores(self, text, topk, score_threshold: float,
                                   filters: Optional[MetadataFilters] = None) -> List[
        Chunk]:
        pass

    def delete_by_ids(self, ids: str) -> List[str]:
        pass

    def get_config(self) -> IndexStoreConfig:
        return self._zsearch_config

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
        highlight_config: Optional[Dict[str, Any]] = None,
        knn_query: Optional[Dict[str, Any]] = None,
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
            knn_query: A dictionary defining the KNN query, e.g., {"field": "combined_vector", "k": 10}
        Returns:
            A list of dictionaries, where each dictionary represents a found document segment
            with its ID, score, content, keywords, and metadata.
        """
        index_name = self._index_name

        payload = self._build_zsearch_query(
            query_criteria=query_criteria,
            limit=limit,
            score_threshold=score_threshold,
            offset=offset,
            source_fields=source_fields,
            exclude_fields=exclude_fields,
            sort_fields=sort_fields,
            collapse=collapse,
            highlight_config=highlight_config,
            knn_query=knn_query
        )

        logger.info(
            "Zsearch index name=%s, search_url=%s, payload=%s",
            index_name,
            self._search_url,
            json.dumps(payload, indent=4, ensure_ascii=False)
        )

        try:
            search_response = self._client.post(self._search_url, json=payload)

            search_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            search_result_json = search_response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during Zsearch query: {e.response.status_code} - {e.response.text}")
            raise e
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Zsearch: {e}")
            raise e
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout connecting to Zsearch: {e}")
            raise e
        except Exception as e:
            logger.error(f"An unexpected error occurred during Zsearch query: {e}")
            raise e

        hits = search_result_json.get("hits", {}).get("hits", [])
        total_hits = search_result_json.get("hits", {}).get("total", {}).get("value", 0)

        logger.info("Found %d total hits for query.", total_hits)
        return hits, total_hits


    def _build_zsearch_query(
            self,
            query_criteria: Union[str, Dict[str, Any]],
            limit: int,
            score_threshold: Optional[float] = 0.0,
            offset: Optional[int] = None,
            source_fields: Optional[List[str]] = None,
            exclude_fields: Optional[List[str]] = None,
            sort_fields: Optional[List[Dict[str, Any]]] = None,
            collapse: Optional[Dict[str, Any]] = None,
            highlight_config: Optional[Dict[str, Any]] = None,
            track_total_hits: Optional[bool] = True,
            knn_query: Optional[Dict[str, Any]] = None # NEW PARAMETER
    ) -> Dict[str, Any]:
        """
        Builds the Elasticsearch query payload based on input criteria and parameters.
        """
        es_query_body = {
            "size": limit,
            "from": offset,
            "query": {},
        }

        if isinstance(query_criteria, str):
            es_query_body["query"] = {
                "multi_match": {
                    "query": query_criteria,
                    "fields": ["content", "keywords", "faq^2"],
                    "type": "best_fields",
                }
            }
        elif isinstance(query_criteria, dict):
            es_query_body["query"] = query_criteria
        elif knn_query:
            es_query_body["knn"] = knn_query

        else:
            raise ValueError(
                "query_criteria must be a string or a dictionary representing ES query DSL.")


        if score_threshold is not None:
            es_query_body["min_score"] = score_threshold

        if source_fields:
            es_query_body["_source"] = source_fields

        if exclude_fields:
            es_query_body["_source"] = {
                "excludes": exclude_fields
            }

        if sort_fields:
            es_query_body["sort"] = sort_fields
        if collapse:
            es_query_body["collapse"] = collapse
        else:
            es_query_body["sort"] = [{"_score": {"order": "desc"}}]

        if highlight_config:
            es_query_body["highlight"] = highlight_config

        if track_total_hits:
            es_query_body["track_total_hits"] = track_total_hits
        return es_query_body

    def _bulk_import_batch(self, documents: List[Dict[str, Any]],
                           batch_num: int, bulk_action_type: str = "index") -> Dict[str, Any]:
        """
        导入单个批次的文档

        Args:
            documents: 单个批次的文档列表 (每个文档字典应包含 document_id)
            batch_num: 批次编号
            bulk_action_type: 批量操作类型，可以是 "index" (完全替换/新增) 或 "upsert" (更新/新增)

        Returns:
            批次导入结果，新增 'successful_ids' 列表
        """
        if not documents:
            return {
                "success": True,
                "batch": batch_num,
                "total": 0,
                "processed": 0,
                "failed": 0,
                "errors": [],
                "successful_ids": []
            }

        try:
            url = f"{self._zsearch_config.endpoint}/_bulk"
            payload_str = self._create_bulk_payload(documents, bulk_action_type)

            headers = {"Content-Type": "application/x-ndjson"}

            # Assuming self._client is your requests.Session object or similar
            response = self._client.post(
                url,
                data=payload_str.encode('utf-8'),
                headers=headers
            )
            response.raise_for_status()

            response_json = response.json()

            errors = []
            successful_ids_in_batch = []
            for item in response_json.get("items", []):
                op_key = next(iter(item.keys()))
                op_result = item.get(op_key, {})

                doc_id = op_result.get("_id")

                if "error" in op_result:
                    error_info = {
                        "document_id": doc_id,
                        "error": op_result["error"],
                        "op_type": op_key
                    }
                    errors.append(error_info)
                elif doc_id:
                    successful_ids_in_batch.append(doc_id)

            processed_count = len(successful_ids_in_batch)
            failed_count = len(errors)

            return {
                "success": failed_count == 0,
                "batch": batch_num,
                "total": len(documents),
                "processed": processed_count,
                "failed": failed_count,
                "errors": errors,
                "successful_ids": successful_ids_in_batch
            }

        except Exception as e:
            logger.error(f"Batch {batch_num} error during bulk import with action '{bulk_action_type}': {str(e)}")
            return {
                "success": False,
                "batch": batch_num,
                "total": len(documents),
                "processed": 0,
                "failed": len(documents),
                "error": str(e),
                "error_type": "RequestException" if isinstance(e, Exception) else "GeneralException", # Use requests.exceptions.RequestException in real code
                "successful_ids": []
            }


    def _create_bulk_payload(
            self,
            documents: List[Dict[str, Any]],
            bulk_action_type: str = "index"
            ) -> str:
        """
        Create the bulk payload for Zsearch.

        Args:
            documents: List of documents to be imported.
            bulk_action_type: Type of bulk action to perform. Defaults to "index".

        Returns:
            The bulk payload as a string.
        """
        payload_lines = []
        for doc in documents:
            _id = doc.pop("_id", None)
            if not _id:
                raise ValueError(
                    f"Document missing '_id' for bulk import: {doc}")

            doc_data = doc.copy()

            if bulk_action_type == "index":
                action = {"index": {"_id": str(_id), "_index": self._index_name}}
                payload_lines.append(json.dumps(action))
                payload_lines.append(json.dumps(doc_data))
            elif bulk_action_type == "upsert":
                action = {"update": {"_id": str(_id), "_index": self._index_name}}
                payload_lines.append(json.dumps(action))
                payload_lines.append(
                    json.dumps({"doc": doc_data, "doc_as_upsert": True}))
            else:
                raise ValueError(
                    f"Unsupported bulk action type: {bulk_action_type}. Must be 'index' or 'upsert'.")

        return "\n".join(payload_lines) + "\n"

    def update(
            self,
            query_conditions: Dict[str, Any],
            update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Internal helper to perform an update_by_query operation based on multiple AND query conditions.

        Args:
            query_conditions: A dictionary where keys are field names and values are the exact
                              values to match (e.g., {"document_id": "doc123", "status": "pending"}).
                              All conditions are ANDed together.
            update_data: A dictionary of key-value pairs representing the fields to update
                         and their new values.

        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not query_conditions:
            raise ValueError("query_conditions cannot be empty. At least one condition is required to prevent accidental mass updates.")
        if not update_data:
            logger.warning("No update_data provided. No update will be performed.")
            return {"updated": 0, "failures": []}

        update_url = f"{self._zsearch_config.endpoint}/{self._index_name}/_update_by_query"
        update_url += "?wait_for_completion=true&refresh=true"

        must_clauses = []
        for field_name, field_value in query_conditions.items():
            if field_value is None:
                logger.warning(f"Skipping query condition for field '{field_name}' due to None value.")
                continue
            must_clauses.append({"term": {field_name: field_value}})

        if not must_clauses:
            raise ValueError("No valid query conditions were provided after processing `query_conditions` (e.g., all values were None).")

        payload = {
            "query": {
                "bool": {
                    "must": must_clauses
                }
            },
            "script": {
                "source": "for (entry in params.update_data.entrySet()) { ctx._source[entry.getKey()] = entry.getValue() }",
                "lang": "painless",
                "params": {
                    "update_data": update_data
                }
            }
        }

        logger.info(
            "Performing update_by_query on index %s, query_conditions=%s, payload=%s",
            self._index_name, query_conditions, json.dumps(payload, ensure_ascii=False)
        )

        try:
            response = self._client.post(update_url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("failures"):
                logger.error(f"Update by query failed for conditions {query_conditions}. Failures: {result['failures']}")
            else:
                logger.info(f"Successfully updated {result.get('updated', 0)} documents for conditions {query_conditions}.")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error performing update_by_query for conditions {query_conditions}: {e}",
                exc_info=True
            )
            raise

    def delete_by_query(self, query_conditions: Dict[str, Any]) -> Dict[
        str, Any]:
        """
        Internal helper to perform a _delete_by_query operation based on multiple AND query conditions.

        Args:
            query_conditions: A dictionary where keys are field names and values are the exact
                              values to match (e.g., {"document_id": "doc123", "status": "expired"}).
                              All conditions are ANDed together.

        Returns:
            The response from the Elasticsearch _delete_by_query API.
        """
        if not query_conditions:
            raise ValueError(
                "query_conditions cannot be empty. At least one condition is required to prevent accidental mass deletion.")

        delete_url = f"{self._zsearch_config.endpoint}/{self._index_name}/_delete_by_query"
        # Adding `wait_for_completion=true` makes the call synchronous.
        # Adding `refresh=true` makes changes visible immediately after the operation.
        delete_url += "?wait_for_completion=true&refresh=true"

        # Build the 'must' clause for the bool query
        must_clauses = []
        for field_name, field_value in query_conditions.items():
            if field_value is None:
                logger.warning(
                    f"Skipping query condition for field '{field_name}' due to None value in delete operation.")
                continue
            must_clauses.append({"term": {field_name: field_value}})

        if not must_clauses:
            raise ValueError(
                "No valid query conditions were provided after processing `query_conditions` (e.g., all values were None).")

        payload = {
            "query": {
                "bool": {
                    "must": must_clauses
                }
            }
        }

        logger.info(
            "Performing delete_by_query on index %s, query_conditions=%s, payload=%s",
            self._index_name, query_conditions, json.dumps(payload, ensure_ascii=False)
        )

        try:
            response = self._client.post(delete_url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("failures"):
                logger.error(
                    f"Delete by query failed for conditions {query_conditions}. Failures: {result['failures']}")
            else:
                logger.info(
                    f"Successfully deleted {result.get('deleted', 0)} documents for conditions {query_conditions}.")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error performing delete_by_query for conditions {query_conditions}: {e}",
                exc_info=True
            )
            # Re-raise or return a structured error response
            raise