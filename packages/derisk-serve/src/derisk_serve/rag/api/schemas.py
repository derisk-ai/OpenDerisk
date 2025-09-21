import dataclasses
from enum import Enum
from typing import List, Optional, Union, Any

from fastapi import File, UploadFile

from derisk._private.pydantic import BaseModel, ConfigDict, Field
from derisk.rag.knowledge.base import DirectoryModeType
from derisk.rag.retriever import RetrieverStrategy
from derisk.rag.transformer.tag_extractor import MetadataTag
from derisk.storage.vector_store.filters import MetadataFilters
from derisk.util.i18n_utils import _
from derisk_ext.rag.chunk_manager import ChunkParameters
from derisk_ext.rag.transformer.image_extractor import IMAGE_EXTRACT_SYSTEM_PROMPT

from ..config import SERVE_APP_NAME_HUMP

class KnowledgeSettingContext(BaseModel):
    """Knowledge Setting Context"""

    embedding_model: Optional[int] = Field(None, description="embedding_model")
    rerank_model: Optional[str] = Field(None, description="rerank_model")
    retrieve_mode: Optional[str] = Field(None, description="The retrieve_mode")
    llm_model: Optional[str] = Field(None, description="llm_model")


class CreateYuqueRequest(BaseModel):
    enable_create_yuque: Optional[bool] = Field(False, description="The enable_create_yuque")
    yuque_book_slug: Optional[str] = Field(None, description="The yuque_book_slug")
    yuque_group_login: Optional[str] = Field(None, description="The dest_group_token")
    yuque_token: Optional[str] = Field(None, description="The yuque_token")

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
    """refresh: refresh"""
    refresh: Optional[str] = Field(None, description="The refresh")

    """create_yuque: create yuque"""
    create_yuque: Optional[CreateYuqueRequest] = Field(None, description="The create_yuque")

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
    doc_token: Optional[str] = Field(None, description="doc token")



class ChunkServeRequest(BaseModel):
    id: Optional[int] = Field(None, description="The primary id")
    chunk_id: Optional[str] = Field(None, description="The chunk id")
    document_id: Optional[str] = Field(None, description="document id")
    doc_id: Optional[str] = Field(None, description="doc id")
    knowledge_id: Optional[str] = Field(None, description="The space id")
    doc_name: Optional[str] = Field(None, description="document name")
    doc_type: Optional[str] = Field(None, description="document type")
    content: Optional[str] = Field(None, description="chunk content")
    meta_data: Optional[str] = Field(None, description="chunk meta info")
    questions: Optional[List[str]] = Field(None, description="chunk questions")
    chunk_id: Optional[str] = Field(None, description="chunk id")
    tags: Optional[List[str]] = Field(None, description="The doc tags")
    chunk_type: Optional[str] = Field("text", description="chunk type")
    image_url: Optional[str] = Field(None, description="image_url")
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
    tags: Optional[List[str]] = Field(None, description="The doc tags")
    chunk_type: Optional[str] = Field("text", description="chunk type")
    image_url: Optional[str] = Field(None, description="image_url")
    knowledge_id: Optional[str] = Field(None, description="knowledge id")
    yuque_url: Optional[str] = Field(None, description="yuque url")
    gmt_created: Optional[str] = Field(None, description="chunk create time")
    gmt_modified: Optional[str] = Field(None, description="chunk modify time")


class KnowledgeSyncRequest(BaseModel):
    """Knowledge Sync request.

    Args:
        doc_id: The document id to sync.
        knowledge_id: The knowledge space id.
        model_name: The model name to use for syncing.
        chunk_parameters: The parameters for chunking the document.
        yuque_doc_uuid: The UUID of the Yuque document.
        extract_image: Whether to extract images from the document.
    """

    doc_id: Optional[Union[str, int]] = Field(None, description="The doc id")

    knowledge_id: Optional[str] = Field(None, description="knowledge space id")

    model_name: Optional[str] = Field(None, description="model name")

    chunk_parameters: Optional[ChunkParameters] = Field(
        None, description="chunk parameters"
    )

    yuque_doc_uuid: Optional[str] = Field(None, description="doc uuid")

    extract_image: bool = Field(
        False, description="Whether to extract images from the document"
    )
    tags: Optional[List[dict]] = Field(None, description="The doc tags")


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
    tags: Optional[List[dict]] = None

    """first_level_header: first_level_header"""
    first_level_header: Optional[str] = None

