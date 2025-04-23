from typing import List, Optional, Union

from fastapi import File, UploadFile

from derisk._private.pydantic import BaseModel, ConfigDict, Field
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
    document_id: Optional[str] = Field(None, description="document id")
    knowledge_id: Optional[str] = Field(None, description="The space id")
    doc_name: Optional[str] = Field(None, description="document name")
    doc_type: Optional[str] = Field(None, description="document type")
    content: Optional[str] = Field(None, description="chunk content")
    meta_data: Optional[str] = Field(None, description="chunk meta info")
    questions: Optional[List[str]] = Field(None, description="chunk questions")
    gmt_created: Optional[str] = Field(None, description="chunk create time")
    gmt_modified: Optional[str] = Field(None, description="chunk modify time")


class ChunkServeResponse(BaseModel):
    id: Optional[int] = Field(None, description="The primary id")
    document_id: Optional[str] = Field(None, description="document id")
    doc_id: Optional[str] = Field(None, description="doc id")
    vector_id: Optional[str] = Field(None, description="vector id")
    full_text_id: Optional[str] = Field(None, description="full_text id")
    doc_name: Optional[str] = Field(None, description="document name")
    doc_type: Optional[str] = Field(None, description="document type")
    content: Optional[str] = Field(None, description="chunk content")
    meta_data: Optional[str] = Field(None, description="chunk meta info")
    questions: Optional[str] = Field(None, description="chunk questions")
    gmt_created: Optional[str] = Field(None, description="chunk create time")
    gmt_modified: Optional[str] = Field(None, description="chunk modify time")


class KnowledgeSyncRequest(BaseModel):
    """Sync request"""

    """doc_ids: doc ids"""
    doc_id: Optional[int] = Field(None, description="The doc id")

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


class KnowledgeSearchRequest(BaseModel):
    """Knowledge Search Request"""

    query: Optional[str] = None
    knowledge_ids: Optional[List[str]] = None
    top_k: Optional[int] = 5
    score_threshold: Optional[float] = 0.5
    similarity_score_threshold: Optional[float] = 0.0
    single_knowledge_top_k: Optional[int] = 5
    enable_rerank: Optional[bool] = True
    enable_summary: Optional[bool] = False
    enable_tag_filter: Optional[bool] = True
    summary_model: Optional[str] = "qwen2.5_72b_proxyllm"
    summary_prompt: Optional[str] = None
    summary_tokens: Optional[int] = 1000


# 复用这里代码


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
