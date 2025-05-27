import asyncio
import concurrent
import json
import logging
import os
import re
import socket
import threading
import time
import timeit
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, cast, Any, Dict

from fastapi import HTTPException, File

from derisk.component import ComponentType, SystemApp
from derisk.configs import TAG_KEY_KNOWLEDGE_FACTORY_DOMAIN_TYPE
from derisk.configs.model_config import (
    KNOWLEDGE_CACHE_ROOT_PATH,
)
from derisk.core import Chunk, LLMClient
from derisk.core.awel import DAG, InputOperator, SimpleCallDataInputSource
from derisk.core.interface.file import _SCHEMA, FileStorageClient
from derisk.model import DefaultLLMClient
from derisk.model.cluster import WorkerManagerFactory
from derisk.rag.embedding.embedding_factory import (
    RerankEmbeddingFactory,
)
from derisk.rag.knowledge import ChunkStrategy, KnowledgeType
from derisk.rag.knowledge.base import TaskStatusType
from derisk.rag.retriever.rerank import RerankEmbeddingsRanker, RetrieverNameRanker
from derisk.rag.transformer.summary_extractor import SummaryExtractor
from derisk.storage.base import IndexStoreBase
from derisk.storage.metadata import BaseDao
from derisk.storage.metadata._base_dao import QUERY_SPEC
from derisk.storage.vector_store.filters import FilterCondition, MetadataFilters
from derisk.util.executor_utils import blocking_func_to_async_no_executor
from derisk.util.pagination_utils import PaginationResult
from derisk.util.string_utils import remove_trailing_punctuation
from derisk.util.tracer import root_tracer, trace
from derisk_app.knowledge.request.request import BusinessFieldType
from derisk_app.knowledge.request.response import DocumentResponse
from derisk_ext.rag.chunk_manager import ChunkParameters, ChunkParametersEncoder
from derisk_ext.rag.knowledge import KnowledgeFactory

from derisk_serve.core import BaseService, blocking_func_to_async