class KnowledgeSearchDirectoryRequest(BaseModel):
    """knowledge directory request"""

    knowledge_ids: Optional[List[str]] = None
    query: Optional[str] = None
    retrieve_directory: Optional[bool] = False
    """directory mode: document or book"""
    directory_mode: Optional[str] = DirectoryModeType.DOCUMENT.value
    doc_uuids: Optional[List[str]] = None


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
    summary_model: Optional[str] = "deepseek-v3"
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
    tag_filters: Optional[List[MetadataTag]] = None
    summary_with_historical: Optional[bool] = False
    doc_uuids: Optional[List[str]] = None


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
    "refresh: refresh"
    refresh: Optional[str] = Field(None, description="The refresh")
    gmt_create: Optional[str] = Field(None, description="The gmt create")
    gmt_modified: Optional[str] = Field(None, description="The gmt modified")


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
    """doc_file: doc token"""
    doc_file: Optional[UploadFile] = None
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

    """yuque sync info"""
    yuque_group_login: Optional[str] = None
    yuque_book_slug: Optional[str] = None
    yuque_doc_slug: Optional[str] = None
    yuque_doc_uuid: Optional[str] = None

    """ doc ids retry"""
    doc_ids: Optional[List[str]] = None
    extract_image: bool = False
    tags: Optional[List[dict]] = None

    file_params: Optional[str] = None


class YuqueRequest(BaseModel):
    """yuque request"""

    """ knowledge id"""
    knowledge_id: Optional[str] = None
    """doc id"""
    doc_id: Optional[str] = None
    """yuque url"""
    yuque_url: Optional[str] = None
    """ yuque token"""
    yuque_token: Optional[str] = None
    """group_login: group login"""
    group_login: Optional[str] = None
    """ book_slug: book slug"""
    book_slug: Optional[str] = None
    """yuque_doc_id: yuque doc id/yuque doc slug"""
    yuque_doc_id: Optional[str] = None
    """yuque_doc_uuid: yuque doc uuid"""
    yuque_doc_uuid: Optional[str] = None
    """yuque_name: yuque name"""
    yuque_name: Optional[str] = None
    """chunk_parameters: chunk parameters"""
    chunk_parameters: Optional[ChunkParameters] = None
    """owner: owner"""
    owner: Optional[str] = None
    """owner: owner"""
    extract_image: Optional[bool] = False
    """tags: tags (meta_data)"""
    tags: Optional[List[dict]] = None



class YuqueDocDetail(BaseModel):
    """yuque doc details"""

    child_doc_slug: Optional[str] = None
    doc_slug: Optional[str] = None
    """file_id: file id/ doc id"""
    file_id: Optional[str] = None
    file_status: Optional[str] = None
    invalid_reason: Optional[str] = None
    parent_doc_slug: Optional[str] = None
    prev_doc_slug: Optional[str] = None
    nextDocSlug: Optional[str] = None
    selected: Optional[bool] = None
    sibling_doc_slug: Optional[str] = None
    sync_status: Optional[str] = None
    sync_time_ms: Optional[int] = None
    title: Optional[str] = None
    type: Optional[str] = None
    progress: Optional[str] = None


class OutlineChunk(BaseModel):
    """yuque outlines"""

    first_level_header: Optional[str] = None
    chunks: Optional[List[str]] = None


class YuqueOutlines(BaseModel):
    """yuque outlines"""

    is_header_split: Optional[bool] = False
    outline_chunks: Optional[List[OutlineChunk]] = None


class YuqueBookDetail(BaseModel):
    """yuque book details"""

    book_slug: Optional[str] = None
    name: Optional[str] = None
    docs: Optional[List[YuqueDocDetail]] = None


class YuqueGroupBook(BaseModel):
    book_slug: Optional[str] = None
    book_name: Optional[str] = None
    group_login: Optional[str] = None
    group_name: Optional[str] = None
    knowledge_id: Optional[str] = None
    type: Optional[str] = None


class TextBook(BaseModel):
    doc_name: Optional[str] = None
    doc_id: Optional[str] = None
    children: Optional[List] = None
    content: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[str] = None

class YuqueDirDetail(BaseModel):
    qas: Optional[List] = None
    group_books: Optional[List[YuqueGroupBook]] = None
    texts: Optional[List[TextBook]] = None
    files: Optional[List[TextBook]] = None


