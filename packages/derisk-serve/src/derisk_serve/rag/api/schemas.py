from typing import List, Optional, Union, Any

from fastapi import File, UploadFile

from derisk._private.pydantic import BaseModel, ConfigDict, Field
from derisk.rag.retriever import RetrieverStrategy
from derisk.storage.vector_store.filters import MetadataFilters
from derisk_ext.rag.chunk_manager import ChunkParameters

from ..config import SERVE_APP_NAME_HUMP


class KnowledgeSettingContext(BaseModel):
    """Knowledge Setting Context"""

    embedding_model: Optional[int] = Field(None, description="embedding_model")
    rerank_model: Optional[str] = Field(None, description="rerank_model")
    retrieve_mode: Optional[str] = Field(None, description="The retrieve_mode")
    llm_model: Optional[str] = Field(None, description="llm_model")


class SpaceServeRequest(BaseModel):
    """name: knowledge space name"""

    """id: id"""
    id: Optional[int] = Field(None, description="The primary id")
    knowledge_id: Optional[str] = Field(None, description="The space id")
    sys_code: Optional[str] = Field(None, description="The sys_code")
    name: str = Field(None, description="The space name")
    """storage_type: vector type"""
    storage_type: Optional[str] = Field(None, description="The storage type")
    """vector_type: vector type"""
    vector_type: Optional[str] = Field(None, description="The vector type")
    """domain_type: domain type"""
    domain_type: str = Field(None, description="The domain type")
    """desc: description"""
    desc: Optional[str] = Field(None, description="The description")
    """owner: owner"""
    owner: Optional[str] = Field(None, description="The owner")
    """context: argument context"""
    context: Optional[str] = Field(None, description="The context")
    """gmt_created: created time"""
    gmt_created: Optional[str] = Field(None, description="The created time")
    """gmt_modified: modified time"""
    gmt_modified: Optional[str] = Field(None, description="The modified time")
    """category: category"""
    category: Optional[str] = Field(None, description="The category")
    """knowledge_type: knowledge type"""
    knowledge_type: Optional[str] = Field(None, description="The knowledge type")
    """name_or_tage: name or tag"""
    name_or_tag: Optional[str] = Field(None, description="The name or tag")
    """tags: tags"""
    tags: Optional[str] = Field(None, description="The tags")


class SpaceServeResponse(BaseModel):
    """name: knowledge space name"""

    """id: id"""
    id: Optional[int] = Field(None, description="The primary id")
    knowledge_id: Optional[str] = Field(None, description="The space id")
    sys_code: Optional[str] = Field(None, description="The sys_code")
    name: str = Field(None, description="The space name")
    """storage_type: vector type"""
    storage_type: str = Field(None, description="The vector type")
    """domain_type: domain type"""
    domain_type: str = Field(None, description="The domain type")
    """desc: description"""
    desc: Optional[str] = Field(None, description="The description")
    """owner: owner"""
    owner: Optional[str] = Field(None, description="The owner")
    """context: argument context"""
    context: Optional[str] = Field(None, description="The context")
    """gmt_created: created time"""
    gmt_created: Optional[str] = Field(None, description="The created time")
    """gmt_modified: modified time"""
    gmt_modified: Optional[str] = Field(None, description="The modified time")


class DocumentServeRequest(BaseModel):
    id: Optional[int] = Field(None, description="The doc id")
    doc_id: Optional[str] = Field(None, description="id")
    sys_code: Optional[str] = Field(None, description="The sys_code")
    doc_name: Optional[str] = Field(None, description="doc name")
    """doc_type: document type"""
    doc_type: Optional[str] = Field(None, description="The doc type")
    """doc_type: document type"""
    tags: Optional[List[str]] = Field(None, description="The doc tags")
    knowledge_id: Optional[str] = Field(None, description="The knowledge space id")
    """content: description"""
    content: Optional[str] = Field(None, description="content")
    """doc file"""
    doc_file: Union[UploadFile, str] = File(None)
    """space name: space name"""
    space_name: Optional[str] = Field(None, description="space name")
    """space name: space name"""
    meta_data: Optional[dict] = Field(None, description="meta data")
    """questions: questions"""
    questions: Optional[List[str]] = Field(None, description="questions")


