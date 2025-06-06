import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Union

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from derisk._private.config import Config
from derisk._private.pydantic import model_to_dict
from derisk.storage.metadata import BaseDao, Model
from derisk.storage.metadata._base_dao import QUERY_SPEC, REQ, RES
from derisk.util import PaginationResult
from derisk_serve.conversation.api.schemas import ServeRequest
from derisk_serve.rag.api.schemas import (
    DocumentServeRequest,
    DocumentServeResponse,
)

logger = logging.getLogger(__name__)


class KnowledgeDocumentEntity(Model):
    __tablename__ = "knowledge_document"
    id = Column(Integer, primary_key=True)
    doc_id = Column(String(100))
    doc_name = Column(String(100))
    doc_type = Column(String(100))
    doc_token = Column(String(100), name="doc_token")
    knowledge_id = Column(String(100))
    space = Column(String(100))
    chunk_size = Column(Integer)
    status = Column(String(100))
    content = Column(Text)
    chunk_params = Column(Text)
    meta_data = Column(Text)
    result = Column(Text)
    vector_ids = Column(Text)
    summary = Column(Text)
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)
    questions = Column(Text)

    def __repr__(self):
        return (
            f"KnowledgeDocumentEntity(id={self.id}, doc_name='{self.doc_name}', "
            f"doc_id='{self.doc_id}', chunk_size='{self.doc_id}', "
            f"doc_type='{self.doc_type}', chunk_size='{self.chunk_size}', "
            f"knowledge_id='{self.knowledge_id}', "
            f"status='{self.status}', "
            f"content='{self.content}', "
            f"meta_data='{self.meta_data}', "
            f"chunk_params='{self.chunk_params}', "
            f"result='{self.result}', summary='{self.summary}', "
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}', "
            f"questions='{self.questions}')"
        )

    def to_dict(self):
        return {
            "__tablename__": self.__tablename__,
            "id": self.id,
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "knowledge_id": self.knowledge_id,
            "doc_type": self.doc_type,
            "doc_token": self.doc_token,
            "space": self.space,
            "chunk_size": self.chunk_size,
            "status": self.status,
            "content": self.content,
            "result": self.result,
            "vector_ids": self.vector_ids,
            "summary": self.summary,
            "gmt_create": self.gmt_created,
            "gmt_modified": self.gmt_modified,
            "questions": self.questions,
            "chunk_params": self.chunk_params,
        }