class DocumentSearchResponse(BaseModel):
    content: Optional[str] = None
    score: Optional[float] = None
    knowledge_id: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    create_time: Optional[str] = None
    modified_time: Optional[str] = None
    doc_type: Optional[str] = None
    yuque_url: Optional[str] = None
    doc_name: Optional[str] = None
    metadata: Optional[dict] = None


class KnowledgeSearchResponse(BaseModel):
    summary_content: Optional[str] = None
    document_response_list: Optional[List[DocumentSearchResponse]] = None
    sub_queries: Optional[dict] = None
    references: Optional[dict] = None
    raw_query: Optional[str] = None
    directory: Optional[dict] = None
    book_directory: Optional[str] = None
    document_contents: Optional[List[str]] = None
    doc_uuids: Optional[List[str]] = None
    doc_titles: Optional[List[str]] = None
    group_login_name: Optional[str] = None


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
    failed_tasks_count: Optional[int] = None
    todo_tasks_count: Optional[int] = None
    last_task_operator: Optional[str] = None


class SettingsRequest(BaseModel):
    setting_key: Optional[str] = None
    value: Optional[str] = None
    operator: Optional[str] = None
    description: Optional[str] = None


class CreateDocRequest(BaseModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    """公开性: (0:私密, 1:公开, 2:企业内公开)"""
    public: Optional[int] = 0
    format: Optional[str] = "lake"
    """使用body_lake语雀内容"""
    body: Optional[str] = None
    token: Optional[str] = None

    group_login: Optional[str] = None
    book_slug: Optional[str] = None
    file_path: Optional[str] = None
    tags: Optional[List[dict]] = None
    target_uuid: Optional[str] = None
    content: Optional[str] = None

class UpdateTocRequest(BaseModel):
    token: Optional[str] = None
    """操作:(appendNode:尾插, prependNode:头插, editNode:编辑节点,removeNode:删除节点)"""
    action: Optional[str] = None
    """操作模式: (sibling:同级, child:子级)"""
    action_mode: Optional[str] = None
    """目标节点 UUID, 不填默认为根节点; 获取方式: 调用"获取知识库目录"接口获取"""
    target_uuid: Optional[str] = None
    """删除目录/编辑目录时需要传入"""
    node_uuid: Optional[str] = None
    doc_ids: Optional[List[int]] = None
    type: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    """  是否在新窗口打开: (0:当前页打开, 1:新窗口打开)"""
    open_window: Optional[int] = 0
    """ 是否可见: (0:不可见, 1:可见)"""
    visible: Optional[int] = 1

class CreateBookRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    """公开性: (0:私密, 1:公开, 2:企业内公开)"""
    public: Optional[str] = "0"
    """ 增强私密性: 将除团队管理员之外的团队成员、团队只读成员也设置为无权限"""
    enhancedPrivacy: Optional[bool] = True

    """要写入的目标知识库group_login"""
    dest_group_login: Optional[str] = None
    dest_group_token: Optional[str] = None
    async_run: Optional[bool] = False
    category: Optional[str] = None


class QueryGraphProjectRequest(BaseModel):
    """user login name 用户登陆名"""
    user_login_name: Optional[str] = None
    """user token 用户访问token"""
    user_token: Optional[str] = None

class GraphProject(BaseModel):
    project_name: Optional[str] = None
    graph: Optional[str] = None
    project_id: Optional[str] = None
    name_zh: Optional[str] = None


class CreateGraphRelationRequest(BaseModel):
    knowledge_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    user_login_name: Optional[str] = None
    user_token: Optional[str] = None
    is_init: Optional[bool] = False

class NodeDetail(BaseModel):
    node_id: Optional[str] = None
    name: Optional[str] = None
    name_zh: Optional[str] = None
    desc: Optional[str] = None
    desc_zh: Optional[str] = None
    vector_id: Optional[str] = None
    vertex_type: Optional[str] = None

class EdgeDetail(BaseModel):
    edge_id: Optional[str] = None
    name: Optional[str] = None
    name_zh: Optional[str] = None
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    edge_type: Optional[str] = None

class GraphDetail(BaseModel):
    nodes: Optional[List[NodeDetail]] = None
    edges: Optional[List[EdgeDetail]] = None


class RefreshInfo(BaseModel):
    group_login: Optional[str] = None
    book_slug: Optional[str] = None
    delete_doc_len: Optional[int] = None
    add_doc_len: Optional[int] = None
    update_doc_len: Optional[int] = None
    delete_doc_ids: Optional[List[str]] = []
    add_doc_slugs: Optional[List[str]] = []
    update_doc_ids: Optional[List[str]] = []


class RefreshContext(BaseModel):
    refresh_mode: Optional[str] = None
    refresh_mode_desc: Optional[str] = None
    refresh_scope: Optional[str] = None
    refresh_infos: Optional[List[RefreshInfo]] = []

    def to_dict(self):
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict):
        refresh_info_data = data.get("refresh_infos")
        if refresh_info_data is not None:
            data["refresh_infos"] = [RefreshInfo(**item) for item in refresh_info_data]
        return cls(**data)

