import datetime
import json
import logging
import re
import uuid
from typing import List, Dict, Optional, Callable, Type, Any

from dateutil import parser
from pydantic import BaseModel

from derisk.component import SystemApp
from derisk.core import Chunk, Document
from derisk.jieba import jieba_util
from derisk.rag.embedding.embedding_factory import RerankEmbeddingFactory
from derisk.rag.retriever.rerank import RerankEmbeddingsRanker
from derisk.storage.metadata import BaseDao
from derisk.util import PaginationResult
from derisk_serve.core import BaseService
from derisk_serve.rag.service.service import Service as KnowledgeService
from ..api.schemas import AssetDocumentResponse, AssetKnowledgeSearchRequest, \
    AssetKnowledgeResponse, AssetToolResponse, AssetAgentResponse, \
    RecommendationFunctionScoreConfig, FunctionScoreFieldFactor, FunctionScoreGauss, \
    AssetKnowledgeCreateRequest, AssetDocumentRequest, AssetToolRequest, \
    AssetAgentRequest

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ...rag.api.schemas import SpaceServeResponse
from ...rag.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class Service(BaseService):
    """The service class for Asset"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
            self,
            system_app: SystemApp,
            config: ServeConfig,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        self._system_app = system_app

    @property
    def storage_manager(self):
        return (StorageManager.get_instance(self._system_app))

    @property
    def knowledge_service(self):
        return KnowledgeService.get_instance(self._system_app)

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    @property
    def dao(self) -> BaseDao:
        """Returns the internal DAO."""
        return None

    def asset_search(self, request: AssetKnowledgeSearchRequest, asset_type) -> List[
        Document]:
        """Get a list of Prompt entities by page
        Args:
            request (AssetKnowledgeSearchRequest): The request
        Returns:
            List[ServerResponse]: The response
        """
        rerank_embeddings = RerankEmbeddingFactory.get_instance(
            self.system_app
        ).create(model_name="derisk/bge-reranker-v2-m3")
        reranker = RerankEmbeddingsRanker(rerank_embeddings, topk=request.top_k)
        if asset_type == "knowledge":
            candidates = []
            knowledge_res: PaginationResult[
                AssetDocumentResponse] = self.knowledge_search(request)
            for item in knowledge_res.items:
                candidates.append(Chunk(
                    content="".join([item.document_name, item.document_content])
                ))
            reranker.rank(candidates, request.query)
        elif asset_type == "document":
            candidates = []
            knowledge_res: PaginationResult[
                AssetDocumentResponse] = self.document_search(request)
            for item in knowledge_res.items:
                candidates.append(Document(
                    content="".join([item.document_name, item.document_content]),
                    doc_name=item.document_name,
                    doc_link=item.document_link,
                    doc_type=item.document_type,
                ))
            rerank_candidates = reranker.rank(candidates, request.query)
            return rerank_candidates

    def document_search(self, request: AssetKnowledgeSearchRequest) -> PaginationResult[
        AssetDocumentResponse
    ]:
        """Get a list of Document entities by page."""

        multi_match_fields = {
            "knowledge_base_name": request.knowledge_weight,
            "document_name": request.document_weight,
            "knowledge_base_desc": request.knowledge_desc_weight,
            "document_desc": request.document_desc_weight,
            "document_content": request.document_content_weight,
            "tags.text": request.tag_weight,
        }

        # Specific highlight configurations for document search
        highlight_fields = {
            "document_name": {},
            "document_content": {"fragment_size": 200},
            "document_desc": {"fragment_size": 200}
        }

        def document_hit_processor(hit: Dict, document_instance: AssetDocumentResponse):
            text = hit.get("_source", {}).get("document_content", "")
            pattern = r'!\[.*?\]\((https?://[^\s)]+)\)'
            urls = re.findall(pattern, text)
            if urls:
                document_instance.document_img_url = urls[0]

        return self._perform_asset_search(
            request=request,
            asset_type_filter="knowledge",
            multi_match_field_weights=multi_match_fields,
            highlight_field_configs=highlight_fields,
            response_model=AssetDocumentResponse,
            hit_processing_callback=document_hit_processor,
        )

    def knowledge_search(self, request: AssetKnowledgeSearchRequest) -> \
    PaginationResult[AssetKnowledgeResponse]:
        """Get a list of Knowledge Base entities by page."""

        multi_match_fields = {
            "knowledge_base_name": request.knowledge_weight,
            "knowledge_base_desc": request.knowledge_desc_weight,
            "tags.text": request.tag_weight,
        }

        highlight_fields = {
            "knowledge_base_name": {},
            "document_name": {},
            "document_content": {
                "fragment_size": 200,
                "number_of_fragments": 3,
                "no_match_size": 0,
                "type": "unified",
                "require_field_match": True
            },
            "tags": {}
        }

        return self._perform_asset_search(
            request=request,
            asset_type_filter="knowledge",
            multi_match_field_weights=multi_match_fields,
            highlight_field_configs=highlight_fields,
            response_model=AssetKnowledgeResponse,
            sort_fields=[{"_score": "desc"}],  # Specific for knowledge search
            collapse_config={"field": "knowledge_base_id"}
            # Specific for knowledge search
        )

    def tool_search(self, request: AssetKnowledgeSearchRequest) -> PaginationResult[
        AssetToolResponse]:
        """
        Get a list of Tool entities by page.
        """
        multi_match_fields = {
            "tool_name": request.tool_name_weight,
            "tool_description": request.tool_desc_weight,
            "sub_tool_name": request.tool_name_weight,
            "tool_parameters.param_name": request.tool_param_name_weight,
            "tool_parameters.param_description": request.tool_param_desc_weight,
            "tags.text": request.tag_weight,
        }

        highlight_fields = {
            "tool_name": {},
            "tool_description": {"fragment_size": 200},
            "tool_parameters.param_name": {},
            "tool_parameters.param_description": {"fragment_size": 100},
        }

        additional_filters = []
        if request.tool_type:
            additional_filters.append({"term": {"tool_type": request.tool_type}})

        return self._perform_asset_search(
            request=request,
            asset_type_filter="tool",  # New asset_type
            multi_match_field_weights=multi_match_fields,
            highlight_field_configs=highlight_fields,
            response_model=AssetToolResponse,  # New response model
            additional_query_filters=additional_filters,
            sort_fields=[{"_score": "desc"}],
        )

    async def add_knowledge(self, request: AssetKnowledgeSearchRequest):
        """
        Load knowledge base.

        Args:
            request (AssetKnowledgeSearchRequest): The request
        """
        search_store = self.storage_manager.create_search_store(
            index_name=request.index_name
        )

    def delete_knowledge(self, request: AssetKnowledgeCreateRequest) -> Dict[
        str, Any]:
        """
        Updates content of documents identified by 'knowledge_id' field.
        Args:
             request: AssetToolRequest.
        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.knowledge_id:
            raise ValueError("knowledge_id cannot be empty for deletion.")
        search_store = self.storage_manager.create_search_store()
        return search_store.delete_by_query({"knowledge_id": request.knowledge_id})

    def delete_document(self, request: AssetDocumentRequest) -> Dict[
        str, Any]:
        """
        Updates content of documents identified by 'document_id' field.
        Args:
             request: AssetToolRequest.
        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.document_id:
            raise ValueError("document_id cannot be empty for deletion.")
        search_store = self.storage_manager.create_search_store()
        return search_store.delete_by_query({"document_id": request.document_id})

    def add_agent(self, request: AssetAgentRequest) -> AssetAgentResponse:
        """
        Add agent
        Args:
            request:

        Returns:
            AssetAgentResponse
        """
        asset_id  = str(f"asset-{uuid.uuid4()}")
        agent_base_dict = {
            "_id": asset_id,
            "asset_id": asset_id,
            "asset_type": "agent",
            "agent_id": request.agent_id,
            "agent_name": request.agent_name or "",
            "text_to_embed": f"{request.agent_name}{request.agent_description}",
            "tags": f"{request.tags}" or "",
            "creator": request.creator,
            "create_time": request.create_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": request.update_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        search_store = self.storage_manager.create_search_store()
        search_store.upsert(
            [agent_base_dict]
        )
        return AssetAgentResponse(**agent_base_dict)

    def update_agent(self, request: AssetAgentRequest) -> int:
        """
        Updates content of documents identified by 'tool_id' field.

        Args:
             request: AssetToolRequest.

        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.agent_id:
            raise ValueError("agent_id cannot be empty.")
        exist = self.check_agent_exists(request.agent_id)
        if not exist:
            raise ValueError("agent_id not exists.")
        search_store = self.storage_manager.create_search_store()
        update_data = {}
        if request.agent_name:
            update_data["agent_name"] = request.agent_name
        if request.agent_description:
            update_data["agent_description"] = request.agent_description
        if request.tags:
            update_data["tags"] = request.tags
        if request.creator:
            update_data["creator"] = request.creator
        if request.create_time:
            update_data["create_time"] = request.create_time
        if request.update_time:
            update_data["update_time"] = request.update_time
        query_conditions = {"agent_id": request.agent_id}
        result = search_store.update(
            query_conditions, update_data
        )
        return result.get("updated", 0)

    def delete_agent(self, request: AssetAgentRequest) -> Dict[
        str, Any]:
        """
        Delete content of documents identified by 'agent_id' field.
        Args:
             request: AssetAgentRequest.
        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.agent_id:
            raise ValueError("agent_id cannot be empty for deletion.")
        search_store = self.storage_manager.create_search_store()
        return search_store.delete_by_query({"agent_id": request.agent_id})

    def agent_search(self, request: AssetKnowledgeSearchRequest) -> PaginationResult[
        AssetAgentResponse]:
        """
        Get a list of Tool entities by page.
        """
        multi_match_fields = {
            "agent_name": request.agent_name_weight,
            "agent_description": request.agent_desc_weight,
        }

        highlight_fields = {
            "agent_name": {},
            "agent_description": {"fragment_size": 200},
        }

        additional_filters = []

        return self._perform_asset_search(
            request=request,
            asset_type_filter="agent",  # New asset_type
            multi_match_field_weights=multi_match_fields,
            highlight_field_configs=highlight_fields,
            response_model=AssetAgentResponse,
            additional_query_filters=additional_filters,
            sort_fields=[{"_score": "desc"}],
        )

    def _perform_asset_search(
            self,
            request: AssetKnowledgeSearchRequest,
            asset_type_filter: str,
            multi_match_field_weights: Dict[str, float],
            highlight_field_configs: Dict[str, Dict],
            response_model: Type[BaseModel],
            additional_query_filters: Optional[List[Dict]] = None,
            hit_processing_callback: Optional[Callable[[Dict, BaseModel], None]] = None,
            sort_fields: Optional[List[Dict]] = None,
            collapse_config: Optional[Dict] = None
    ) -> PaginationResult:
        """
        Generic method to perform asset searches.
        Args:
            request (AssetKnowledgeSearchRequest): The request
            asset_type_filter (str): The asset type filter
            multi_match_field_weights (Dict[str, float]): The multi_match field weights
            highlight_field_configs (Dict[str, Dict]): The highlight field configs
            response_model (Type[BaseModel]): The response model
            additional_query_filters (Optional[List[Dict]]): Additional query filters
            hit_processing_callback (Optional[Callable[[Dict, BaseModel], None]]): Hit processing callback
            sort_fields (Optional[List[Dict]]): Sort fields
            collapse_config (Optional[Dict]): Collapse config
        """
        search_store = self.storage_manager.create_search_store(
            index_name=request.index_name
        )
        query = jieba_util.preprocess_query(request.query)
        logger.info("Query: %s, raw query: %s", query, request.query)
        query_vector_data = search_store.embeddings.embed_query(query)

        # Build multi_match fields dynamically from weights
        multi_match_fields_list = [
            f"{field}^{weight}"
            for field, weight in multi_match_field_weights.items()
            if weight is not None  # Ensure weight exists
        ]

        query_dsl = {
            "bool": {
                "filter": [
                    {"term": {"asset_type": asset_type_filter}}
                ],
                "should": [
                    {
                        "knn": {
                            "field": "combined_vector",
                            "query_vector": query_vector_data,
                            "k": request.limit,
                            "num_candidates": request.vector_candidates,
                            "boost": request.vector_boost
                        }
                    },
                    {
                        "multi_match": {
                            "query": query,
                            "fields": multi_match_fields_list,
                            "operator": "or",
                            "fuzziness": "AUTO",
                            "boost": request.text_boost
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        }

        highlight_tag = json.loads(request.highlight_tag)
        pre_tag = highlight_tag.get('pre_tag', "<em>")
        post_tag = highlight_tag.get('post_tag', "</em>")

        final_highlight_config = {
            "fields": {}
        }
        for field, config in highlight_field_configs.items():
            field_config = config.copy()
            field_config["pre_tags"] = [pre_tag]
            field_config["post_tags"] = [post_tag]
            final_highlight_config["fields"][field] = field_config

        optional_filters_should = []
        if isinstance(request.tags, list) and len(request.tags) > 1:
            optional_filters_should.append({"terms": {"tags": request.tags}})
        elif request.tags:
            optional_filters_should.append({"term": {
                "tags": request.tags[0] if isinstance(request.tags,
                                                      list) else request.tags}})

        if request.knowledge_type:
            optional_filters_should.append(
                {"term": {"knowledge_type": request.knowledge_type}})
        if request.document_type:
            optional_filters_should.append(
                {"term": {"document_type": request.document_type}})
        if request.tool_type:
            optional_filters_should.append({"term": {"tool_type": request.tool_type}})

        if additional_query_filters:
            optional_filters_should.extend(additional_query_filters)

        if optional_filters_should:
            query_dsl["bool"]["filter"].append(
                {
                    "bool": {
                        "should": optional_filters_should,
                        "minimum_should_match": 1
                    }
                }
            )

        # Prepare search parameters
        search_params = {
            "query_criteria": query_dsl,
            "offset": request.offset,
            "limit": request.limit,
            "score_threshold": request.score_threshold,
            "exclude_fields": ["combined_vector"],
            "highlight_config": final_highlight_config
        }
        if sort_fields:
            search_params["sort_fields"] = sort_fields
        if collapse_config:
            search_params["collapse"] = collapse_config

        hits_results, total = search_store.search(**search_params)
        logger.info("Found %d total hits for query.", len(hits_results))

        parsed_results = []
        for hit in hits_results:
            source_data = hit["_source"].copy()
            source_data["highlight"] = hit.get("highlight", {})
            source_data["score"] = hit.get("_score", {})

            instance = response_model(**source_data)

            if hit_processing_callback:
                hit_processing_callback(hit, instance)

            parsed_results.append(instance)

        return PaginationResult(
            total_count=total,
            items=parsed_results,
            page_size=request.limit,
            page=request.page,
            total_pages=total
        )

    def knowledge_recommendation(self, request: AssetKnowledgeSearchRequest) -> \
            PaginationResult[AssetDocumentResponse]:
        """
        Recommends knowledge documents based on query and popularity/recency.
        """
        multi_match_fields = {
            "document_name": request.multi_match_weights.get("document_name", 3),
            "document_desc": request.multi_match_weights.get("document_desc", 1.5),
            "document_content": request.multi_match_weights.get("document_content", 1),
            "tags": request.multi_match_weights.get("tags", 2),
            "document_tags": request.multi_match_weights.get("document_tags", 2),
            "knowledge_base_name": request.multi_match_weights.get(
                "knowledge_base_name", 1),
            # Note: "knowledge_base_desc" from your original query is now covered by multi_match_weights if needed
        }

        match_phrase_fields = {
            "document_name": 4,
        }

        # Function score configuration for knowledge documents
        func_score_config = RecommendationFunctionScoreConfig(
            field_value_factors=[
                # FunctionScoreFieldFactor(field="read_count", modifier="log1p",
                #                          factor=1.5, missing=0),
                # FunctionScoreFieldFactor(field="like_count", modifier="log1p",
                #                          factor=2.0, missing=0),
            ],
            gauss_functions=[
                FunctionScoreGauss(field="document_update_at", origin="now",
                                   scale="30d", offset="7d", decay=0.5)
            ],
            score_mode="multiply",
            boost_mode="multiply"
        )

        highlight_fields = {
            "document_name": {},
            "document_content": {"fragment_size": 200},
            "document_desc": {"fragment_size": 200},
            "tags": {},  # For keyword fields, just {} is fine
            "document_tags": {},  # For keyword fields, just {} is fine
            "knowledge_base_name": {},
        }

        source_includes = [
            "document_name", "document_id", "document_content", "document_type",
            "document_desc",
            "document_link", "tags", "document_tags", "knowledge_base_name","knowledge_base_id",
            "creator", "read_count", "like_count", "document_update_at", "asset_id"
        ]

        def document_hit_processor(hit: Dict, document_instance: AssetDocumentResponse):
            text = hit.get("_source", {}).get("document_content", "")
            pattern = r'!\[.*?\]\((https?://[^\s)]+)\)'
            urls = re.findall(pattern, text)
            if urls:
                document_instance.document_img_url = urls[0]

        return self._perform_recommendation_search(
            request=request,
            asset_type="knowledge",
            multi_match_fields=multi_match_fields,
            match_phrase_fields=match_phrase_fields,
            function_score_config=func_score_config,
            response_model=AssetDocumentResponse,
            source_includes=source_includes,
            sort_fields=[{"_score": {"order": "desc"}},
                         {"document_update_at": {"order": "desc"}}],
            hit_processing_callback=document_hit_processor
        )

    def tool_recommendation(self, request: AssetKnowledgeSearchRequest) -> \
    PaginationResult[AssetToolResponse]:
        """
        Recommends tools based on query and popularity.
        """
        multi_match_fields = {
            "tool_name": request.multi_match_weights.get("tool_name", 3),
            "tool_description": request.multi_match_weights.get("tool_description",
                                                                1.5),
            "sub_tool_name": request.multi_match_weights.get("sub_tool_name", 2),
            "sub_tool_description": request.multi_match_weights.get(
                "sub_tool_description", 1),
            "tags": request.multi_match_weights.get("tags", 1.5),
        }

        match_phrase_fields = {
            "tool_name": 4,
            "tool_description": 2,
        }

        func_score_config = RecommendationFunctionScoreConfig(
            # field_value_factors=[
            #     FunctionScoreFieldFactor(field="read_count", modifier="log1p", factor=1.0, missing=0),
            #     FunctionScoreFieldFactor(field="like_count", modifier="log1p", factor=1.5, missing=0),
            # ],
            gauss_functions=[
                FunctionScoreGauss(field="update_time", origin="now", scale="90d",
                                   offset="15d", decay=0.5)
            ],
            score_mode="multiply",
            boost_mode="multiply"
        )

        highlight_fields = {
            "tool_name": {},
            "tool_description": {"fragment_size": 200},
            "sub_tool_name": {},
            "sub_tool_description": {"fragment_size": 200},
            "tool_parameters.param_name": {},
            # assuming tool_parameters is nested and has param_name
            "tool_parameters.param_description": {"fragment_size": 100},
        }

        source_includes = [
            "tool_id", "tool_name", "tool_description", "sub_tool_name",
            "sub_tool_description", "tool_type", "tool_parameters", "tags",
            "creator", "read_count", "like_count", "update_time", "asset_id",
            "asset_type"
        ]

        return self._perform_recommendation_search(
            request=request,
            asset_type="tool",
            multi_match_fields=multi_match_fields,
            match_phrase_fields=match_phrase_fields,
            function_score_config=func_score_config,
            highlight_fields=highlight_fields,
            response_model=AssetToolResponse,
            source_includes=source_includes,
            collapse_config={"field": "tool_id"},
            sort_fields=[{"_score": {"order": "desc"}}, {"update_time": {
                "order": "desc"}} if "update_time" in source_includes else None]
        )

    def agent_recommendation(self, request: AssetKnowledgeSearchRequest) -> \
    PaginationResult[AssetAgentResponse]:
        """
        Recommends tools based on query and popularity.
        """
        multi_match_fields = {
            "agent_name": request.multi_match_weights.get("agent_name", 3),
            "agent_description": request.multi_match_weights.get("agent_description",
                                                                 1.5),
            "tags": request.multi_match_weights.get("tags", 1.5),
        }

        match_phrase_fields = {
            "agent_name": 4,
            "agent_description": 2,
        }

        func_score_config = RecommendationFunctionScoreConfig(
            # field_value_factors=[
            #     FunctionScoreFieldFactor(field="read_count", modifier="log1p", factor=1.0, missing=0),
            #     FunctionScoreFieldFactor(field="like_count", modifier="log1p", factor=1.5, missing=0),
            # ],
            gauss_functions=[
                FunctionScoreGauss(field="update_time", origin="now", scale="90d",
                                   offset="15d", decay=0.5)
            ],
            score_mode="multiply",
            boost_mode="multiply"
        )

        # highlight_fields = {
        #     "tool_name": {},
        #     "tool_description": {"fragment_size": 200},
        #     "sub_tool_name": {},
        #     "sub_tool_description": {"fragment_size": 200},
        #     "tool_parameters.param_name": {}, # assuming tool_parameters is nested and has param_name
        #     "tool_parameters.param_description": {"fragment_size": 100},
        # }

        source_includes = [
            "agent_id", "agent_name", "agent_description", "tags",
            "creator", "update_time", "asset_id"
        ]

        return self._perform_recommendation_search(
            request=request,
            asset_type="agent",
            multi_match_fields=multi_match_fields,
            match_phrase_fields=match_phrase_fields,
            function_score_config=func_score_config,
            response_model=AssetAgentResponse,
            source_includes=source_includes,
            sort_fields=[{"_score": {"order": "desc"}}, {"update_time": {
                "order": "desc"}} if "update_time" in source_includes else None]
        )



    def update_document(self, request: AssetDocumentRequest) -> \
    Dict[str, Any]:
        """
        Updates content of documents identified by 'document_id' field.

        Args:
            request: AssetDocumentRequest.

        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.document_id:
            raise ValueError("document_id cannot be empty.")
        exist = self.check_document_exists(request.document_id)
        if not exist:
            raise ValueError("document_id not exists.")
        search_store = self.storage_manager.create_search_store()
        update_data = {}
        if request.document_content:
            update_data["document_content"] = request.document_content
        if request.document_desc:
            update_data["document_desc"] = request.document_desc
        if request.document_tags:
            update_data["document_tags"] = request.document_tags
        if request.document_type:
            update_data["document_type"] = request.document_type
        if request.document_link:
            update_data["document_link"] = request.document_link
        if request.creator:
            update_data["creator"] = request.creator
        if request.read_count:
            update_data["read_count"] = request.read_count
        if request.like_count:
            update_data["like_count"] = request.like_count
        if request.document_create_at:
            update_data["document_create_at"] = request.document_create_at
        if request.document_update_at:
            update_data["document_update_at"] = request.document_update_at
        return search_store.update(
            "document_id", request.document_id, update_data
        )

    def add_tool(self, request: AssetToolRequest) -> AssetToolResponse:
        tool_base_dict = {
            "_id": request.asset_id,
            "asset_id": request.asset_id,
            "asset_type": "tool",
            "tool_id": request.tool_id,
            "tool_name": request.tool_name,
            "tool_description": request.tool_description or "",
            "sub_tool_name": request.sub_tool_name or "",
            "sub_tool_description": request.sub_tool_description or "",
            "text_to_embed": f"{request.tool_name}{request.tool_description}",
            "tool_type": request.tool_type,
            "tool_parameters": request.tool_parameters,
            "creator": request.creator,
            "create_time": request.create_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": request.update_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if request.sub_tool_name:
            tool_base_dict["text_to_embed"] += request.sub_tool_name
        if request.sub_tool_description:
            tool_base_dict["text_to_embed"] += request.sub_tool_description

        search_store = self.storage_manager.create_search_store()
        search_store.upsert(
            [tool_base_dict]
        )
        return AssetToolResponse(**tool_base_dict)

    def update_tool(self, request: AssetToolRequest) -> int:
        """
        Updates content of documents identified by 'tool_id' field.

        Args:
             request: AssetToolRequest.

        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.tool_id:
            raise ValueError("tool_id cannot be empty.")
        exist = self.check_tool_exists(request.tool_id)
        if not exist:
            raise ValueError("tool_id not exists.")
        if request.tool_type.lower() == "mcp" and request.sub_tool_name:
            if not self.check_mcp_tool_exists(request.tool_id, request.sub_tool_name):
                logger.info(f"mcp tool {request.sub_tool_name} not exists, need to be added.")
                self.add_tool(request)
                return 1
        search_store = self.storage_manager.create_search_store()
        update_data = {}
        if request.tool_name:
            update_data["tool_name"] = request.tool_name
        if request.sub_tool_name:
            update_data["sub_tool_name"] = request.sub_tool_name
        if request.tool_description:
            update_data["tool_description"] = request.tool_description
        if request.sub_tool_description:
            update_data["sub_tool_description"] = request.sub_tool_description
        if request.tool_type:
            update_data["tool_type"] = request.tool_type
        if request.tool_parameters:
            update_data["tool_parameters"] = request.tool_parameters
        if request.creator:
            update_data["creator"] = request.creator
        if request.create_time:
            update_data["create_time"] = request.create_time
        if request.update_time:
            update_data["update_time"] = request.update_time
        query_conditions = {"tool_id": request.tool_id}
        if request.tool_type.lower() == "mcp" and request.sub_tool_name:
            query_conditions["sub_tool_name.keyword"] = request.sub_tool_name
        result = search_store.update(
            query_conditions, update_data
        )
        return result.get("updated", 0)

    def delete_tool(self, request: AssetToolRequest) -> Dict[
        str, Any]:
        """
        Updates content of documents identified by 'tool_id' field.
        Args:
             request: AssetToolRequest.
        Returns:
            The response from the Elasticsearch _update_by_query API.
        """
        if not request.tool_id:
            raise ValueError("tool_id cannot be empty for deletion.")
        search_store = self.storage_manager.create_search_store()
        return search_store.delete_by_query({"tool_id": request.tool_id})

    def _perform_recommendation_search(
            self,
            request: AssetKnowledgeSearchRequest,
            asset_type: str,  # "knowledge", "tool", "agent"
            multi_match_fields: Dict[str, float],
            match_phrase_fields: Dict[str, float],
            function_score_config: Optional[RecommendationFunctionScoreConfig],
            highlight_fields: Optional[Dict[str, Dict]] = None,
            response_model: Optional[Type[BaseModel]] = None,
            source_includes: Optional[List[str]] = None,
            source_excludes: Optional[List[str]] = None,
            sort_fields: Optional[List[Dict]] = None,
            collapse_config: Optional[Dict] = None,
            hit_processing_callback: Optional[Callable[[Dict, BaseModel], None]] = None
    ) -> PaginationResult[Any]:
        """
        Generic recommendation search method wrapping _execute_es_search.
        It sets up common parameters for a recommendation query.
        """
        # Ensure query is not empty for text-based matching
        if not request.query and not function_score_config:
            raise ValueError(
                "Query cannot be empty if no function_score is provided for recommendation.")

        # Update request with specific recommendation parameters for _execute_es_search
        # (This is more to mimic how parameters flow, real usage would pass them directly)
        request.multi_match_weights = multi_match_fields
        request.match_phrase_fields_boost = match_phrase_fields
        request.function_score_config = function_score_config
        request.source_includes = source_includes
        request.source_excludes = source_excludes

        return self._recommendation_search(
            request=request,
            asset_type_filter=asset_type,
            multi_match_weights=multi_match_fields,
            # These are already set in request, but passed explicitly
            highlight_field_configs=highlight_fields,
            response_model=response_model,
            sort_fields=sort_fields,
            hit_processing_callback=hit_processing_callback,
            # Pass through complex query config
            match_phrase_fields_boost=match_phrase_fields,
            function_score_config=function_score_config,
            source_includes=source_includes,
            source_excludes=source_excludes,
            collapse_config=collapse_config,
        )

    def _recommendation_search(
            self,
            request: AssetKnowledgeSearchRequest,
            asset_type_filter: str,
            multi_match_weights: Dict[str, float],
            highlight_field_configs: Dict[str, Dict],
            response_model: Type[BaseModel],
            additional_query_filters: Optional[List[Dict]] = None,
            hit_processing_callback: Optional[Callable[[Dict, BaseModel], None]] = None,
            sort_fields: Optional[List[Dict]] = None,
            collapse_config: Optional[Dict] = None,
            source_includes: Optional[List[str]] = None,
            source_excludes: Optional[List[str]] = None,
            match_phrase_fields_boost: Optional[Dict[str, float]] = None,
            function_score_config: Optional[RecommendationFunctionScoreConfig] = None
    ) -> PaginationResult[Any]:

        search_store = self.storage_manager.create_search_store(
            index_name=request.index_name
        )
        query_text = jieba_util.preprocess_query(request.query)
        logger.info("Processed Query: %s, Raw Query: %s", query_text, request.query)
        query_vector_data = search_store.embeddings.embed_query(query_text)

        # Build the core bool query
        core_bool_query = {
            "filter": [
                {"term": {"asset_type": asset_type_filter}}
            ],
            "should": [],
            "must": []
        }

        # IMPORTANT: KNN is NOT a part of the 'bool' query. It's a top-level search parameter in ES 8+.
        # We need to construct it separately and pass it to the search method.
        knn_param = {  # This is the top-level 'knn' parameter
            "field": "combined_vector",
            "query_vector": query_vector_data,
            "k": request.limit,  # Use request.limit for k in KNN
            "num_candidates": request.vector_candidates,
            # "boost": request.vector_boost # Boost for KNN is not standard in the knn query itself, might be handled via function_score or a nested query if you're not on ES 8.
        }

        # Build multi_match clause and add to must
        multi_match_fields_list = [f"{field}^{weight}" for field, weight in
                                   multi_match_weights.items() if
                                   weight is not None and field != ""]  # Filter out empty strings
        if multi_match_fields_list:
            core_bool_query["must"].append({
                "multi_match": {
                    "query": query_text,
                    "fields": multi_match_fields_list,
                    "operator": "and",
                    "fuzziness": "AUTO",
                    "boost": request.text_boost,
                    "analyzer": "ik_smart",
                    "type": "best_fields"  # ADD THIS BACK!
                }
            })

        # Add match_phrase clauses to should
        # if match_phrase_fields_boost:
        #     for field, boost in match_phrase_fields_boost.items():
        #         core_bool_query["should"].append({
        #             "match_phrase": {
        #                 field: {
        #                     "query": query_text,
        #                     "boost": boost
        #                 }
        #             }
        #         })

        # Only apply minimum_should_match if there's 'should' or 'must'
        if core_bool_query["should"] or core_bool_query["must"]:
            if "should" in core_bool_query and len(core_bool_query["should"]) > 0:
                core_bool_query["minimum_should_match"] = 1

        # Build function_score query
        main_query_dsl = {}
        if function_score_config:
            functions_list = []
            for fvf_config in function_score_config.field_value_factors:
                functions_list.append({
                    "field_value_factor": {
                        "field": fvf_config.field,
                        "modifier": fvf_config.modifier,
                        "factor": fvf_config.factor,
                        "missing": fvf_config.missing
                    }
                })
            for gauss_config in function_score_config.gauss_functions:
                gauss_dict = {
                    gauss_config.field: {
                        "origin": gauss_config.origin,
                        "scale": gauss_config.scale
                    }
                }
                if gauss_config.offset is not None:
                    gauss_dict[gauss_config.field]["offset"] = gauss_config.offset
                if gauss_config.decay is not None:
                    gauss_dict[gauss_config.field]["decay"] = gauss_config.decay
                functions_list.append({"gauss": gauss_dict})

            main_query_dsl = {
                "function_score": {
                    "query": {"bool": core_bool_query},
                    "functions": functions_list,
                    "score_mode": function_score_config.score_mode,
                    "boost_mode": function_score_config.boost_mode
                }
            }
        else:
            main_query_dsl = {"bool": core_bool_query}

        optional_filters_should = []
        if isinstance(request.tags, list) and len(request.tags) > 1:
            optional_filters_should.append({"terms": {"tags": request.tags}})
        elif request.tags:
            optional_filters_should.append({"term": {
                "tags": request.tags[0] if isinstance(request.tags,
                                                      list) else request.tags}})

        if request.knowledge_type:
            optional_filters_should.append(
                {"term": {"knowledge_type": request.knowledge_type}})
        if request.document_type:
            optional_filters_should.append(
                {"term": {"document_type": request.document_type}})
        if request.tool_type:
            optional_filters_should.append({"term": {"tool_type": request.tool_type}})
        if request.agent_type:
            optional_filters_should.append({"term": {"agent_type": request.agent_type}})

        if additional_query_filters:
            core_bool_query["filter"].extend(additional_query_filters)

        if optional_filters_should:
            core_bool_query["filter"].append(
                {
                    "bool": {
                        "should": optional_filters_should,
                        "minimum_should_match": 1
                    }
                }
            )

        final_highlight_config = None
        if highlight_field_configs:
            highlight_tag = json.loads(request.highlight_tag)
            pre_tag = highlight_tag.get('pre_tag', "<em>")
            post_tag = highlight_tag.get('post_tag', "</em>")

            final_highlight_config = {
                "fields": {}
            }
            for field, config in highlight_field_configs.items():
                field_config = config.copy()
                field_config["pre_tags"] = [pre_tag]
                field_config["post_tags"] = [post_tag]
                final_highlight_config["fields"][field] = field_config

        hits_results, total = search_store.search(
            query_criteria=main_query_dsl,
            limit=request.limit,
            offset=request.offset,
            score_threshold=request.score_threshold,
            source_fields=source_includes,
            exclude_fields=source_excludes,
            highlight_config=final_highlight_config,
            sort_fields=sort_fields,
            collapse=collapse_config,
        )
        logger.info("Found %d total hits for query.", len(hits_results))

        parsed_results = []
        for hit in hits_results:
            source_data = hit["_source"].copy()
            source_data["highlight"] = hit.get("highlight", {})
            source_data["score"] = hit.get("_score", {})

            instance = response_model(**source_data)

            if hit_processing_callback:
                hit_processing_callback(hit, instance)

            parsed_results.append(instance)

        return PaginationResult(
            total_count=total,
            items=parsed_results,
            page_size=request.limit,
            page=request.page,
            total_pages=total
        )

    def check_document_exists(self, document_id: str) -> bool:
        """
        Check document_id exists in Zsearch。

        Args:
            document_id: document_id
            index_name: index_name

        """
        search_store = self.storage_manager.create_search_store()
        if not document_id:
            logger.warning("Attempted to check existence for an empty document_id.")
            return False

        query_criteria = {"term": {"document_id": document_id}}

        try:
            hits, total_hits = search_store.search(
                query_criteria=query_criteria,
                limit=1,
                source_fields=[
                    "document_id",
                    "document_name",
                    "document_type",
                    "knowledge_base_id",
                    "knowledge_base_name",
                ],
                track_total_hits=False
            )
            return total_hits > 0
        except Exception as e:
            logger.error(
                f"Error checking existence for document_id '{document_id}': {e}")
            return False


    def check_tool_exists(self, tool_id: str) -> bool:
        """
        Check tool_id exists in Zsearch。

        Args:
            tool_id: tool_id

        """
        search_store = self.storage_manager.create_search_store()
        if not tool_id:
            logger.warning("Attempted to check existence for an empty tool_id.")
            return False

        query_criteria = {"term": {"tool_id": tool_id}}

        try:
            hits, total_hits = search_store.search(
                query_criteria=query_criteria,
                limit=1,
                source_fields=[
                    "tool_id",
                    "tool_name",
                    "tool_type",
                ],
            )
            return total_hits > 0
        except Exception as e:
            logger.error(
                f"Error checking existence for tool_id '{tool_id}': {e}")
            return False


    def check_agent_exists(self, agent_id: str) -> bool:
        """
        Check agent_id exists in search engine。

        Args:
            agent_id: tool_id

        """
        search_store = self.storage_manager.create_search_store()
        if not agent_id:
            logger.warning("Attempted to check existence for an empty agent_id.")
            return False

        query_criteria = {"term": {"agent_id": agent_id}}

        try:
            hits, total_hits = search_store.search(
                query_criteria=query_criteria,
                limit=1,
                source_fields=[
                    "agent_id",
                    "agent_name",
                    "agent_description",
                ],
            )
            return total_hits > 0
        except Exception as e:
            logger.error(
                f"Error checking existence for agent_id '{agent_id}': {e}")
            return False

    def check_mcp_tool_exists(self, tool_id: str, sub_tool_name: str) -> bool:
        """
        Check tool_id exists in Zsearch。

        Args:
            tool_id: tool_id
            sub_tool_name: mcp sub_tool_name

        """
        search_store = self.storage_manager.create_search_store()
        if not tool_id:
            logger.warning("Attempted to check existence for an empty tool_id.")
            return False

        query_criteria = {"term": {"sub_tool_name.keyword": sub_tool_name}}

        try:
            hits, total_hits = search_store.search(
                query_criteria=query_criteria,
                limit=1,
                source_fields=[
                    "tool_id",
                    "tool_name",
                    "tool_type",
                    "sub_tool_name",
                ],
            )
            return total_hits > 0
        except Exception as e:
            logger.error(
                f"Error checking existence for tool_id '{tool_id}': {e}")
            return False