from ..api.schemas import (
    ChunkServeRequest,
    DocumentServeRequest,
    DocumentServeResponse,
    KnowledgeRetrieveRequest,
    KnowledgeSyncRequest,
    SpaceServeRequest,
    SpaceServeResponse,
    KnowledgeSearchRequest,
    KnowledgeDocumentRequest,
    KnowledgeSearchResponse,
    DocumentSearchResponse,
    StrategyDetail,
    ParamDetail,
    ChunkEditRequest, OutlineChunk, KnowledgeTaskRequest, KnowledgeTaskResponse
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..domain.index import DomainGeneralIndex
from ..models.chunk_db import DocumentChunkDao, DocumentChunkEntity
from ..models.document_db import (
    KnowledgeDocumentDao,
    KnowledgeDocumentEntity,
)
from ..models.knowledge_task_db import KnowledgeTaskEntity, KnowledgeTaskDao
from ..models.models import KnowledgeSpaceDao, KnowledgeSpaceEntity
from ..models.rag_span_db import RagFlowSpanDao
from ..operators.knowledge_space import SpaceRetrieverOperator
from ..operators.summary import SummaryOperator
from ..retriever.knowledge_space import KnowledgeSpaceRetriever
from ..storage_manager import StorageManager
from ..transformer.tag_extractor import TagsExtractor
from ...agent.db.gpts_app import GptsAppDao

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    TODO = "待处理"
    FAILED = "失败"
    RUNNING = "处理中"
    FINISHED = "可用"
    RETRYING = "重试中"


class Service(BaseService[KnowledgeSpaceEntity, SpaceServeRequest, SpaceServeResponse]):
    """The service class for Flow"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[KnowledgeSpaceDao] = None,
        document_dao: Optional[KnowledgeDocumentDao] = None,
        chunk_dao: Optional[DocumentChunkDao] = None,
        task_dao: Optional[KnowledgeTaskDao] = None,
        rag_span_dao: Optional[RagFlowSpanDao] = None,
        gpts_app_dao: Optional[GptsAppDao] = None
    ):
        self._system_app = system_app
        self._dao: KnowledgeSpaceDao = dao
        self._document_dao: KnowledgeDocumentDao = document_dao
        self._chunk_dao: DocumentChunkDao = chunk_dao
        self._task_dao: KnowledgeTaskDao = task_dao
        self._rag_span_dao: RagFlowSpanDao = rag_span_dao
        self._gpts_app_dao: GptsAppDao = gpts_app_dao
        self._serve_config = config

        self._knowledge_id_stores = {}


        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or KnowledgeSpaceDao()
        self._document_dao = self._document_dao or KnowledgeDocumentDao()
        self._chunk_dao = self._chunk_dao or DocumentChunkDao()
        self._task_dao = self._task_dao or KnowledgeTaskDao()
        self._rag_span_dao = self._rag_span_dao or RagFlowSpanDao()
        self._gpts_app_dao = self._gpts_app_dao or GptsAppDao()
        self._system_app = system_app

    @property
    def storage_manager(self):
        return StorageManager.get_instance(self._system_app)

    @property
    def dao(
        self,
    ) -> BaseDao[KnowledgeSpaceEntity, SpaceServeRequest, SpaceServeResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    @property
    def llm_client(self) -> LLMClient:
        worker_manager = self._system_app.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        return DefaultLLMClient(worker_manager, True)

    def get_fs(self) -> FileStorageClient:
        """Get the FileStorageClient instance"""
        return FileStorageClient.get_instance(self.system_app)

    def create_space(self, request: SpaceServeRequest) -> str:
        """Create a new Space entity

        Args:
            request (KnowledgeSpaceRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        query = {"name": request.name}
        if request.vector_type:
            request.storage_type = request.vector_type
        if request.storage_type == "VectorStore":
            request.storage_type = (
                self.storage_manager.storage_config().vector.get_type_value()
            )
        if request.storage_type == "KnowledgeGraph":
            knowledge_space_name_pattern = r"^[_a-zA-Z0-9\u4e00-\u9fa5]+$"
            if not re.match(knowledge_space_name_pattern, request.name):
                raise Exception(f"space name:{request.name} invalid")
        if request.owner:
            query.update({"owner": request.owner})
        if request.sys_code:
            query.update({"sys_code": request.sys_code})

        space = self.get(query)
        if space is not None:
            raise HTTPException(
                status_code=400,
                detail=f"knowledge name:{request.name} have already named",
            )
        if request.knowledge_type is None:
            request.knowledge_type = "PRIVATE"

        knowledge_id = str(uuid.uuid4())
        request.knowledge_id = knowledge_id
        # request.gmt_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # request.gmt_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        request.gmt_created = datetime.now()
        request.gmt_modified = datetime.now()
        self._dao.create(request)
        return knowledge_id

    def update_space_by_knowledge_id(self, update: SpaceServeRequest):
        logger.info(f"update_space_by_knowledge_id update is {update}")

        # get space
        if not update.knowledge_id:
            raise Exception("knowledge_id is required")

        knowledge_spaces = self._dao.get_knowledge_space(
            query=KnowledgeSpaceEntity(knowledge_id=update.knowledge_id)
        )
        if knowledge_spaces is None or len(knowledge_spaces) == 0:
            raise Exception(f"can not found space for {update.knowledge_id}")
        if len(knowledge_spaces) > 1:
            raise Exception(
                f"found more than one space! {update.knowledge_id} {len(knowledge_spaces)}"
            )
        knowledge_space = knowledge_spaces[0]

        if update.name:
            knowledge_space.name = update.name
        if update.desc:
            knowledge_space.desc = update.desc
        if update.category:
            knowledge_space.category = update.category
        if update.tags:
            knowledge_space.tags = update.tags
        if update.knowledge_type:
            knowledge_space.knowledge_type = update.knowledge_type

        # update
        self._dao.update_knowledge_space(knowledge_space)

        return True

    def update_space(self, request: SpaceServeRequest) -> SpaceServeResponse:
        """Create a new Space entity

        Args:
            request (KnowledgeSpaceRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        query = {}
        if request.name:
            query.update({"name": request.name})
        if request.knowledge_id:
            query.update({"knowledge_id": request.knowledge_id})
        if request.owner:
            query.update({"owner": request.owner})
        if request.sys_code:
            query.update({"sys_code": request.sys_code})
        spaces = self._dao.get_list(query)
        if not spaces:
            raise HTTPException(
                status_code=400,
                detail=f"no knowledge space found {request}",
            )
        update_obj = self._dao.update_knowledge_space(self._dao.from_request(request))
        return update_obj

    def create_document(self, request: DocumentServeRequest) -> str:
        """Create a new document entity

        Args:
            request (KnowledgeSpaceRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        knowledge_query = {}
        if request.knowledge_id:
            knowledge_query.update({"knowledge_id": request.knowledge_id})
        if request.space_name:
            knowledge_query.update({"name": request.space_name})
        space = self.get(knowledge_query)
        if space is None:
            raise Exception(f"knowledge id:{request.space_id} not found")
        # query = KnowledgeDocumentEntity(doc_name=request.doc_name, space=space.name)
        doc_query = {}
        if request.doc_name:
            doc_query.update({"doc_name": request.doc_name})
        if space.knowledge_id:
            doc_query.update({"knowledge_id": space.knowledge_id})
        documents = self._document_dao.get_list(doc_query)
        custom_metadata = request.meta_data
        if len(documents) > 0:
            raise Exception(f"document name:{request.doc_name} have already named")
        if request.doc_file and request.doc_type == KnowledgeType.DOCUMENT.name:
            doc_file = request.doc_file
            safe_filename = os.path.basename(doc_file.filename)
            custom_metadata = {
                "space_name": space.name,
                "doc_name": doc_file.filename,
                "doc_type": request.doc_type,
            }
            if request.tags:
                custom_metadata.update({"tags": request.tags})
            bucket = "derisk_knowledge_file"
            file_uri = self.get_fs().save_file(
                bucket,
                safe_filename,
                doc_file.file,
                custom_metadata=custom_metadata,
            )
            request.content = file_uri
        doc_id = str(uuid.uuid4())
        document = {
            "doc_name": request.doc_name,
            "knowledge_id": space.knowledge_id,
            "doc_id": doc_id,
            "doc_type": request.doc_type,
            "space": space.name,
            "chunk_size": 0,
            "status": SyncStatus.TODO.name,
            "last_sync": datetime.now(),
            "content": request.content,
            "metadata": json.dumps(custom_metadata),
            "result": "",
        }
        res = self._document_dao.create(document)
        if doc_id is None:
            raise Exception(f"create document failed, {request.doc_name}")
        return res

    async def sync_document(self, requests: List[KnowledgeSyncRequest], knowledge_id_stores: Optional[dict] = None) -> List:
        """Create a new document entity

        Args:
            request (KnowledgeSpaceRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        logger.info(f"sync_document requests len is {len(requests)}, knowledge_id_stores is {knowledge_id_stores}")

        doc_ids = []
        for sync_request in requests:
            knowledge_id = sync_request.knowledge_id
            docs = self._document_dao.documents_by_doc_ids([sync_request.doc_id])
            if len(docs) == 0:
                raise Exception(
                    f"there are document called, doc_id: {sync_request.doc_id}"
                )
            doc = docs[0]
            if (
                doc.status == SyncStatus.RUNNING.name
                or doc.status == SyncStatus.FINISHED.name
            ):
                raise Exception(
                    f" doc:{doc.doc_name} status is {doc.status}, can not sync"
                )
            chunk_parameters = sync_request.chunk_parameters

            # update chunk params
            if chunk_parameters is None:
                if doc.chunk_params:
                    chunk_parameters_dict = json.loads(doc.chunk_params)
                    if chunk_parameters_dict["enable_merge"] is None:
                        chunk_parameters_dict["enable_merge"] = False
                    chunk_parameters = ChunkParameters(**chunk_parameters_dict)
                else:
                    chunk_parameters = ChunkParameters(
                        chunk_strategy="CHUNK_BY_SIZE", chunk_size=512, chunk_overlap=50
                    )
            logger.info(f"chunk_parameters is {chunk_parameters}")

            knowledge_id_store = None
            if knowledge_id_stores is not None:
                logger.info(f"update knowledge_id_stores is {knowledge_id_stores}")

                knowledge_id_store = knowledge_id_stores.get(knowledge_id)

            await self._sync_knowledge_document(
                knowledge_id, doc, chunk_parameters, knowledge_id_store=knowledge_id_store
            )
            doc_ids.append(doc.id)
        return doc_ids

    def get(self, request: QUERY_SPEC) -> Optional[SpaceServeResponse]:
        """Get a Flow entity

        Args:
            request (SpaceServeRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self._dao.get_one(query_request)

    def get_document(self, request: QUERY_SPEC) -> Optional[DocumentServeResponse]:
        """Get a Flow entity

        Args:
            request (SpaceServeRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self._document_dao.get_one(query_request)


    def get_agents_by_knowledge_id(self, knowledge_id: str):
        # get apps
        if not knowledge_id:
            raise Exception("knowledge_id is required")

        apps = self._gpts_app_dao.get_gpts_apps_by_knowledge_id(knowledge_id=knowledge_id)
        if not apps:
            return None

        # get agents
        agents = [app.app_name for app in apps]
        logger.info(f"get_agents_by_knowledge_id agents len is {len(agents)} name is {agents}")

        return agents

    def delete(self, knowledge_id: str) -> Optional[bool]:
        """Delete a Knowledge entity

        Args:
            knowledge_id (str): The knowledge_id

        Returns:
            bool: delete success
        """
        # Build the query request from the request
        logger.info(f"delete knowledge_id is {knowledge_id}")

        query_request = {"knowledge_id": knowledge_id}
        space = self.get(query_request)
        if space is None:
            raise HTTPException(
                status_code=400, detail=f"Knowledge Space {knowledge_id} not found"
            )

        # 判断知识库是否被agent使用
        used_agents = self.get_agents_by_knowledge_id(knowledge_id=knowledge_id)
        if used_agents:
            logger.error(f"delete knowledge_id not invalid, agents {used_agents} used knowledge_id {knowledge_id}")

            raise Exception(f"knowledge id {knowledge_id} is used by agents {used_agents}")

        document_query = KnowledgeDocumentEntity(knowledge_id=space.knowledge_id)
        documents = self._document_dao.get_documents(document_query)
        if documents:
            storage_connector = self.get_or_update_knowledge_id_store(knowledge_id=space.knowledge_id)
            # delete vectors
            storage_connector.delete_vector_name(space.name)
            for document in documents:
                # delete chunks
                self._chunk_dao.raw_delete(doc_id=document.doc_id)

            # delete documents
            self._document_dao.raw_delete(document_query)
        # delete space
        self._dao.delete(query_request)
        return True

    def update_document(self, request: DocumentServeRequest):
        """update knowledge document

        Args:
            - space_id: space id
            - request: KnowledgeDocumentRequest
        """
        if not request.id:
            raise Exception("doc_id is required")
        document = self._document_dao.get_one({"id": request.id})
        entity = self._document_dao.from_response(document)
        if request.doc_name:
            entity.doc_name = request.doc_name
            update_chunk = self._chunk_dao.get_one({"document_id": entity.id})
            if update_chunk:
                update_chunk.doc_name = request.doc_name
                self._chunk_dao.update({"id": update_chunk.id}, update_chunk)
        if len(request.questions) == 0:
            entity.questions = ""
        else:
            questions = [
                remove_trailing_punctuation(question) for question in request.questions
            ]
            entity.questions = json.dumps(questions, ensure_ascii=False)
        self._document_dao.update(
            {"id": entity.id}, self._document_dao.to_request(entity)
        )

    def delete_document(self, document_id: str) -> Optional[DocumentServeResponse]:
        """Delete a Flow entity

        Args:
            uid (str): The uid

        Returns:
            SpaceServeResponse: The data after deletion
        """

        query_request = {"id": document_id}
        docuemnt = self._document_dao.get_one(query_request)
        if docuemnt is None:
            raise Exception(f"there are no or more than one document  {document_id}")

        # get space by name
        spaces = self._dao.get_knowledge_space(
            KnowledgeSpaceEntity(name=docuemnt.space)
        )
        if len(spaces) != 1:
            raise Exception(f"invalid space name: {docuemnt.space}")
        space = spaces[0]

        knowledge_id = space.knowledge_id
        vector_ids = docuemnt.vector_ids
        if vector_ids is not None:
            vector_store_connector = self.get_or_update_knowledge_id_store(knowledge_id=knowledge_id)

            # delete vector by ids
            vector_store_connector.delete_by_ids(vector_ids)
        # delete chunks
        self._chunk_dao.raw_delete(docuemnt.id)
        # delete document
        self._document_dao.raw_delete(docuemnt)
        return docuemnt

    def get_list(self, request: SpaceServeRequest) -> List[SpaceServeResponse]:
        """Get a list of Flow entities

        Args:
            request (SpaceServeRequest): The request

        Returns:
            List[SpaceServeResponse]: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_list(query_request)

    def get_knowledge_ids(self, request: SpaceServeRequest):
        logger.info(f"get_knowledge_ids request is {request}")

        query = KnowledgeSpaceEntity()
        if request.category:
            query.category = request.category
        if request.knowledge_type:
            query.knowledge_type = request.knowledge_type

        spaces = self._dao.get_knowledge_space(
            query=query, name_or_tag=request.name_or_tag
        )
        knowledge_id_tags = {}
        for space in spaces:
            try:
                tags = json.loads(space.tags) if space.tags else []
            except Exception as e:
                logger.error(
                    f"get_knowledge_ids error knowledge_id is {space.knowledge_id}, tags is {space.tags}, exception is {str(e)}"
                )
                tags = []
            knowledge_id_tags[space.knowledge_id] = tags
        logger.info(
            f"get_knowledge_ids spaces is {len(spaces)}, knowledge_id_tags is {knowledge_id_tags}"
        )

        return knowledge_id_tags

    def get_list_by_page(
        self, request: QUERY_SPEC, page: int, page_size: int
    ) -> PaginationResult[SpaceServeResponse]:
        """Get a list of Flow entities by page

        Args:
            request (SpaceServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[SpaceServeResponse]: The response
        """
        return self.dao.get_list_page(request, page, page_size)

    def get_document_list(self, request: QUERY_SPEC) -> List[DocumentServeResponse]:
        """Get a list of Flow entities by page

        Args:
            request (SpaceServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[SpaceServeResponse]: The response
        """
        return self._document_dao.get_list(request)

    def get_document_list_page(
        self, request: QUERY_SPEC, page: int, page_size: int
    ) -> PaginationResult[DocumentServeResponse]:
        """Get a list of Flow entities by page

        Args:
            request (SpaceServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[SpaceServeResponse]: The response
        """
        return self._document_dao.get_list_page(request, page, page_size)

    def get_chunk_list_page(self, request: QUERY_SPEC, page: int, page_size: int):
        """get document chunks with page
        Args:
            - request: QUERY_SPEC
        """
        return self._chunk_dao.get_list_page(request, page, page_size)

    def get_chunk_list(self, request: QUERY_SPEC):
        """get document chunks
        Args:
            - request: QUERY_SPEC
        """
        return self._chunk_dao.get_list(request)

    def update_chunk(self, request: ChunkServeRequest):
        """update knowledge document chunk"""
        if not request.id:
            raise Exception("chunk_id is required")
        chunk = self._chunk_dao.get_one({"id": request.id})
        entity = self._chunk_dao.from_response(chunk)
        if request.content:
            entity.content = request.content
        if request.questions:
            questions = [
                remove_trailing_punctuation(question) for question in request.questions
            ]
            entity.questions = json.dumps(questions, ensure_ascii=False)
        self._chunk_dao.update_chunk(entity)

    async def _batch_document_sync(
        self, space_id, sync_requests: List[KnowledgeSyncRequest]
    ) -> List[int]:
        """batch sync knowledge document chunk into vector store
        Args:
            - space: Knowledge Space Name
            - sync_requests: List[KnowledgeSyncRequest]
        Returns:
            - List[int]: document ids
        """
        doc_ids = []
        for sync_request in sync_requests:
            docs = self._document_dao.documents_by_ids([sync_request.doc_id])
            if len(docs) == 0:
                raise Exception(
                    f"there are document called, doc_id: {sync_request.doc_id}"
                )
            doc = docs[0]
            if (
                doc.status == SyncStatus.RUNNING.name
                or doc.status == SyncStatus.FINISHED.name
            ):
                raise Exception(
                    f" doc:{doc.doc_name} status is {doc.status}, can not sync"
                )
            chunk_parameters = sync_request.chunk_parameters
            if chunk_parameters.chunk_strategy != ChunkStrategy.CHUNK_BY_SIZE.name:
                space_context = self.get_space_context(space_id)
                chunk_parameters.chunk_size = (
                    self._serve_config.chunk_size
                    if space_context is None
                    else int(space_context["embedding"]["chunk_size"])
                )
                chunk_parameters.chunk_overlap = (
                    self._serve_config.chunk_overlap
                    if space_context is None
                    else int(space_context["embedding"]["chunk_overlap"])
                )
            await self._sync_knowledge_document(space_id, doc, chunk_parameters)
            doc_ids.append(doc.id)
        return doc_ids

    async def _sync_knowledge_document(
        self,
        knowledge_id,
        doc: KnowledgeDocumentEntity,
        chunk_parameters: ChunkParameters,
        knowledge_id_store: Optional[IndexStoreBase] = None
    ) -> None:
        """sync knowledge document chunk into vector store"""
        logger.info(f"_sync_knowledge_document start, 当前线程数：{threading.active_count()}, knowledge_id_store is {knowledge_id_store}")

        space = self.get({"knowledge_id": knowledge_id})

        if knowledge_id_store is None:
            storage_connector = self.get_or_update_knowledge_id_store(knowledge_id=knowledge_id)
        else:
            storage_connector = knowledge_id_store

        knowledge_content = doc.content
        if (
            doc.doc_type == KnowledgeType.DOCUMENT.value
            and knowledge_content.startswith(_SCHEMA)
        ):
            logger.info(
                f"Download file from file storage, doc: {doc.doc_name}, file url: "
                f"{doc.content}"
            )
            local_file_path, file_meta = await blocking_func_to_async(
                self.system_app,
                self.get_fs().download_file,
                knowledge_content,
                dest_dir=KNOWLEDGE_CACHE_ROOT_PATH,
            )
            logger.info(f"Downloaded file to {local_file_path}")
            knowledge_content = local_file_path
        knowledge = None
        if not space.domain_type or (
            space.domain_type.lower() == BusinessFieldType.NORMAL.value.lower()
        ):
            labels = {"label": doc.summary} if doc.summary else None

            knowledge = KnowledgeFactory.create(
                datasource=knowledge_content,
                knowledge_type=KnowledgeType.get_by_value(doc.doc_type),
                metadata=labels,
                doc_token=doc.doc_token,
                doc_id=doc.doc_id,
            )

        doc.status = SyncStatus.RUNNING.name
        doc.chunk_params = json.dumps(chunk_parameters, cls=ChunkParametersEncoder)

        doc.gmt_modified = datetime.now()
        domain_index = DomainGeneralIndex()

        chunks = await domain_index.extract(knowledge, chunk_parameters)

        chunk_entities = [
            DocumentChunkEntity(
                chunk_id=chunk_doc.chunk_id,
                doc_name=doc.doc_name,
                doc_type=doc.doc_type,
                doc_id=doc.doc_id,
                content=chunk_doc.content,
                meta_data=json.dumps(chunk_doc.metadata, ensure_ascii=False),
                knowledge_id=knowledge_id,
                gmt_created=datetime.now(),
                gmt_modified=datetime.now(),
            )
            for chunk_doc in chunks
        ]
        self._chunk_dao.create_documents_chunks(chunk_entities)
        doc.chunk_size = len(chunks)

        await blocking_func_to_async(
            self.system_app, self._document_dao.update_knowledge_document, doc
        )

        await self.async_doc_process(
            domain_index,
            chunks,
            storage_connector,
            doc,
            space,
            knowledge_content,
        )

        logger.info(f"begin save document chunks, doc:{doc.doc_name}")

    @trace("async_doc_process")
    async def async_doc_process(
        self,
        domain_index: DomainGeneralIndex,
        chunks,
        storage_connector,
        doc,
        space,
        knowledge_content: str,
    ):
        """async document process into storage
        Args:
            - knowledge: Knowledge
            - chunk_parameters: ChunkParameters
            - vector_store_connector: vector_store_connector
            - doc: doc
        """

        logger.info(f"async doc persist sync, doc:{doc.doc_name}")
        try:
            with root_tracer.start_span(
                "app.knowledge.assembler.persist",
                metadata={"doc": doc.doc_name},
            ):
                from derisk.core.awel import BaseOperator

                dags = self.dag_manager.get_dags_by_tag(
                    TAG_KEY_KNOWLEDGE_FACTORY_DOMAIN_TYPE, space.domain_type
                )
                if dags and dags[0].leaf_nodes:
                    end_task = cast(BaseOperator, dags[0].leaf_nodes[0])
                    logger.info(
                        f"Found dag by tag key: {TAG_KEY_KNOWLEDGE_FACTORY_DOMAIN_TYPE}"
                        f" and value: {space.domain_type}, dag: {dags[0]}"
                    )
                    db_name, chunk_docs = await end_task.call(
                        {"file_path": knowledge_content, "space": doc.space}
                    )
                    doc.chunk_size = len(chunk_docs)
                    vector_ids = [chunk.chunk_id for chunk in chunk_docs]
                else:
                    max_chunks_once_load = self.config.max_chunks_once_load
                    max_threads = self.config.max_threads

                    save_chunks = await domain_index.load(
                        chunks=chunks,
                        vector_store=storage_connector,
                        max_chunks_once_load=max_chunks_once_load,
                        max_threads=max_threads,
                    )
                    logger.info(f"async_doc_process end 当前线程数: {threading.active_count()}")

                    vector_ids = []
                    for save_chunk in save_chunks:
                        query_chunk = {"chunk_id": save_chunk.chunk_id}
                        self._chunk_dao.update(query_chunk, save_chunk)
                        vector_ids.append(save_chunk.vector_id)
            doc.status = SyncStatus.FINISHED.name
            doc.result = "document persist into index store success"
            if vector_ids:
                doc.vector_ids = ",".join(vector_ids)
            logger.info(f"async document persist index store success:{doc.doc_name}")
            # save chunk details

        except Exception as e:
            doc.status = SyncStatus.FAILED.name
            doc.result = "document embedding failed" + str(e)
            logger.error(f"document embedding, failed:{doc.doc_name}, {str(e)}")
        return self._document_dao.update_knowledge_document(doc)

    def get_space_context(self, space_id):
        """get space contect
        Args:
           - space_name: space name
        """
        space = self.get({"id": space_id})
        if space is None:
            raise Exception(
                f"have not found {space_id} space or found more than one space called "
                f"{space_id}"
            )
        if space.context is not None:
            return json.loads(space.context)
        return None

    async def retrieve(
        self, request: KnowledgeRetrieveRequest, space: SpaceServeResponse
    ) -> List[Chunk]:
        """Retrieve the service."""
        reranker: Optional[RerankEmbeddingsRanker] = None
        top_k = request.top_k
        if self._serve_config.rerank_model:
            reranker_top_k = self._serve_config.rerank_top_k
            rerank_embeddings = RerankEmbeddingFactory.get_instance(
                self._system_app
            ).create()
            reranker = RerankEmbeddingsRanker(rerank_embeddings, topk=reranker_top_k)
            if top_k < reranker_top_k or self._top_k < 20:
                # We use reranker, so if the top_k is less than 20,
                # we need to set it to 20
                top_k = max(reranker_top_k, 20)

        space_retriever = KnowledgeSpaceRetriever(
            space_id=space.id,
            embedding_model=self._serve_config.embedding_model,
            top_k=top_k,
            rerank=reranker,
            system_app=self._system_app,
        )
        return await space_retriever.aretrieve_with_scores(
            request.query, request.score_threshold
        )

    async def knowledge_search(
        self, request: KnowledgeSearchRequest
    ) -> List[Chunk]:
        """Retrieve the service."""
        search_task = self.build_knowledge_search_dag(request=request)
        return await search_task.call(call_data={"query": request.query})

    def build_knowledge_search_dag(
            self, request: KnowledgeSearchRequest
    ):
        """Build a DAG for knowledge search."""
        with DAG("derisk_knowledge_search_dag") as _dag:
            # Create an input task
            input_task = InputOperator(SimpleCallDataInputSource())
            # Create a branch task to decide between fetching from cache or processing
            # with the model
            knowledge_operator = SpaceRetrieverOperator(
                knowledge_ids=request.knowledge_ids,
                rerank_top_k=request.top_k,
                similarity_top_k=request.single_knowledge_top_k,
                similarity_score_threshold=request.similarity_score_threshold,
                rerank_score_threshold=request.score_threshold,
                retrieve_mode=request.mode,
                llm_model=request.summary_model,
                rerank_model=request.rerank_model,
                system_app=self.system_app,
                task_name="知识库搜索",
            )
            worker_manager = self._system_app.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            llm_client = DefaultLLMClient(worker_manager=worker_manager)
            if request.enable_summary:
                summary_operator = SummaryOperator(
                    llm_client=llm_client,
                    model_name=request.summary_model,
                    task_name="生成总结",
                )
                input_task >> knowledge_operator >> summary_operator
                return summary_operator
            else:

                input_task >> knowledge_operator
        return knowledge_operator


    async def aget_space_context_by_space_id(
        self, knowledge_id
    ):
        return await blocking_func_to_async(
            self.system_app, self.get_space_context_by_space_id, knowledge_id
        )

    def get_space_context_by_space_id(self, knowledge_id):
        """get space contect
        Args:
           - space_id: space name
        """
        get_space_context_by_space_id_start_time = timeit.default_timer()

        spaces = self._dao.get_knowledge_space_by_knowledge_ids([knowledge_id])
        if len(spaces) != 1:
            raise Exception(
                f"have not found {knowledge_id} space or found more than one space called {knowledge_id}"
            )
        space = spaces[0]

        get_space_context_by_space_id_end_time = timeit.default_timer()
        cost_time = round(
            get_space_context_by_space_id_end_time
            - get_space_context_by_space_id_start_time,
            2,
        )
        logger.info(f"get_space_context_by_space_id cost time is {cost_time} seconds")

        if space.context is not None:
            return json.loads(spaces[0].context)
        return None

    async def acreate_knowledge_document(
        self, knowledge_id, request: KnowledgeDocumentRequest
    ):
        return await blocking_func_to_async(
            self.system_app, self.create_knowledge_document, knowledge_id, request
        )

    def create_knowledge_document(
        self, knowledge_id, request: KnowledgeDocumentRequest
    ):
        """create knowledge document
        Args:
           - request: KnowledgeDocumentRequest
        """
        start_time = timeit.default_timer()

        knowledge_spaces = self._dao.get_knowledge_space(
            KnowledgeSpaceEntity(knowledge_id=knowledge_id)
        )
        if len(knowledge_spaces) == 0:
            return None
        ks = knowledge_spaces[0]
        query = KnowledgeDocumentEntity(
            doc_name=request.doc_name, knowledge_id=knowledge_id
        )
        documents = self._document_dao.get_knowledge_documents(query)
        if len(documents) > 0:
            logger.info(f"request is {request}")
            raise Exception(f"document name:{request.doc_name} have already named")

        labels = request.labels
        questions = None
        if request.questions:
            questions = [
                remove_trailing_punctuation(question) for question in request.questions
            ]
            questions = json.dumps(questions, ensure_ascii=False)

        doc_id = str(uuid.uuid4())
        document = KnowledgeDocumentEntity(
            doc_id=doc_id,
            doc_name=request.doc_name,
            doc_type=request.doc_type,
            doc_token=request.doc_token,
            knowledge_id=knowledge_id,
            space=ks.name,
            chunk_size=0,
            status=SyncStatus.TODO.name,
            gmt_modified=datetime.now(),
            content=request.content,
            summary=labels,
            questions=questions,
            result="",
            chunk_params=json.dumps(
                request.chunk_parameters, cls=ChunkParametersEncoder
            ),
        )

        id = self._document_dao.create_knowledge_document(document)

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"create_knowledge_document cost time is {cost_time} seconds")

        if id is None:
            raise Exception(f"create document failed, {request.doc_name}")
        return doc_id

    def _get_vector_connector(self, knowledge_id):
        spaces = self._dao.get_knowledge_space_by_knowledge_ids([knowledge_id])
        if spaces is None:
            logger.error(f"get_vector_connector space is None, knowledge_id is {knowledge_id}")

            raise Exception(f"get_vector_connector space is None, knowledge_id is {knowledge_id}")
        space = spaces[0]

        storage_connector = self.storage_manager.get_storage_connector(
            index_name=knowledge_id, storage_type=space.storage_type
        )

        return storage_connector

    async def adocuments_by_doc_ids(self, doc_ids) -> List[KnowledgeDocumentEntity]:
        return await blocking_func_to_async(
            self.system_app, self._document_dao.documents_by_doc_ids, doc_ids
        )

    async def abatch_document_sync(
        self,
        knowledge_id,
        sync_requests: List[KnowledgeSyncRequest],
        space_context: dict,
        knowledge_id_store: Optional[dict] = None,
    ) -> List[int]:
        """batch sync knowledge document chunk into vector store
        Args:
            - space_id: Knowledge Space id
            - sync_requests: List[KnowledgeSyncRequest]
        Returns:
            - List[int]: document ids
        """
        start_time = timeit.default_timer()
        logger.info(f"abatch_document_sync start, 当前线程数：{threading.active_count()}")

        doc_ids = []

        for sync_request in sync_requests:
            docs = await self.adocuments_by_doc_ids([sync_request.doc_id])

            if len(docs) == 0:
                raise Exception(
                    f"there are document called, doc_id: {sync_request.doc_id}"
                )
            doc = docs[0]
            if (
                doc.status == SyncStatus.RUNNING.name
                or doc.status == SyncStatus.FINISHED.name
            ):
                raise Exception(
                    f" doc:{doc.doc_name} status is {doc.status}, can not sync"
                )
            chunk_parameters = sync_request.chunk_parameters
            # if chunk_parameters.chunk_strategy != ChunkStrategy.CHUNK_BY_SIZE.name:
            #     chunk_parameters.chunk_size = (
            #         CFG.KNOWLEDGE_CHUNK_SIZE
            #         if space_context is None
            #         else int(space_context["embedding"]["chunk_size"])
            #     )
            #     chunk_parameters.chunk_overlap = (
            #         CFG.KNOWLEDGE_CHUNK_OVERLAP
            #         if space_context is None
            #         else int(space_context["embedding"]["chunk_overlap"])
            #     )

            await self._sync_knowledge_document(
                knowledge_id, doc, chunk_parameters, knowledge_id_store
            )

            doc_ids.append(doc.doc_id)

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"new_batch_document_sync cost time is {cost_time} seconds")

        return doc_ids

    async def create_knowledge_document_and_sync(
        self,
        knowledge_id,
        request: KnowledgeDocumentRequest,
        space_context: dict,
        doc_id: str,
        knowledge_id_store: Optional[dict] = None,
    ):
        start_time = timeit.default_timer()
        logger.info(f"create_knowledge_document_and_sync start, 当前线程数：{threading.active_count()}")

        # build param
        knowledge_sync_request = KnowledgeSyncRequest(
            doc_id=doc_id, chunk_parameters=request.chunk_parameters
        )

        doc_ids = await self.abatch_document_sync(
            knowledge_id=knowledge_id,
            sync_requests=[knowledge_sync_request],
            space_context=space_context,
            knowledge_id_store=knowledge_id_store
        )
        logger.info(f"doc_id is {doc_id}， doc_ids is {doc_ids}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"new_create_knowledge_document_and_sync cost time is {cost_time} seconds"
        )

        return doc_id





    def get_host_ip(self):
        try:
            # Using host name to get the IP
            ip = socket.gethostbyname(socket.gethostname())
        except Exception as e:
            logger.warning(f"get_host_ip error {str(e)}")
            ip = "error: ip not found"
        return ip


    def get_default_chunk_parameters(self):
        return ChunkParameters(
                    chunk_strategy="Automatic", chunk_size=500, chunk_overlap=100, separator="\n"
                )

    def convert_to_chunk_parameters(self, chunk_parameters: Optional[str]=None):
        logger.info(f"convert_to_chunk_parameters chunk_parameters is {chunk_parameters}")

        try:
            if chunk_parameters:
                chunk_parameters_dict = json.loads(chunk_parameters)
                if chunk_parameters_dict["enable_merge"] is None:
                    chunk_parameters_dict["enable_merge"] = False
                if chunk_parameters_dict["chunk_strategy"] is None:
                    return self.get_default_chunk_parameters()
                chunk_parameters = ChunkParameters(**chunk_parameters_dict)
            else:
                chunk_parameters = self.get_default_chunk_parameters()
            return chunk_parameters
        except Exception as e:
            logger.error(f"convert_to_chunk_parameters failed, use default chunk param, error is {str(e)}")

            return self.get_default_chunk_parameters()






    def check_timeout(self, task: KnowledgeTaskEntity):
        start_time = task.start_time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        difference = abs(datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S") - datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S"))
        is_timeout = difference > timedelta(minutes=3)
        logger.info(f"check_timeout is timeout {is_timeout}")

        return is_timeout

    def check_retry_times(self, task: KnowledgeTaskEntity):
        retry_times = task.retry_times if task.retry_times else 0
        can_retry = retry_times < 2
        logger.info(f"check_retry_times can retry is {can_retry}")

        return can_retry


    async def retry_doc(self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None):
        logger.info(f"retry_doc start task, task id is {task.task_id}, knowledge_id_stores is {knowledge_id_stores}")

        await self.sync_document(
            requests=[KnowledgeSyncRequest(doc_id=task.doc_id)], knowledge_id_stores=knowledge_id_stores
        )

        return True


    async def check_doc_sync_status(self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None):
        logger.info(f"check_doc_sync_status, task id is {task.task_id}, doc_id is {task.doc_id}")

        doc_id = task.doc_id
        knowledge_id = task.knowledge_id
        doc = self.get_document_by_doc_id(knowledge_id=knowledge_id, doc_id=doc_id)
        if not doc or not doc.status:
            logger.error(f"check_doc_sync_status doc is None, {doc_id}, task id is {task.task_id}")

            task.status = TaskStatusType.FINISHED.name
            task.error_msg = "doc not found, task force failed"
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self._task_dao.update_knowledge_task_batch(tasks=[task])
            return True

        if doc.status == SyncStatus.FINISHED.name:
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.status = TaskStatusType.SUCCEED.name
        elif doc.status == SyncStatus.RUNNING.name or doc.status == SyncStatus.RETRYING.name:
            is_timeout = self.check_timeout(task=task)
            if is_timeout:
                task.status = TaskStatusType.FINISHED.name
                task.error_msg = "timeout failed"
                task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif doc.status == SyncStatus.FAILED.name or doc.status == SyncStatus.TODO.name:
            task.status = TaskStatusType.RUNNING.name
            retry = self.check_retry_times(task=task)
            if retry:
                task.retry_times += 1

                await self.retry_doc(task=task, knowledge_id_stores=knowledge_id_stores)
            else:
                task.status = TaskStatusType.FINISHED.name
                task.error_msg += "\n retry more than max times , task still failed"
                task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            task.status = TaskStatusType.FINISHED.name
            task.error_msg = "another condition happened , task still failed"
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task.gmt_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._task_dao.update_knowledge_task_batch(tasks=[task])
        return True

    def end_task(self, task: Optional[KnowledgeTaskEntity]=None, error_msg: Optional[str]=None):
        logger.info(f"end_task start, task id is {task.task_id}, task status is {task.status}")

        task.status = TaskStatusType.FINISHED.name
        task.error_msg = error_msg
        task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._task_dao.update_knowledge_task_batch(tasks=[task])
        return True

    async def retry_task(self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None):
        logger.info(f"retry_task start, task id is {task.task_id}， knowledge_id_stores is {knowledge_id_stores}")

        task.status = TaskStatusType.RUNNING.name
        retry = self.check_retry_times(task=task)
        if retry:
            task.retry_times = 0 if task.retry_times is None else task.retry_times + 1

            if task.doc_id:
                try:
                    await self.retry_doc(task=task, knowledge_id_stores=knowledge_id_stores)
                except Exception as e:
                    logger.error(f"retry_task error, {str(e)}")
                    task.error_msg = str(e)
            else:
                task.status = TaskStatusType.TODO.name
        else:
            task.status = TaskStatusType.FINISHED.name
            task.error_msg += "\n retry more than max times , task still failed"
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.host = self.get_host_ip()

        self._task_dao.update_knowledge_task_batch(tasks=[task])
        return True


    def init_knowledge_id_stores(self):
        try:
            knowledge_ids = self._task_dao.get_not_finished_knowledge_ids(
                ignore_status=[TaskStatusType.SUCCEED.name, TaskStatusType.FINISHED.name])
            for knowledge_id in knowledge_ids:
                if self._knowledge_id_stores is None or knowledge_id not in self._knowledge_id_stores.keys():
                    logger.info(f"auto_sync init knowledge id index store {knowledge_id}, self._knowledge_id_stores len is {len(self._knowledge_id_stores.keys())}")

                    self._knowledge_id_stores[knowledge_id] = self._get_vector_connector(knowledge_id=knowledge_id)
        except Exception as e:
            logger.error(f"init_knowledge_id_stores error, {str(e)}")

            raise Exception(f"init_knowledge_id_stores error, {str(e)}")

        return self._knowledge_id_stores


    async def auto_sync(self):
        # get task
        tasks = self._task_dao.get_knowledge_tasks_by_status(ignore_status=[TaskStatusType.SUCCEED.name, TaskStatusType.FINISHED.name], limit=1)
        if len(tasks) == 0:
            logger.info(f"no task to sync")

            return True
        task = tasks[0]

        # check host
        current_host = self.get_host_ip()
        if not task.host:
            logger.info(f"task host is None, update host : {current_host}")

            task.host = current_host
            self._task_dao.update_knowledge_task_batch(tasks=[task])
        elif current_host != task.host:
            logger.info(f"current host is {current_host}, task host is {task.host}, break")

            return True
        else:
            try:
                # init knowledge id index store
                knowledge_id_stores = self.init_knowledge_id_stores()

                if task.status == TaskStatusType.TODO.name:
                    # 未开始
                    await self.start_task(task=task, knowledge_id_stores=knowledge_id_stores)
                elif task.status == TaskStatusType.RUNNING.name:
                    # 已开始，有doc_id
                    await self.check_doc_sync_status(task=task)
                elif task.status == TaskStatusType.FAILED.name:
                    # 已开始，没有doc_id
                    await self.retry_task(task=task, knowledge_id_stores=knowledge_id_stores)
                else:
                    # 异常情况
                    self.end_task(task=task, error_msg="task status is abnormal, force task end")
            except Exception as e:
                logger.error(f"auto_sync error, {str(e)}")

                self.end_task(task=task, error_msg="auto sync error, force task end: " + str(e))
            return True

    def check_active_threads(self):
        if threading.active_count() > 400:
            logger.warning(f"当前线程数： {threading.active_count()}, stop sync task! ")

            return False

        return True


    async def run_periodic(self, interval: Optional[int] = 5):
        logger.info(f"run_periodic start, interval is {interval}")

        # 等待主程序运行成功再开启定时任务
        await asyncio.sleep(60)
        while True:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"run_periodic start {now}")

            try:
                # 线程数过高 服务降级
                if self.check_active_threads():
                    await self.auto_sync()
            except Exception as e:
                logger.warning("Periodic task failed", exc_info=e)
            await asyncio.sleep(interval)

    def _run_async_loop(self, interval: Optional[int]):
        # Run the asyncio loop in a separate OS thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.run_periodic(interval))
        finally:
            loop.close()

    def run_periodic_in_thread(self, interval: Optional[int] = 5):
        logger.info(f"run_periodic_in_thread start, interval is {interval}")

        # 新开线程启动异步任务
        thread = threading.Thread(target=self._run_async_loop, args=(interval,))
        # 守护线程，主线程结束子线程也结束
        thread.daemon = True
        thread.start()


    async def init_auto_sync(self,interval: Optional[int] = 5):
        logger.info(f"init_auto_sync start, interval is {interval}")

        asyncio.create_task(self.run_periodic(interval=interval))

        logger.info(f"init_auto_sync end, interval is {interval}")
        return True

    def update_knowledge_task(self, request: KnowledgeTaskRequest):
        logger.info(f"update_knowledge_task start, request is {request}")

        if request.task_id is None:
            raise Exception("task_id is None")

        # query task
        tasks = self._task_dao.get_knowledge_tasks(query=KnowledgeTaskEntity(task_id=request.task_id))
        if not tasks or len(tasks) != 1:
            raise Exception(f"task_id {request.task_id} can not be found")
        task = tasks[0]
        logger.info(f"update_knowledge_task task_id is {task.task_id}, task status is {task.status}")

        # update task
        task.status = request.status if request.status else TaskStatusType.FINISHED.name

        return self._task_dao.update_knowledge_task_batch(tasks=[task])


    def get_knowledge_task(self, knowledge_id: str):
        logger.info(f"get knowledge task knowledge_id is {knowledge_id}")

        if not knowledge_id:
            raise Exception("knowledge_id is None")

        # get all tasks
        tasks = self._task_dao.get_knowledge_tasks(query=KnowledgeTaskEntity(knowledge_id=knowledge_id), page=1, page_size=10000)
        logger.info(f"tasks len is {len(tasks)}")

        # build result
        total_tasks_count = len(tasks)
        succeed_tasks_count = 0
        running_tasks_count = 0
        todo_tasks_count = 0
        last_task_operator = ""

        if not tasks:
            spaces = self._dao.get_knowledge_space_by_knowledge_ids(knowledge_ids=[knowledge_id])
            if not spaces:
                raise Exception(f"knowledge_id {knowledge_id} can not be found")
            last_task_operator = spaces[0].owner
        else:
            for task in tasks:
                last_task_operator = task.owner
                if task.status == TaskStatusType.TODO.name:
                    todo_tasks_count += 1
                elif task.status in (TaskStatusType.SUCCEED.name, TaskStatusType.FINISHED.name):
                    succeed_tasks_count += 1
                else:
                    running_tasks_count += 1

        if total_tasks_count != (succeed_tasks_count + running_tasks_count + todo_tasks_count):
            logger.info(f"todo_tasks_count is {todo_tasks_count}, succeed_tasks_count is {succeed_tasks_count}, running_tasks_count is {running_tasks_count}, total_tasks_count {total_tasks_count}")

            raise Exception("tasks count is not equal to total tasks count")

        # return result
        return KnowledgeTaskResponse(
            knowledge_id=knowledge_id,
            total_tasks_count=total_tasks_count,
            succeed_tasks_count=succeed_tasks_count,
            running_tasks_count=running_tasks_count,
            todo_tasks_count=todo_tasks_count,
            last_task_operator=last_task_operator
        )


    def delete_knowledge_task(self, request: Optional[KnowledgeTaskRequest] = None):
        logger.info(f"delete knowledge task request is {request}")

        if request.knowledge_id is None:
            raise Exception("knowledge_id is None")
        if request.operator is None:
            raise Exception("operator is None")

        query = KnowledgeTaskEntity(knowledge_id=request.knowledge_id)
        if request.task_id:
            query.task_id = request.task_id
        if request.batch_id:
            query.batch_id = request.batch_id

        self._task_dao.delete_knowledge_tasks(query=query)

        return True





    async def create_single_file_knowledge(
        self, knowledge_id, request: DocumentServeRequest
    ):
        # generate doc_id
        id = self.create_document(request=request)
        doc = self._document_dao.get_knowledge_documents(
            query=KnowledgeDocumentEntity(id=id)
        )
        doc_id = doc.doc_id

        # async doc
        space_context = self.get_space_context_by_space_id(knowledge_id)
        sync_request = KnowledgeDocumentRequest(
            knowledge_id=knowledge_id,
            doc_name=request.doc_name,
            doc_type=request.doc_type,
        )
        asyncio.create_task(
            self.create_knowledge_document_and_sync(
                knowledge_id=knowledge_id,
                request=sync_request,
                space_context=space_context,
                doc_id=doc_id,
            )
        )
        logger.info(f"create_single_file_knowledge doc_id is {doc_id}")

        return doc_id

    async def create_single_document_knowledge(
        self, knowledge_id, request: KnowledgeDocumentRequest
    ):
        space_context = self.get_space_context_by_space_id(knowledge_id)

        # generate doc_id
        doc_id = await self.acreate_knowledge_document(
            knowledge_id=knowledge_id, request=request
        )

        # async
        asyncio.create_task(
            self.create_knowledge_document_and_sync(
                knowledge_id=knowledge_id,
                request=request,
                space_context=space_context,
                doc_id=doc_id,
            )
        )
        logger.info(f"create_single_document_knowledge doc_id is {doc_id}")

        return doc_id




    def update_doc_sync_info_dict(
        self, group_login: str, book_slug: str, import_doc_uuid_dict: dict, toc: dict
    ):
        logger.info(
            f"update_doc_sync_info_dict group_login: {group_login}, book_slug: {book_slug}"
        )

        doc_uuid = str(toc.get("uuid"))

        # init status dict
        doc_sync_info_dict = {
            "selected": False,
            "file_id": None,
            "file_status": None,
            "progress": None,
        }

        # update doc sync info
        if (len(import_doc_uuid_dict.keys()) > 0) and (
            doc_uuid in import_doc_uuid_dict.keys()
        ):
            logger.info(f"update_doc_sync_info_dict {doc_uuid} need to update")

            doc = import_doc_uuid_dict.get(doc_uuid)
            doc_sync_info_dict["selected"] = True
            doc_sync_info_dict["file_id"] = str(doc.doc_id)
            if doc.status == SyncStatus.FINISHED.name:
                doc_sync_info_dict["file_status"] = "ready"
                doc_sync_info_dict["progress"] = "100"
            elif doc.status == SyncStatus.RUNNING.name:
                doc_sync_info_dict["file_status"] = "running"
                doc_sync_info_dict["progress"] = "0"
            elif doc.status == SyncStatus.RETRYING.name:
                doc_sync_info_dict["file_status"] = "retrying"
                doc_sync_info_dict["progress"] = "0"
            else:
                doc_sync_info_dict["file_status"] = "error"
                doc_sync_info_dict["progress"] = "0"

        return doc_sync_info_dict

    async def adelete_document_by_doc_id(self, knowledge_id: str, doc_id: str, knowledge_id_store: Optional[Any] = None):
        return await blocking_func_to_async(
            self.system_app, self.delete_document_by_doc_id, knowledge_id, doc_id, knowledge_id_store
        )

    def get_document_by_doc_id(self, knowledge_id: str, doc_id: str):
        logger.info(f"get_document_by_doc_id {knowledge_id}")

        # check params
        if doc_id is None:
            raise Exception("doc_id is required")
        if knowledge_id is None:
            raise Exception("knowledge_id is required")

        # get document
        documents = self._document_dao.get_documents(
            query=KnowledgeDocumentEntity(doc_id=doc_id)
        )
        if documents is None or len(documents) == 0:
            logger.error(f"can not found document for {doc_id}")

            return None

        if len(documents) > 1:
            raise Exception(f"found more than one document! {doc_id}")

        return documents[0]

    def delete_document_by_doc_id(self, knowledge_id: str, doc_id: str, knowledge_id_store: Optional[Any] = None):
        logger.info(f"delete_document_by_doc_id {knowledge_id} {doc_id}")

        # get document
        document = self.get_document_by_doc_id(knowledge_id=knowledge_id, doc_id=doc_id)
        if document is None:
            return True

        # delete vector_id
        vector_ids = document.vector_ids
        if vector_ids:
            if knowledge_id_store is None:
                knowledge_id_store = self.get_or_update_knowledge_id_store(knowledge_id=knowledge_id)

            vector_store_connector = knowledge_id_store
            vector_store_connector.delete_by_ids(vector_ids)

        # delete chunks
        self._chunk_dao.raw_delete(doc_id=doc_id)
        # delete document
        return self._document_dao.raw_delete(KnowledgeDocumentEntity(doc_id=doc_id))

    async def delete_document_by_space_id(self, knowledge_id: str, knowledge_id_store: Optional[Any] = None):
        logger.info(f"delete_document_by_space_id {knowledge_id}, knowledge_id_store is {knowledge_id_store}")

        # get document
        document_query = KnowledgeDocumentEntity(knowledge_id=knowledge_id)
        documents = self._document_dao.get_documents(document_query)
        doc_ids = [doc.doc_id for doc in documents]

        tasks = [
            self.adelete_document_by_doc_id(knowledge_id=knowledge_id, doc_id=doc_id, knowledge_id_store=knowledge_id_store)
            for doc_id in doc_ids
        ]
        results = await asyncio.gather(*tasks)
        for result in results:
            logger.info(f"delete_document_by_doc_id {result}")

        return True

    def get_or_update_knowledge_id_store(self, knowledge_id: str):
        logger.info(f"get_or_update_knowledge_id_store {knowledge_id}, 当前线程数：{threading.active_count()}")

        if self._knowledge_id_stores is None or knowledge_id not in self._knowledge_id_stores.keys():
            logger.info(f"update knowledge_id_stores {self._knowledge_id_stores}, len is {len(self._knowledge_id_stores.keys())}")

            # update knowledge_id_stores
            self._knowledge_id_stores[knowledge_id] = self._get_vector_connector(knowledge_id=knowledge_id)

        knowledge_id_store = self._knowledge_id_stores[knowledge_id]

        return knowledge_id_store


    async def delete_documents(
        self, knowledge_id: Optional[str] = None, doc_id: Optional[str] = None
    ):
        logger.info(f"delete_documents knowledge_id is {knowledge_id} doc_id is {doc_id}, 当前线程数：{threading.active_count()}")

        knowledge_id_store = self.get_or_update_knowledge_id_store(knowledge_id=knowledge_id)
        if doc_id is None:
            await self.delete_document_by_space_id(knowledge_id=knowledge_id, knowledge_id_store=knowledge_id_store)
        else:
            await self.adelete_document_by_doc_id(
                knowledge_id=knowledge_id, doc_id=doc_id, knowledge_id_store=knowledge_id_store
            )
        logger.info(f"delete_documents end knowledge_id is {knowledge_id} doc_id is {doc_id}, 当前线程数：{threading.active_count()}")



    def get_failed_document_ids(self, request: KnowledgeDocumentRequest):
        """failed document sync"""
        query = KnowledgeDocumentEntity(knowledge_id=request.knowledge_id)
        filter_status = [
            SyncStatus.FAILED.name,
            SyncStatus.RETRYING.name,
            SyncStatus.TODO.name,
        ]

        documents = self._document_dao.get_documents(
            query=query, doc_ids=None, filter_status=filter_status
        )


        doc_ids = [
            doc.doc_id
            for doc in documents
        ]
        logger.info(f"get_failed_document_ids {doc_ids}")

        return doc_ids

    async def limited_retry_sync_single_doc(self, semaphore, doc_id: str):
        async with semaphore:
            return await self.sync_document(
                requests=[KnowledgeSyncRequest(doc_id=doc_id)]
            )

    async def retry_knowledge_space(
        self,
        knowledge_id: str,
        request: KnowledgeDocumentRequest,
        max_concurrent_tasks: Optional[int] = 10,
    ):
        logger.info(f"retry_knowledge_space {knowledge_id} {request}")

        # get failed doc
        if request.doc_ids is None:
            failed_doc_ids = self.get_failed_document_ids(request=request)
        else:
            failed_doc_ids = request.doc_ids
        logger.info(f"failed_doc_ids is {failed_doc_ids}")

        # update status -> retrying
        self._document_dao.update_knowledge_document_by_doc_ids(
            doc_ids=failed_doc_ids, status=SyncStatus.RETRYING.name
        )


        semaphore = asyncio.Semaphore(max_concurrent_tasks)

        # sync retry
        tasks = [
            asyncio.create_task(
                self.limited_retry_sync_single_doc(semaphore=semaphore, doc_id=doc_id)
            )
            for doc_id in failed_doc_ids
        ]

        logger.info(f"retry_knowledge_space tasks len is {len(tasks)}")

        return True


    def remove_html_tags(self, text: str):
        try:
            cleaned_text = re.sub(r"<[^>]+>", "", text)
            cleaned_text = cleaned_text.strip()
            return cleaned_text
        except Exception as e:
            logger.error(f"remove_html_tags error: text is {text}, {str(e)}")

            return ""


    def get_header_split(self, doc_id: str):
        # check is_header_split
        docs = self._document_dao.get_documents(query=KnowledgeDocumentEntity(doc_id=doc_id))
        if docs is None or len(docs) != 1:
            logger.error(f"get_header_split doc is None or more than one {doc_id}")

            raise Exception("get_header_split doc error")
        doc = docs[0]
        chunk_params = json.loads(doc.chunk_params)
        is_header_split = False
        if chunk_params:
            chunk_strategy = chunk_params.get("chunk_strategy")
            if chunk_strategy and (
                chunk_strategy == ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER.name or chunk_strategy == "Automatic"):
                logger.info(f"get_chunks chunk_strategy is {chunk_strategy}")

                is_header_split = True
        logger.info(f"get_header_split is_header_split is {is_header_split}")

        return is_header_split


    def get_chunks_by_outline(self, knowledge_id: str, doc_id: str, outline: str):
        # get filter chunks
        chunks = self.get_chunks(request=ChunkEditRequest(doc_id=doc_id, knowledge_id=knowledge_id, first_level_header=outline))

        chunk_ids = [str(chunk.chunk_id) for chunk in chunks]
        logger.info(f"get_chunks_by_outline chunk_ids is {len(chunk_ids)}")

        return chunk_ids


    def get_all_chunk_strategies(self):
        chunk_strategy = []
        for strategy in ChunkStrategy:
            chunk_detail = StrategyDetail(
                strategy=strategy.name,
                name=strategy.value[4],
                description=strategy.value[3],
                parameters=[
                    ParamDetail(
                        param_name=param.get("param_name"),
                        param_type=param.get("param_type"),
                        default_value=param.get("default_value"),
                        description=param.get("description"),
                    )
                    for param in strategy.value[1]
                ],
                suffix=[
                    knowledge.document_type().value
                    for knowledge in KnowledgeFactory.subclasses()
                    if strategy in knowledge.support_chunk_strategy()
                    and knowledge.document_type() is not None
                ],
                type=list(
                    set(
                        [
                            knowledge.type().value
                            for knowledge in KnowledgeFactory.subclasses()
                            if strategy in knowledge.support_chunk_strategy()
                        ]
                    )
                ),
            )
            chunk_strategy.append(chunk_detail)
        logger.info(f"get_all_chunk_strategies len is {len(chunk_strategy)}")

        return chunk_strategy

    def get_chunk_strategies(
        self, suffix: Optional[str] = None, type: Optional[str] = None
    ):
        logger.info(f"get_chunk_strategies {suffix} {type}")

        # get all strategies
        chunk_strategies = self.get_all_chunk_strategies()

        # filter by suffix and type
        if suffix:
            chunk_strategies = [
                strategy for strategy in chunk_strategies if suffix in strategy.suffix
            ]
        if type:
            chunk_strategies = [
                strategy for strategy in chunk_strategies if type in strategy.type
            ]
        logger.info(f"chunk_strategies len is {len(chunk_strategies)}")

        return chunk_strategies

    def check_knowledge_search_request_params(self, request: KnowledgeSearchRequest):
        if not request:
            raise Exception("knowledge_search_request is None")
        if len(request.knowledge_ids) == 0:
            raise Exception("knowledge_ids is None")
        if not request.query:
            raise Exception("query is None")
        if request.top_k is not None and (
            int(request.top_k) <= 0 or int(request.top_k) > 100
        ):
            raise Exception("top_k is not in [1, 100]")
        if request.similarity_score_threshold is not None and (
            float(request.similarity_score_threshold) < 0
            or float(request.similarity_score_threshold) > 1
        ):
            raise Exception("similarity_score_threshold is not in [0, 1]")
        # if request.score_threshold is not None and (float(request.score_threshold) < 0 or float(request.score_threshold) > 1):
        #     raise Exception("score_threshold is not in [0, 1]")

    async def afilter_space_id_by_tags(
        self, knowledge_ids: List[str], request: KnowledgeSearchRequest
    ):
        logger.info(
            f"afilter_space_id_by_tags space id is {knowledge_ids}, query is {request.query}"
        )
        start_time = timeit.default_timer()

        # get spaces
        knowledges = self._dao.get_knowledge_space_by_knowledge_ids(knowledge_ids)
        tags = [knowledge.name for knowledge in knowledges]
        extract_tags = []
        if request.enable_tag_filter and tags:
            tag_extractor = TagsExtractor(
                llm_client=self.llm_client, model_name=request.summary_model, tags=tags
            )
            extract_tags = await tag_extractor.extract(request.query)

        if len(extract_tags) == 0:
            logger.error(
                "space id is {space_ids} , query is {request.query}, extract_tags is empty"
            )
        else:
            space_id_tag_dict = {
                str(knowledge.knowledge_id): knowledge.name for knowledge in knowledges
            }
            cleaned_tags = [tag.strip("'\"") for tag in extract_tags]
            logger.info(
                f"space id is {knowledge_ids} , query is {request.query}, extract_tags is {extract_tags}, cleaned_tags is {cleaned_tags}, space_id_tag_dict is {space_id_tag_dict}"
            )

            filter_space_ids = [
                space_id
                for space_id in knowledge_ids
                if space_id_tag_dict.get(space_id) in cleaned_tags
            ]
            if len(filter_space_ids) != 0:
                logger.info(
                    f"filter success query is {request.query}, extract_tags is {cleaned_tags}"
                )

                space_ids = filter_space_ids
        logger.info(f"filter space_ids is {knowledge_ids}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"afilter_space_id_by_tags cost time is {cost_time} seconds")

        return space_ids

    def check_metadata_filters(self, metadata_filters: MetadataFilters = None):
        condition = metadata_filters.condition
        filters = metadata_filters.filters

        if not condition:
            raise Exception("condition is None")

        if not filters:
            raise Exception("filters is None")

    def get_all_meta_values(self, knowledge_ids: List[str]) -> dict:
        # get all chunks
        all_chunk_meta_info = self._chunk_dao.get_all_chunk_meta_info_by_knowledge_ids(
            knowledge_ids=knowledge_ids
        )

        # get key values dict
        key_values_dict = {}
        for meta_info in all_chunk_meta_info:
            meta_info_dict = json.loads(meta_info[0])
            for key, value in meta_info_dict.items():
                if not value:
                    continue
                if key not in key_values_dict.keys():
                    key_values_dict[key] = set()
                key_values_dict[key].add(value)
        logger.info(f"key_values_dict len is {len(key_values_dict.keys())}")

        return key_values_dict

    async def aget_metadata_filter(self, request: KnowledgeSearchRequest = None):
        start_time = timeit.default_timer()

        knowledge_ids = request.knowledge_ids
        metadata_filters = request.metadata_filters

        # check param
        self.check_metadata_filters(metadata_filters=metadata_filters)

        # get meta data
        filters = metadata_filters.filters
        update_filters = []

        # get all metadata by space
        for filter in filters:
            filter_key = filter.key
            filter_value = filter.value
            if not filter_value:
                key_values_dict = self.get_all_meta_values(knowledge_ids=knowledge_ids)
                values = list(key_values_dict.get(filter_key))

                # get filter metadata by llm
                tag_extractor = TagsExtractor(
                    llm_client=self.llm_client,
                    model_name=request.summary_model,
                    tags=values,
                )
                filter_value = await tag_extractor.extract(request.query)
                filter_value = [value.strip("'\"") for value in filter_value]
                filter_value = [value for value in filter_value if value]
                logger.info(f"extract filter_value is {filter_value}")

            if not filter_value:
                logger.info("filter_value is empty, need to find all chunks")

                continue

            # build filter condition
            for value in filter_value:
                new_filter = filter.copy()
                new_filter.value = value
                update_filters.append(new_filter)

        metadata_filters.filters = update_filters

        if not update_filters:
            metadata_filters = None

        if len(update_filters) > 1:
            metadata_filters.condition = FilterCondition.OR

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"aget_metadata_filter cost time is {cost_time} seconds")

        return metadata_filters

    async def acreate_knowledge_space_retriever(
        self,
        knowledge_id: str,
        top_k: int,
        retrieve_mode: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        return await blocking_func_to_async(
            self.system_app,
            self.create_knowledge_space_retriever,
            knowledge_id,
            top_k,
            retrieve_mode,
            llm_model,
        )

    def create_knowledge_space_retriever(
        self,
        knowledge_id: str,
        top_k: int,
        retrieve_mode: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        return KnowledgeSpaceRetriever(
            space_id=knowledge_id,
            embedding_model=self._serve_config.embedding_model,
            top_k=top_k,
            retrieve_mode=retrieve_mode,
            llm_model=llm_model,
            system_app=self._system_app,
        )

    async def aget_all_knowledge_space_retriever(
        self,
        knowledge_ids: List[str],
        top_k: int,
        retrieve_mode: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> dict[str, "KnowledgeSpaceRetriever"]:
        logger.info(
            f"aget_all_knowledge_space_retriever knowledge_ids is {knowledge_ids}, top_k is {top_k}"
        )
        start_time = timeit.default_timer()

        tasks = [
            self.acreate_knowledge_space_retriever(
                knowledge_id, top_k, retrieve_mode, llm_model
            )
            for knowledge_id in knowledge_ids
        ]

        knowledge_space_retrievers = await asyncio.gather(*tasks)
        space_id_knowledge_space_retriever_dict = {
            knowledge_id: knowledge_space_retrievers[i]
            for i, knowledge_id in enumerate(knowledge_ids)
        }
        logger.info(
            f"space_id_knowledge_space_retriever_dict is {len(space_id_knowledge_space_retriever_dict)}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"aget_all_knowledge_space_retriever cost time is {cost_time} seconds"
        )

        return space_id_knowledge_space_retriever_dict

    async def aget_chunks_by_similarity(
        self,
        knowledge_id: str = None,
        request: KnowledgeSearchRequest = None,
        knowledge_space_retriever: KnowledgeSpaceRetriever = None,
    ):
        logger.info(f"aretrieve_with_scores space id is {knowledge_id}")
        start_time = timeit.default_timer()

        question = request.query
        top_k = request.single_knowledge_top_k
        similarity_score_threshold = (
            request.similarity_score_threshold
            if request.similarity_score_threshold is not None
            else 0.0
        )
        logger.info(
            f"search_single_knowledge_space top_k is {top_k}, similarity_score_threshold is {similarity_score_threshold}"
        )

        chunks = await knowledge_space_retriever.aretrieve_with_scores(
            question, similarity_score_threshold, request.metadata_filters
        )

        chunks = [chunk for chunk in chunks if chunk.content is not None]
        logger.info(
            f"aretrieve_with_scores chunks len is {len(chunks)}, space id is {knowledge_id}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"knowledge_space_retriever.aretrieve_with_scores cost time is {cost_time} seconds, space id is {knowledge_id}"
        )

        return chunks

    def get_chunk_id_dict_by_space_id(self, knowledge_id: str):
        logger.info(f"get chunk id dict knowledge_id: {knowledge_id}")
        start_time = timeit.default_timer()

        chunks = self._chunk_dao.get_chunks_by_knowledge_id(
            knowledge_id=knowledge_id, status="FINISHED"
        )
        chunk_id_dict = {chunk.vector_id: chunk for chunk in chunks}
        logger.info(f"chunk id dict: {len(chunk_id_dict.keys())}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"get_chunk_id_dict_by_space_id cost time is {cost_time} seconds, space id is {knowledge_id}"
        )

        return chunk_id_dict

    async def aget_chunk_id_dict_by_space_id(self, knowledge_id: str):
        return await blocking_func_to_async(
            self.system_app, self.get_chunk_id_dict_by_space_id, knowledge_id
        )

    def get_doc_id_dict(self, knowledge_id: str):
        logger.info(f"get doc id dict knowledge id is: {knowledge_id}")
        start_time = timeit.default_timer()

        documents = self._document_dao.get_knowledge_documents(
            query=KnowledgeDocumentEntity(knowledge_id=knowledge_id, status="FINISHED"),
            page=1,
            page_size=1000,
        )
        doc_id_dict = {doc.doc_id: doc for doc in documents}
        logger.info(f"doc id dict: {len(doc_id_dict.keys())}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"get_doc_id_dict cost time is {cost_time} seconds, space id is {knowledge_id}"
        )

        return doc_id_dict

    async def aget_doc_id_dict(self, knowledge_id: str):
        return await blocking_func_to_async(
            self.system_app, self.get_doc_id_dict, knowledge_id
        )

    def build_document_search_response(
        self, knowledge_id: str, chunk: Chunk, chunk_id_dict: dict, doc_id_dict: dict
    ):
        if "prop_field" in chunk.metadata.keys():
            meta_data = chunk.metadata.get("prop_field")
        elif "metadata" in chunk.metadata.keys():
            meta_data = chunk.metadata.get("metadata")
        else:
            meta_data = chunk.metadata

        chunk_id = str(chunk.chunk_id)
        content = chunk.content
        score = float(chunk.score)
        knowledge_id = str(knowledge_id)
        # todo--向量中存储doc_id
        doc_id = ""
        create_time = str(meta_data.get("created_at")) if meta_data is not None else ""
        modified_time = (
            str(meta_data.get("updated_at")) if meta_data is not None else ""
        )

        doc_type = KnowledgeType.TEXT
        doc_name = meta_data.get("title") if meta_data is not None else ""

        # update doc_id
        if chunk_id in chunk_id_dict.keys():
            db_chunk = chunk_id_dict.get(chunk_id)
            doc_id = str(db_chunk.doc_id) if db_chunk is not None else ""

        return DocumentSearchResponse(
            content=content,
            score=score,
            knowledge_id=knowledge_id,
            doc_id=doc_id,
            chunk_id=chunk.metadata.get("chunk_id"),
            create_time=create_time,
            modified_time=modified_time,
            doc_type=doc_type,
            doc_name=doc_name,
        )

    async def asearch_single_knowledge_space(
        self,
        knowledge_id: str = None,
        request: KnowledgeSearchRequest = None,
        space_id_knowledge_space_retriever_dict: dict = None,
    ) -> List[DocumentSearchResponse]:
        logger.info(
            f"search_single_knowledge_space space id is {knowledge_id}, request is:{request}"
        )
        start_time = timeit.default_timer()

        knowledge_space_retriever = space_id_knowledge_space_retriever_dict.get(
            knowledge_id
        )

        chunks, chunk_id_dict, doc_id_dict = await asyncio.gather(
            self.aget_chunks_by_similarity(
                knowledge_id=knowledge_id,
                request=request,
                knowledge_space_retriever=knowledge_space_retriever,
            ),
            self.aget_chunk_id_dict_by_space_id(knowledge_id=knowledge_id),
            self.aget_doc_id_dict(knowledge_id=knowledge_id),
        )

        document_response_list = []
        for chunk in chunks:
            document_search_response = self.build_document_search_response(
                knowledge_id=knowledge_id,
                chunk=chunk,
                chunk_id_dict=chunk_id_dict,
                doc_id_dict=doc_id_dict,
            )
            document_response_list.append(document_search_response)
        logger.info(
            f"search_single_knowledge_space res len is {len(document_response_list)}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"search_single_knowledge_space cost time is {cost_time} seconds, knowledge id is {knowledge_id}"
        )

        return document_response_list

    async def apost_filters(
        self,
        document_response_list: List[DocumentResponse],
        rerank_top_k: int,
        question: str,
    ):
        logger.info(
            f"apost_filters start chunks len is {len(document_response_list)}, rerank_top_k is {rerank_top_k}, question is {question}"
        )
        start_time = timeit.default_timer()

        # record old chunk
        chunk_id_document_response_dict = {
            document_response.chunk_id: document_response
            for document_response in document_response_list
        }

        # convert document_response to chunk
        chunks = []
        for document_response in document_response_list:
            content = document_response.content
            score = document_response.score
            chunk_id = document_response.chunk_id
            chunks.append(Chunk(content=content, score=score, chunk_id=chunk_id))

        # rerank chunks
        post_reranks = [RetrieverNameRanker(topk=int(rerank_top_k))]

        # add rerank model
        rerank_embeddings = RerankEmbeddingFactory.get_instance(
            self.system_app
        ).create()
        reranker = RerankEmbeddingsRanker(rerank_embeddings, topk=int(rerank_top_k))
        post_reranks.append(reranker)

        rerank_chunks = []
        for filter in post_reranks:
            logger.info(f"current post filter is {filter}")
            try:
                rerank_chunks = await filter.arank(chunks, question)
            except Exception as e:
                logger.error(f"{filter} rerank error: {str(e)}")

            if rerank_chunks and len(rerank_chunks) > 0:
                logger.info(f"find rerank chunks, filter is {filter}")

                break
        logger.info(f"rerank chunks len is {len(rerank_chunks)}")

        if len(rerank_chunks) == 0:
            logger.info(
                f"rerank chunks is empty, use old chunks chunks len is {len(chunks)}"
            )

            rerank_chunks = chunks

        # convert chunk to document_response
        rerank_document_response_list = []
        for chunk in rerank_chunks:
            chunk_id = chunk.chunk_id
            chunk_score = chunk.score

            old_document_response = chunk_id_document_response_dict.get(chunk_id)
            old_document_response.score = chunk_score
            rerank_document_response_list.append(old_document_response)

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"apost_filters cost time is {cost_time} seconds")

        return rerank_document_response_list

    def distinct_and_sort(
        self,
        document_response_list: [DocumentResponse],
        top_k: int = 5,
        score_threshold: float = 0.5,
    ):
        logger.info(
            f"distinct_and_sort document_response_list len is {len(document_response_list)} top_k is {top_k}"
        )
        start_time = timeit.default_timer()

        # distinct
        document_response_dict = {}
        for response in document_response_list:
            chunk_id = response.chunk_id
            if chunk_id not in document_response_dict.keys():
                document_response_dict[chunk_id] = response
        distinct_document_response_list = list(document_response_dict.values())

        # sort
        distinct_document_response_list = sorted(
            distinct_document_response_list, key=lambda x: x.score, reverse=True
        )

        # filter with score
        distinct_document_response_list = [
            response
            for response in distinct_document_response_list
            if response.score > score_threshold
        ]

        # top_k
        distinct_document_response_list = distinct_document_response_list[:top_k]
        logger.info(
            f"distinct_and_sort document_response_list len is {len(distinct_document_response_list)}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"distinct_and_sort cost time is {cost_time} seconds")

        return distinct_document_response_list

    async def asearch_knowledge(
        self, request: KnowledgeSearchRequest
    ) -> KnowledgeSearchResponse:
        logger.info(f"search_knowledge request is:{request}")
        start_time = timeit.default_timer()

        # check params
        self.check_knowledge_search_request_params(request=request)

        # distinct knowledge_id
        knowledge_ids = request.knowledge_ids
        knowledge_id_dict = {knowledge_id: True for knowledge_id in knowledge_ids}
        knowledge_ids = list(knowledge_id_dict.keys())

        # filter knowledge_id by tags
        if request.enable_tag_filter and len(knowledge_ids) > 1:
            knowledge_ids = await self.afilter_space_id_by_tags(
                knowledge_ids=knowledge_ids, request=request
            )
        logger.info(
            f"search_knowledge knowledge_ids len is {len(knowledge_ids)} knowledge_id_dict len is {len(knowledge_id_dict)}"
        )

        metadata_filters = None
        if request.metadata_filters:
            metadata_filters = await self.aget_metadata_filter(request=request)
        request.metadata_filters = metadata_filters

        # get all knowledge_space_retriever
        space_id_knowledge_space_retriever_dict = (
            await self.aget_all_knowledge_space_retriever(
                knowledge_ids=knowledge_ids,
                top_k=request.single_knowledge_top_k,
                llm_model=request.summary_model,
            )
        )

        tasks = [
            self.asearch_single_knowledge_space(
                knowledge_id=knowledge_id,
                request=request,
                space_id_knowledge_space_retriever_dict=space_id_knowledge_space_retriever_dict,
            )
            for knowledge_id in knowledge_ids
        ]
        results = await asyncio.gather(*tasks)
        document_response_list = []
        for result in results:
            document_response_list.extend(result)

        # post_filter
        rerank_top_k = int(request.top_k)
        document_response_list = await self.apost_filters(
            document_response_list=document_response_list,
            rerank_top_k=rerank_top_k,
            question=request.query,
        )

        # filter with distinct, score, top_k
        document_response_list = self.distinct_and_sort(
            document_response_list=document_response_list,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )

        knowledge_search_response = KnowledgeSearchResponse(
            document_response_list=document_response_list
        )

        if request.enable_summary:
            logger.info(f"enable summary {request.query}")

            worker_manager = self._system_app.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            llm_client = DefaultLLMClient(worker_manager=worker_manager)
            summary_extractor = SummaryExtractor(
                llm_client=llm_client,
                model_name=request.summary_model,
                prompt=request.summary_prompt,
            )
            contents = "\n".join(
                [document_res.content for document_res in document_response_list]
            )
            summary = await summary_extractor.extract(text=contents)
            knowledge_search_response.summary_content = summary
        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"search_knowledge cost time is {cost_time} seconds")

        return knowledge_search_response


    def get_chunks(self, request: ChunkEditRequest):
        logger.info(f"get_chunks request is:{request}")

        if request.knowledge_id is None:
            raise Exception("knowledge_id is required")

        if request.doc_id is None:
            raise Exception("doc_id is required")

        # get chunks
        chunk_responses = self._chunk_dao.get_list({
                "knowledge_id": request.knowledge_id,
                "doc_id": request.doc_id
            })

        # check is_header_split
        is_header_split = self.get_header_split(doc_id=request.doc_id)

        # filter chunks
        filter_chunks = []
        if request.first_level_header:
            if is_header_split is False:
                logger.info("is_header_split is False, return None")

                return None
            for chunk in chunk_responses:
                meta_data = json.loads(chunk.meta_data)
                header = meta_data.get("Header1")
                if header is None:
                    header = meta_data.get("Header2")
                if header is not None and request.first_level_header in header:
                    logger.info(f"get chunks first_level_header success: {header}, {request.first_level_header}")

                    filter_chunks.append(chunk)
            chunk_responses = filter_chunks
        logger.info(f"chunks size is {len(chunk_responses)}, filter size is {len(filter_chunks)}, is_header_split is {is_header_split}")

        return chunk_responses

    def get_new_vector_id(
        self,
        old_vector_id: Optional[str] = None,
        chunk: Optional[DocumentChunkEntity] = None,
        vector_store_connector: Optional[Any] = None,
    ):
        logger.info(f"embedding_and_update_vector {old_vector_id}, {chunk}")

        # 方法1: 直接upsert 2.2.x 不支持
        # 方法2: 先delete, 再insert, 要确保插入成功
        generate_vector_ids = []
        try:
            if chunk is None:
                raise Exception("chunk is None")

            new_chunk = Chunk(
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                metadata=json.loads(chunk.meta_data),
                vector_id=chunk.vector_id,
            )

            delete_and_insert_times = 0
            delete_and_insert_flag = False
            while delete_and_insert_times < 3 and not delete_and_insert_flag:
                if vector_store_connector.delete_by_chunk_ids(chunk_ids=chunk.chunk_id):
                    generate_vector_ids = vector_store_connector.load_document(
                        [new_chunk]
                    )
                    if generate_vector_ids is not None:
                        delete_and_insert_flag = True
                        logger.info(
                            f"polygon store generate new vector_id is {generate_vector_ids}"
                        )

                    delete_and_insert_times += 1

            if len(generate_vector_ids) == 0:
                logger.error(
                    f"polygon store generate new vector_id is {generate_vector_ids}"
                )

                raise Exception("chunk edit with polygon store delete and insert error")

            return generate_vector_ids[0]
        except Exception as e:
            logger.error(f"polygon store delete_and_insert error {e}")

            raise Exception(
                f"chunk edit with polygon store delete and insert error {str(e)}"
            )

    def update_chunk_content(
        self, entity: DocumentChunkEntity, request: ChunkEditRequest
    ):
        doc = self._document_dao.get_knowledge_documents(
            query=KnowledgeDocumentEntity(doc_id=entity.doc_id)
        )[0]
        if doc.vector_ids is None:
            raise Exception("vector_ids is required")
        vector_ids = doc.vector_ids.split(",")
        logger.info(f"vector_ids size {len(vector_ids)}")

        vector_store_connector = self.get_or_update_knowledge_id_store(knowledge_id=doc.knowledge_id)
        entity.content = request.content

        generate_vector_id_start_time = timeit.default_timer()
        chunk_vector_id = entity.vector_id
        new_vector_id = self.get_new_vector_id(
            old_vector_id=chunk_vector_id,
            chunk=entity,
            vector_store_connector=vector_store_connector,
        )
        generate_vector_id_end_time = timeit.default_timer()
        generate_vector_id_cost_time = round(
            generate_vector_id_end_time - generate_vector_id_start_time, 2
        )
        logger.info(
            f"generate vector id cost time is {generate_vector_id_cost_time} seconds"
        )

        old_vector_ids = doc.vector_ids.split(",")
        new_vector_ids = [
            vec_id for vec_id in old_vector_ids if vec_id != chunk_vector_id
        ]
        new_vector_ids.append(new_vector_id)
        logger.info(
            f"old_vector_id is {chunk_vector_id}, new_vector_id is {new_vector_id}"
        )

        new_vector_ids = ",".join(map(str, new_vector_ids))
        doc.vector_ids = new_vector_ids
        self._document_dao.update_knowledge_document(doc)

        # 目前保存的是milvus中的vector_id，后续可能是graph_id
        entity.chunk_id = str(uuid.uuid4())
        entity.vector_id = str(new_vector_id)

        return entity

    def edit_chunk(self, request: ChunkEditRequest):
        """update knowledge chunk

        Args:
            - request: ChunkEditRequest
        """
        if not request.chunk_id:
            raise Exception("chunk_id is required")
        if not request.knowledge_id:
            raise Exception("knowledge_id is required")
        if not request.doc_id:
            raise Exception("doc_id is required")

        entities = self._chunk_dao.get_document_chunks(
            query=DocumentChunkEntity(chunk_id=request.chunk_id)
        )
        if not entities:
            raise Exception(f"chunk {request.chunk_id} is not existed")
        entity = entities[0]

        if request.meta_info is not None:
            entity.meta_info = request.meta_info
        if request.tags is not None:
            entity.tags = json.dumps(request.tags, ensure_ascii=False)

        if request.questions is not None:
            # 添加问题
            if len(request.questions) == 0:
                request.questions = ""
            questions = [
                remove_trailing_punctuation(question) for question in request.questions
            ]
            entity.questions = json.dumps(questions, ensure_ascii=False)

        if request.content is None or request.content == entity.content:
            logger.info(f"content is null or content is not modify: {entity.content}")
        else:
            logger.info(f"content is modify: {entity.content}")

            entity = self.update_chunk_content(entity=entity, request=request)

        self._chunk_dao.update_chunk(entity)
        logger.info(f"update chunk success {entity.chunk_id}")

        return True

    def get_rag_flows(self, request: QUERY_SPEC):
        """Get rag flows"""
        flow_res = []
        seen_span_ids = set()
        for flow in self._rag_span_dao.get_list(request):
            if not flow.input:
                continue
            if flow.span_id in seen_span_ids:
                continue
            seen_span_ids.add(flow.span_id)
            flow_res.append(
                {
                    "node_name": flow.node_name,
                    "node_type": flow.node_type,
                    "input": flow.input,
                    "output": flow.output,
                    "start_time": flow.start_time,
                    "end_time": flow.end_time,
                }
            )
        return flow_res

    def get_rag_flow(self, request: QUERY_SPEC):
        """Get rag flow"""
        return self._rag_span_dao.get_one(request)