class RefreshScopeType(Enum):
    SPACE = "知识空间同步"
    GROUP = "语雀团队同步"
    BOOK = "语雀知识库同步"


class RefreshModeType(Enum):
    REFRESH_EXISTING_ONLY = "仅同步已导入的文档"
    REFRESH_FULL_MIRROR = "完全镜像同步"


class RefreshTimeType(Enum):
    T_PLUS_1 = "T+1同步"
    HOURLY_12 = "每12小时同步"
    HOURLY_6 = "每6小时同步"
    HOURLY_1 = "每1小时同步"
    MINUTELY_30 = "每30分钟同步"
    MINUTELY_10 = "每10分钟同步"



@dataclasses.dataclass
class KnowledgeSetting:
    enable_refresh: bool = dataclasses.field(
        default=False, metadata={"help": _("是否同步"),
                                "label": _("是否同步")}
    )
    enable_scheduled_refresh: bool = dataclasses.field(
        default=False, metadata={"help": _("是否定时同步"),
                                  "label": _("是否定时同步")}
    )
    scheduled_refresh_time: str = dataclasses.field(
        default=RefreshTimeType.T_PLUS_1.value, metadata={"help": _("定时同步时间"),
                                  "label": _("定时同步时间"),
                                  "options": [
                                      {"name": m.name, "value": m.value}
                                      for m in RefreshTimeType
                                  ]}
    )
    refresh_mode: str = dataclasses.field(
        default=RefreshModeType.REFRESH_EXISTING_ONLY.name, metadata={"help": _("同步模式"),
                                  "label": _("同步模式"),
                                  "options": [
                                      {"name": m.name, "value": m.value}
                                      for m in RefreshModeType
                                  ]}
    )
    refresh_scope: str = dataclasses.field(
        default=RefreshScopeType.SPACE.name, metadata={"help": _("同步范围"),
                                  "label": _("同步范围"),
                                  "options": [
                                      {"name": m.name, "value": m.value}
                                      for m in RefreshScopeType
                                  ]}
    )
    refresh_group_login: str = dataclasses.field(
        default="", metadata={"help": _("同步语雀团队范围"),
                                  "label": _("同步语雀团队范围")}
    )
    refresh_book_slug: str = dataclasses.field(
        default="", metadata={"help": _("同步语雀知识库范围"),
                                  "label": _("同步语雀知识库范围")}
    )
    enable_immediately_refresh: bool = dataclasses.field(
        default=False, metadata={"help": _("是否立即同步"),
                                  "label": _("是否立即同步")}
    )
    vlm_model: str = dataclasses.field(
        default="aistudio/Qwen2.5-VL-72B-Instruct", metadata={"help": _("图片理解模型"),
                                  "label": _("图片理解模型"),
                                  "options": ["aistudio/Qwen2.5-VL-72B-Instruct"]}
    )
    vlm_prompt: str = dataclasses.field(
        default=IMAGE_EXTRACT_SYSTEM_PROMPT, metadata={"help": _("图片理解提示词"),
                                  "label": _("图片理解提示词")}
    )
    embedding_model: str = dataclasses.field(
        default="bge-m3", metadata={"help": _("向量索引模型"),
                                    "label": _("向量索引模型"),
                                    "options": ["bge-m3"]}
    )
    last_modify_user: str = dataclasses.field(
        default="", metadata={"help": _("最后修改人"),
                                  "label": _("最后修改人")}
    )
    yuque: List[dict] = dataclasses.field(
        default="", metadata={"help": _("语雀"),
                                  "label": _("语雀")}
    )

class KnowledgeWriteRequest(BaseModel):
    """doc_name: doc path"""

    file_path: Optional[str] = None
    content: Optional[str] = None
    tag: Optional[List[dict]] = None