class KnowledgeDocumentDao(BaseDao):
    def create_knowledge_document(self, document: KnowledgeDocumentEntity):
        session = self.get_raw_session()
        knowledge_document = KnowledgeDocumentEntity(
            doc_id=document.doc_id,
            doc_name=document.doc_name,
            doc_type=document.doc_type,
            knowledge_id=document.knowledge_id,
            doc_token=document.doc_token,
            space=document.space,
            chunk_size=0.0,
            status=document.status,
            content=document.content or "",
            result=document.result or "",
            summary=document.summary or "",
            vector_ids=document.vector_ids,
            gmt_created=datetime.now(),
            gmt_modified=datetime.now(),
            questions=document.questions,
            chunk_params=document.chunk_params or "",
        )
        session.add(knowledge_document)
        session.commit()
        doc_id = knowledge_document.id
        session.close()
        return doc_id

    def get_knowledge_documents(self, query, page=1, page_size=20):
        """Get a list of documents that match the given query.
        Args:
            query: A KnowledgeDocumentEntity object containing the query parameters.
            page: The page number to return.
            page_size: The number of documents to return per page.
        """
        session = self.get_raw_session()
        print(f"current session:{session}")
        knowledge_documents = session.query(KnowledgeDocumentEntity)
        if query.id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.id == query.id
            )
        if query.doc_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_id == query.doc_id
            )
        if query.doc_name is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_name == query.doc_name
            )
        if query.doc_type is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_type == query.doc_type
            )
        if query.space is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.space == query.space
            )
        if query.knowledge_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.knowledge_id == query.knowledge_id
            )
        if query.status is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.status == query.status
            )

        knowledge_documents = knowledge_documents.order_by(
            KnowledgeDocumentEntity.id.desc()
        )
        knowledge_documents = knowledge_documents.offset((page - 1) * page_size).limit(
            page_size
        )
        result = knowledge_documents.all()
        session.close()
        return result

    def document_by_id(self, document_id) -> KnowledgeDocumentEntity:
        session = self.get_raw_session()
        query = session.query(KnowledgeDocumentEntity).filter(
            KnowledgeDocumentEntity.id == document_id
        )

        result = query.first()
        session.close()
        return result

    def documents_by_ids(self, ids) -> List[KnowledgeDocumentEntity]:
        """Get a list of documents by their IDs.
        Args:
            ids: A list of document IDs.
        Returns:
            A list of KnowledgeDocumentEntity objects.
        """
        session = self.get_raw_session()
        print(f"current session:{session}")
        knowledge_documents = session.query(KnowledgeDocumentEntity)
        knowledge_documents = knowledge_documents.filter(
            KnowledgeDocumentEntity.id.in_(ids)
        )
        result = knowledge_documents.all()
        session.close()
        return result

    def documents_by_doc_ids(self, doc_ids) -> List[KnowledgeDocumentEntity]:
        """Get a list of documents by their IDs.
        Args:
            ids: A list of document IDs.
        Returns:
            A list of KnowledgeDocumentEntity objects.
        """
        session = self.get_raw_session()
        print(f"current session:{session}")
        knowledge_documents = session.query(KnowledgeDocumentEntity)
        knowledge_documents = knowledge_documents.filter(
            KnowledgeDocumentEntity.doc_id.in_(doc_ids)
        )
        result = knowledge_documents.all()
        session.close()
        return result

    def get_documents(
        self, query: KnowledgeDocumentEntity = None, doc_ids=None, filter_status=None
    ):
        logger.info(
            f"get_documents query is {query}, doc_ids is {doc_ids}, filter_status is {filter_status}"
        )

        session = self.get_raw_session()
        print(f"current session:{session}")
        knowledge_documents = session.query(KnowledgeDocumentEntity)
        if query.id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.id == query.id
            )
        if query.doc_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_id == query.doc_id
            )
        if doc_ids is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_id.in_(doc_ids)
            )
        if query.doc_name is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_name == query.doc_name
            )
        if query.knowledge_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.knowledge_id == query.knowledge_id
            )
        if query.doc_type is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_type == query.doc_type
            )
        if query.space is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.space == query.space
            )
        if query.status is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.status == query.status
            )
        if filter_status is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.status.in_(filter_status)
            )
        if query.content is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.content == query.content
            )
        if query.knowledge_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.knowledge_id == query.knowledge_id
            )

        knowledge_documents = knowledge_documents.order_by(
            KnowledgeDocumentEntity.id.desc()
        )
        result = knowledge_documents.all()
        session.close()
        return result

    def get_knowledge_documents_count_bulk(self, space_names):
        session = self.get_raw_session()
        """
        Perform a batch query to count the number of documents for each knowledge space.

        Args:
            space_names: A list of knowledge space names to query for document counts.
            session: A SQLAlchemy session object.

        Returns:
            A dictionary mapping each space name to its document count.
        """
        counts_query = (
            session.query(
                KnowledgeDocumentEntity.space,
                func.count(KnowledgeDocumentEntity.id).label("document_count"),
            )
            .filter(KnowledgeDocumentEntity.space.in_(space_names))
            .group_by(KnowledgeDocumentEntity.space)
        )

        results = counts_query.all()
        docs_count = {result.space: result.document_count for result in results}
        session.close()
        return docs_count

    def get_knowledge_documents_count_bulk_by_ids(self, spaces):
        session = self.get_raw_session()
        """
        Perform a batch query to count the number of documents for each knowledge space.

        Args:
            spaces: A list of knowledge space names to query for document counts.
            session: A SQLAlchemy session object.

        Returns:
            A dictionary mapping each space name to its document count.
        """
        # build the group by query
        counts_query = (
            session.query(
                KnowledgeDocumentEntity.space,
                func.count(KnowledgeDocumentEntity.id).label("document_count"),
            )
            .filter(KnowledgeDocumentEntity.space.in_(spaces))
            .group_by(KnowledgeDocumentEntity.space)
        )

        results = counts_query.all()
        docs_count = {result.space: result.document_count for result in results}
        session.close()
        return docs_count

    def get_knowledge_documents_count(self, query):
        session = self.get_raw_session()
        knowledge_documents = session.query(func.count(KnowledgeDocumentEntity.id))
        if query.id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.id == query.id
            )
        if query.doc_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_id == query.doc_id
            )
        if query.doc_name is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_name == query.doc_name
            )
        if query.doc_type is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_type == query.doc_type
            )
        if query.space is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.space == query.space
            )
        if query.status is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.status == query.status
            )
        count = knowledge_documents.scalar()
        session.close()
        return count

    def update(self, query_request: QUERY_SPEC, update_request: REQ) -> RES:
        """Update an entity object.

        Args:
            query_request (REQ): The request schema object or dict for query.
            update_request (REQ): The request schema object for update.
        Returns:
            RES: The response schema object.
        """
        with self.session() as session:
            query = self._create_query_object(session, query_request)
            entry = query.first()
            if entry is None:
                raise Exception("Invalid request")
            for key, value in model_to_dict(update_request).items():  # type: ignore
                if value is not None:
                    if key in ["gmt_created", "gmt_modified"]:
                        continue
                    setattr(entry, key, value)
            session.merge(entry)
            return self.to_response(entry)

    def update_knowledge_document_by_doc_ids(self, doc_ids: List[str], status: str):
        logger.info(f"update_knowledge_document_by_ids doc_ids is {doc_ids} {status}")

        session = self.get_raw_session()
        try:
            affected_rows = (
                session.query(KnowledgeDocumentEntity)
                .filter(KnowledgeDocumentEntity.doc_id.in_(doc_ids))
                .update(
                    {KnowledgeDocumentEntity.status: status}, synchronize_session=False
                )
            )

            session.commit()
            logger.info(f"Updated {affected_rows} documents to status: '{status}'")

            return affected_rows

        finally:
            session.close()

    def update_set_space_id(self, space, space_id):
        session = self.get_raw_session()
        knowledge_documents = session.query(KnowledgeDocumentEntity)
        if space is not None:
            knowledge_documents.filter(KnowledgeDocumentEntity.space == space).filter(
                KnowledgeDocumentEntity.id is None
            ).update({KnowledgeDocumentEntity.id: space_id}, synchronize_session=False)
            session.commit()
        session.close()

    def update_knowledge_document(self, document: KnowledgeDocumentEntity):
        try:
            session = self.get_raw_session()
            updated_document = session.merge(document)
            session.commit()
            return updated_document.id
        finally:
            session.close()

    def raw_delete(self, query: KnowledgeDocumentEntity):
        logger.info(f"doc raw_delete query is {query}")

        session = self.get_raw_session()
        knowledge_documents = session.query(KnowledgeDocumentEntity)
        if query.id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.id == query.id
            )
        if query.doc_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_id == query.doc_id
            )
        if query.doc_name is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.doc_name == query.doc_name
            )
        if query.space is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.space == query.space
            )
        if query.knowledge_id is not None:
            knowledge_documents = knowledge_documents.filter(
                KnowledgeDocumentEntity.knowledge_id == query.knowledge_id
            )
        knowledge_documents.delete()
        session.commit()
        session.close()

    def get_list_page(
        self, query_request: QUERY_SPEC, page: int, page_size: int
    ) -> PaginationResult[RES]:
        """Get a page of entity objects.

        Args:
            query_request (REQ): The request schema object or dict for query.
            page (int): The page number.
            page_size (int): The page size.

        Returns:
            PaginationResult: The pagination result.
        """
        with self.session() as session:
            query = self._create_query_object(session, query_request)
            total_count = query.count()
            items = (
                query.order_by(KnowledgeDocumentEntity.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = [self.to_response(item) for item in items]
            total_pages = (total_count + page_size - 1) // page_size

            return PaginationResult(
                items=items,
                total_count=total_count,
                total_pages=total_pages,
                page=page,
                page_size=page_size,
            )

    def from_request(
        self, request: Union[ServeRequest, Dict[str, Any]]
    ) -> KnowledgeDocumentEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        request_dict = (
            request.dict() if isinstance(request, DocumentServeRequest) else request
        )
        entity = KnowledgeDocumentEntity(
            id=request_dict.get("id"),
            doc_id=request_dict.get("doc_id"),
            doc_name=request_dict.get("doc_name"),
            doc_type=request_dict.get("doc_type"),
            knowledge_id=request_dict.get("knowledge_id"),
            space=request_dict.get("space"),
            chunk_size=request_dict.get("chunk_size"),
            status=request_dict.get("status"),
            content=request_dict.get("content"),
            result=request_dict.get("result"),
            summary=request_dict.get("summary"),
            chunk_params=json.dumps(
                request_dict.get("chunk_params"), ensure_ascii=False
            ),
            questions=request_dict.get("questions"),
        )
        return entity

    def to_request(self, entity: KnowledgeDocumentEntity) -> DocumentServeRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return DocumentServeRequest(
            id=entity.id,
            doc_id=entity.doc_id,
            doc_name=entity.doc_name,
            doc_type=entity.doc_type,
            space=entity.space,
            chunk_size=entity.chunk_size,
            status=entity.status,
            content=entity.content,
            result=entity.result,
            summary=entity.summary,
            chunk_params=json.loads(entity.chunk_params),
            questions=entity.questions,
            gmt_created=entity.gmt_created,
            gmt_modified=entity.gmt_modified,
        )

    def to_response(self, entity: KnowledgeDocumentEntity) -> DocumentServeResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return DocumentServeResponse(
            id=entity.id,
            doc_id=entity.doc_id,
            doc_name=entity.doc_name,
            doc_type=entity.doc_type,
            space=entity.space,
            chunk_size=entity.chunk_size,
            status=entity.status,
            content=entity.content,
            result=entity.result,
            summary=entity.summary,
            questions=entity.questions,
            gmt_created=str(entity.gmt_created),
            gmt_modified=str(entity.gmt_modified),
        )

    def from_response(
        self, response: Union[DocumentServeResponse, Dict[str, Any]]
    ) -> KnowledgeDocumentEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        response_dict = (
            response.dict() if isinstance(response, DocumentServeResponse) else response
        )
        entity = KnowledgeDocumentEntity(
            id=response_dict.get("id"),
            doc_id=response_dict.get("doc_id"),
            doc_name=response_dict.get("doc_name"),
            doc_type=response_dict.get("doc_type"),
            doc_token=response_dict.get("doc_token"),
            space=response_dict.get("space"),
            chunk_size=response_dict.get("chunk_size"),
            status=response_dict.get("status"),
            content=response_dict.get("content"),
            result=response_dict.get("result"),
            vector_ids=response_dict.get("vector_ids"),
            summary=response_dict.get("summary"),
            questions=response_dict.get("questions"),
        )
        return entity
