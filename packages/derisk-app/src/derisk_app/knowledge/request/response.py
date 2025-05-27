import json
from typing import List, Optional

from derisk._private.pydantic import BaseModel, Field
from derisk_serve.rag.api.schemas import (
    ChunkServeResponse,
    DocumentServeResponse,
)
from derisk_serve.rag.models.document_db import KnowledgeDocumentEntity


class ChunkDetailResponse(BaseModel):
    id: Optional[int] = Field(None, description="The primary id")
    document_id: Optional[str] = Field(None, description="document id")
    vector_id: Optional[str] = Field(None, description="vector id")
    full_text_id: Optional[str] = Field(None, description="full_text id")
    doc_name: Optional[str] = Field(None, description="document name")
    doc_type: Optional[str] = Field(None, description="document type")
    content: Optional[str] = Field(None, description="chunk content")
    meta_info: Optional[str] = Field(None, description="chunk meta info")
    questions: Optional[str] = Field(None, description="chunk questions")
    gmt_created: Optional[str] = Field(None, description="chunk create time")
    gmt_modified: Optional[str] = Field(None, description="chunk modify time")

    @classmethod
    def to_chunk_serve_response(cls, res: ChunkServeResponse):
        """Convert the entity to a response

        Args:
            res (T): The response

        Returns:
            REQ: The request
        """
        return ChunkDetailResponse(
            id=res.id,
            document_id=res.doc_id,
            vector_id=res.vector_id,
            full_text_id=res.full_text_id,
            doc_name=res.doc_name,
            doc_type=res.doc_type,
            content=res.content,
            meta_info=res.meta_data,
            questions=res.questions,
            gmt_created=str(res.gmt_created),
            gmt_modified=str(res.gmt_modified),
        )


class ChunkQueryResponse(BaseModel):
    """data: data"""

    data: List[ChunkDetailResponse] = Field(None, description="document chunk list")
    """summary: document summary"""
    summary: Optional[str] = Field(None, description="document summary")
    """total: total size"""
    total: Optional[int] = Field(None, description="total size")
    """page: current page"""
    page: Optional[int] = Field(None, description="current page")


class DocumentResponse(BaseModel):
    """DocumentResponse: DocumentResponse"""

    id: Optional[int] = Field(None, description="The doc id")
    doc_name: Optional[str] = Field(None, description="doc type")
    """vector_type: vector type"""
    doc_type: Optional[str] = Field(None, description="The doc content")
    """desc: description"""
    content: Optional[str] = Field(None, description="content")
    """vector ids"""
    vector_ids: Optional[str] = Field(None, description="vector ids")
    """space: space name"""
    space: Optional[str] = Field(None, description="space name")
    """space_id: space id"""
    space_id: Optional[int] = Field(None, description="space id")
    """status: status"""
    status: Optional[str] = Field(None, description="status")
    """result: result"""
    result: Optional[str] = Field(None, description="result")
    """summary: summary"""
    summary: Optional[str] = Field(None, description="summary")
    """gmt_created: created time"""
    gmt_created: Optional[str] = Field(None, description="created time")
    """gmt_modified: modified time"""
    gmt_modified: Optional[str] = Field(None, description="modified time")
    """chunk_size: chunk size"""
    chunk_size: Optional[int] = Field(None, description="chunk size")
    """questions: questions"""
    questions: Optional[List[str]] = Field(None, description="questions")

    @classmethod
    def to_response(cls, entity: KnowledgeDocumentEntity):
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return DocumentResponse(
            id=entity.id,
            doc_name=entity.doc_name,
            doc_type=entity.doc_type,
            space=entity.space,
            chunk_size=entity.chunk_size,
            status=entity.status,
            content=entity.content,
            result=entity.result,
            vector_ids=entity.vector_ids,
            summary=entity.summary,
            questions=json.loads(entity.questions) if entity.questions else None,
            gmt_created=str(entity.gmt_created),
            gmt_modified=str(entity.gmt_modified),
        )

    @classmethod
    def serve_to_response(cls, response: DocumentServeResponse):
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return DocumentResponse(
            id=response.id,
            doc_name=response.doc_name,
            doc_type=response.doc_type,
            space=response.space,
            chunk_size=response.chunk_size,
            status=response.status,
            content=response.content,
            result=response.result,
            vector_ids=response.vector_ids,
            summary=response.summary,
            questions=json.loads(response.questions) if response.questions else None,
            gmt_created=str(response.gmt_created),
            gmt_modified=str(response.gmt_modified),
        )


class SpaceQueryResponse(BaseModel):
    """data: data"""

    id: Optional[int] = None
    knowledge_id: Optional[str] = None
    name: Optional[str] = None
    """vector_type: vector type"""
    storage_type: Optional[str] = None
    """domain_type"""
    domain_type: Optional[str] = None
    """desc: description"""
    desc: Optional[str] = None
    """context: context"""
    context: Optional[str] = None
    """owner: owner"""
    owner: Optional[str] = None
    gmt_created: Optional[str] = None
    gmt_modified: Optional[str] = None
    """doc_count: doc_count"""
    docs: Optional[int] = None


class KnowledgeQueryResponse(BaseModel):
    """source: knowledge reference source"""

    source: str
    """score: knowledge vector query similarity score"""
    score: float = 0.0
    """text: raw text info"""
    text: str


class DocumentQueryResponse(BaseModel):
    """data: data"""

    data: List[DocumentResponse] = Field(None, description="document list")
    """total: total size"""
    total: Optional[int] = Field(None, description="total size")
    """page: current page"""
    page: Optional[int] = Field(None, description="current page")