class DocumentServeResponse(BaseModel):
    id: Optional[int] = Field(None, description="The doc id")
    doc_id: Optional[str] = Field(None, description="document id")
    doc_name: Optional[str] = Field(None, description="doc type")
    """storage_type: storage type"""
    doc_type: Optional[str] = Field(None, description="The doc content")
    """desc: description"""
    content: Optional[str] = Field(None, description="content")
    """vector ids"""
    vector_ids: Optional[str] = Field(None, description="vector ids")
    """space: space name"""
    space: Optional[str] = Field(None, description="space name")
    knowledge_id: Optional[str] = Field(None, description="The space id")
    """status: status"""
    status: Optional[str] = Field(None, description="status")
    """result: result"""
    result: Optional[str] = Field(None, description="result")
    """result: result"""
    tags: Optional[List[str]] = Field(None, description="The doc tags")
    """summary: summary"""
    summary: Optional[str] = Field(None, description="summary")
    """gmt_created: created time"""
    gmt_created: Optional[str] = Field(None, description="created time")
    """gmt_modified: modified time"""
    gmt_modified: Optional[str] = Field(None, description="modified time")
    """chunk_size: chunk size"""
    chunk_size: Optional[int] = Field(None, description="chunk size")
    """questions: questions"""
    questions: Optional[str] = Field(None, description="questions")
    meta_data: Optional[dict] = Field(None, description="meta_data")


class ChunkServeRequest(BaseModel):
    id: Optional[int] = Field(None, description="The primary id")
    chunk_id: Optional[str] = Field(None, description="The chunk id")
    document_id: Optional[str] = Field(None, description="document id")
    knowledge_id: Optional[str] = Field(None, description="The space id")
    doc_name: Optional[str] = Field(None, description="document name")
    doc_type: Optional[str] = Field(None, description="document type")
    content: Optional[str] = Field(None, description="chunk content")
    meta_data: Optional[str] = Field(None, description="chunk meta info")
    questions: Optional[List[str]] = Field(None, description="chunk questions")
    chunk_id: Optional[str] = Field(None, description="chunk id")
    gmt_created: Optional[str] = Field(None, description="chunk create time")
    gmt_modified: Optional[str] = Field(None, description="chunk modify time")


class ChunkServeResponse(BaseModel):
    id: Optional[int] = Field(None, description="The primary id")
    chunk_id: Optional[str] = Field(None, description="The chunk id")
    document_id: Optional[str] = Field(None, description="document id")
    doc_id: Optional[str] = Field(None, description="doc id")
    vector_id: Optional[str] = Field(None, description="vector id")
    full_text_id: Optional[str] = Field(None, description="full_text id")
    doc_name: Optional[str] = Field(None, description="document name")
    doc_type: Optional[str] = Field(None, description="document type")
    content: Optional[str] = Field(None, description="chunk content")
    meta_data: Optional[str] = Field(None, description="chunk meta info")
    questions: Optional[str] = Field(None, description="chunk questions")
    chunk_id: Optional[str] = Field(None, description="chunk id")
    tags: Optional[str] = Field(None, description="The doc tags")
    gmt_created: Optional[str] = Field(None, description="chunk create time")
    gmt_modified: Optional[str] = Field(None, description="chunk modify time")


class KnowledgeSyncRequest(BaseModel):
    """Sync request"""

    """doc_ids: doc ids"""
    doc_id: Optional[Union[str, int]] = Field(None, description="The doc id")

    """knowledge space id"""
    knowledge_id: Optional[str] = Field(None, description="knowledge space id")

    """model_name: model name"""
    model_name: Optional[str] = Field(None, description="model name")

    """chunk_parameters: chunk parameters 
    """
    chunk_parameters: Optional[ChunkParameters] = Field(
        None, description="chunk parameters"
    )



class KnowledgeRetrieveRequest(BaseModel):
    """Retrieve request"""

    """knowledge id"""
    knowledge_id: str = Field(None, description="knowledge id")

    """query: query"""
    query: str = Field(None, description="query")

    """top_k: top k"""
    top_k: Optional[int] = Field(5, description="top k")

    """score_threshold: score threshold
    """
    score_threshold: Optional[float] = Field(0.0, description="score threshold")


class ChunkEditRequest(BaseModel):
    """id: id"""

    """chunk_id: chunk_id"""
    chunk_id: Optional[int] = None
    """chunk content: content"""
    content: Optional[str] = None
    """label: label"""
    label: Optional[str] = None
    """questions: questions"""
    questions: Optional[List[str]] = None
    """meta_info: meta_info or meta_data"""
    meta_info: Optional[str] = None

    """knowledge_id : knowledge_id"""
    knowledge_id: Optional[str] = None
    """doc_id: doc_id"""
    doc_id: Optional[str] = None
    """tags: tags"""
    tags: Optional[List[str]] = None

    """first_level_header: first_level_header"""
    first_level_header: Optional[str] = None

class KnowledgeSearchRequest(BaseModel):
    """Knowledge Search Request"""

    query: Optional[str] = None
    knowledge_ids: Optional[List[str]] = None
    top_k: Optional[int] = 5
    score_threshold: Optional[float] = 0.5
    similarity_score_threshold: Optional[float] = 0.0
    single_knowledge_top_k: Optional[int] = 10
    enable_rerank: Optional[bool] = True
    enable_summary: Optional[bool] = True
    enable_tag_filter: Optional[bool] = True
    summary_model: Optional[str] = "aistudio/DeepSeek-V3"
    rerank_model: Optional[str] = "bge-reranker-v2-m3"
    summary_prompt: Optional[
        str
    ] = """你是一个「总结专家」，请根据query对检索到的文档进行总结，要求总结的内容和query是相关的。 请注意有可能检索到的文档含有表格，请谨慎处理。回答的时候最好按照1.2.3.点进行总结。"
    "注意："
    "1.尽可能的不要漏要点信息，不要加上你的评论和建议."
    "2.尽可能地保留知识的要点信息，不要遗漏.\n"
    "检索到的知识: {text}"""
    summary_tokens: Optional[int] = 1000

    """search mode: semantic or hybrid"""
    mode: Optional[str] = RetrieverStrategy.SEMANTIC.value
    response_filters: Optional[List[str]] = None
    metadata_filters: Optional[MetadataFilters] = None
    enable_split_query: Optional[bool] = True
    split_query_model: Optional[str] = None
    split_query_prompt: Optional[str] = None
    enable_rewrite_query: Optional[bool] = False
    rewrite_query_model: Optional[str] = None
    rewrite_query_prompt: Optional[str] = None
    search_with_historical: Optional[bool] = False
    tag_filters: Optional[List[dict]] = None
    summary_with_historical: Optional[bool] = False


class SpaceServeResponse(BaseModel):
    """Flow response model"""

    model_config = ConfigDict(title=f"ServeResponse for {SERVE_APP_NAME_HUMP}")

    """storage_type: storage type"""
    id: Optional[int] = Field(None, description="The space id")
    knowledge_id: Optional[str] = Field(None, description="The knowledge id")
    name: Optional[str] = Field(None, description="The space name")
    """storage_type: storage type"""
    storage_type: Optional[str] = Field(None, description="The vector type")
    """desc: description"""
    desc: Optional[str] = Field(None, description="The description")
    """context: argument context"""
    context: Optional[str] = Field(None, description="The context")
    """owner: owner"""
    owner: Optional[str] = Field(None, description="The owner")
    """user_id: user_id"""
    user_id: Optional[str] = Field(None, description="user id")
    """user_id: user_ids"""
    user_ids: Optional[str] = Field(None, description="user ids")
    """sys code"""
    sys_code: Optional[str] = Field(None, description="The sys code")
    """domain type"""
    domain_type: Optional[str] = Field(None, description="domain_type")
    """category: category"""
    category: Optional[str] = Field(None, description="The category")
    """knowledge_type: knowledge type"""
    knowledge_type: Optional[str] = Field(None, description="knowledge type")
    """tags: tags"""
    tags: Optional[str] = Field(None, description="The tags")


class DocumentChunkVO(BaseModel):
    id: int = Field(..., description="document chunk id")
    document_id: int = Field(..., description="document id")
    knowledge_id: str = Field(..., description="knowledge id")
    doc_name: str = Field(..., description="document name")
    doc_type: str = Field(..., description="document type")
    content: str = Field(..., description="document content")
    meta_data: str = Field(..., description="document meta info")
    gmt_created: str = Field(..., description="document create time")
    gmt_modified: str = Field(..., description="document modify time")


class DocumentVO(BaseModel):
    """Document Entity."""

    id: int = Field(..., description="document id")
    doc_name: str = Field(..., description="document name")
    doc_type: str = Field(..., description="document type")
    space: str = Field(..., description="document space name")
    chunk_size: int = Field(..., description="document chunk size")
    status: str = Field(..., description="document status")
    content: str = Field(..., description="document content")
    result: Optional[str] = Field(None, description="document result")
    vector_ids: Optional[str] = Field(None, description="document vector ids")
    summary: Optional[str] = Field(None, description="document summary")
    gmt_created: str = Field(..., description="document create time")
    gmt_modified: str = Field(..., description="document modify time")


class KnowledgeDomainType(BaseModel):
    """Knowledge domain type"""

    name: str = Field(..., description="The domain type name")
    desc: str = Field(..., description="The domain type description")


class KnowledgeStorageType(BaseModel):
    """Knowledge storage type"""

    name: str = Field(..., description="The storage type name")
    desc: str = Field(..., description="The storage type description")
    domain_types: List[KnowledgeDomainType] = Field(..., description="The domain types")


class KnowledgeConfigResponse(BaseModel):
    """Knowledge config response"""

    storage: List[KnowledgeStorageType] = Field(..., description="The storage types")


class KnowledgeDocumentRequest(BaseModel):
    """doc_name: doc path"""

    doc_name: Optional[str] = None
    """doc_id: doc id"""
    doc_id: Optional[str] = None
    """doc_type: doc type"""
    doc_type: Optional[str] = None
    """doc_token: doc token"""
    doc_token: Optional[str] = None
    """content: content"""
    content: Optional[str] = None
    """content: content"""
    source: Optional[str] = None

    """ space id"""
    knowledge_id: Optional[str] = None

    """ oss_file_key """
    oss_file_key: Optional[str] = None

    labels: Optional[str] = None

    questions: Optional[List[str]] = None

    chunk_parameters: Optional[ChunkParameters] = None

    chunk_id: Optional[int] = None


    """ doc ids retry"""
    doc_ids: Optional[List[str]] = None

class OutlineChunk(BaseModel):
    """ outlines"""
    first_level_header: Optional[str] = None
    chunks: Optional[List[str]] = None





class DocumentSearchResponse(BaseModel):
    content: Optional[str] = None
    score: Optional[float] = None
    knowledge_id: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    create_time: Optional[str] = None
    modified_time: Optional[str] = None
    doc_type: Optional[str] = None
    doc_name: Optional[str] = None


class KnowledgeSearchResponse(BaseModel):
    summary_content: Optional[str] = None
    document_response_list: Optional[List[DocumentSearchResponse]] = None
    sub_queries: Optional[dict] = None
    references: Optional[dict] = None
    raw_query: Optional[str] = None


class ParamDetail(BaseModel):
    param_name: Optional[str] = None
    param_type: Optional[str] = None
    default_value: Optional[Any] = None
    description: Optional[str] = None


class StrategyDetail(BaseModel):
    strategy: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[List[ParamDetail]] = None
    suffix: Optional[List[str]] = None
    type: Optional[List[str]] = None


class KnowledgeTaskRequest(BaseModel):
    task_id: Optional[str] = None
    status: Optional[str] = None
    operator: Optional[str] = None
    knowledge_id: Optional[str] = None
    batch_id: Optional[str] = None


class KnowledgeTaskResponse(BaseModel):
    knowledge_id: Optional[str] = None
    total_tasks_count: Optional[int] = None
    succeed_tasks_count: Optional[int] = None
    running_tasks_count: Optional[int] = None
    todo_tasks_count: Optional[int] = None
    last_task_operator: Optional[str] = None

