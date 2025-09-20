import asyncio
import concurrent
import json
import logging
import os
import re
import socket
import threading
import timeit
import uuid
from asyncio import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, cast, Any, Dict

from fastapi import HTTPException

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
from derisk.rag.retriever import RetrieverStrategy
from derisk.rag.retriever.rerank import RerankEmbeddingsRanker, RetrieverNameRanker
from derisk.rag.transformer.summary_extractor import SummaryExtractor
from derisk.storage.base import IndexStoreBase
from derisk.storage.metadata import BaseDao
from derisk.storage.metadata._base_dao import QUERY_SPEC
from derisk.storage.vector_store.filters import FilterCondition, MetadataFilters, \
    MetadataFilter
from derisk.util.pagination_utils import PaginationResult
from derisk.util.string_utils import remove_trailing_punctuation
from derisk.util.tracer import root_tracer, trace
from derisk_app.knowledge.request.request import BusinessFieldType
from derisk_app.knowledge.request.response import DocumentResponse
from derisk_ext.rag.chunk_manager import ChunkParameters, ChunkParametersEncoder
from derisk_ext.rag.knowledge import KnowledgeFactory
from derisk_ext.rag.transformer.image_extractor import ImageExtractor
from derisk_ext.rag.yuque_index.ant_yuque_loader import AntYuqueLoader
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
    YuqueRequest,
    KnowledgeDocumentRequest,
    YuqueBookDetail,
    YuqueDirDetail,
    YuqueDocDetail,
    YuqueGroupBook,
    KnowledgeSearchResponse,
    DocumentSearchResponse,
    StrategyDetail,
    ParamDetail,
    ChunkEditRequest, YuqueOutlines, OutlineChunk, KnowledgeTaskRequest, KnowledgeTaskResponse, SettingsRequest,
    TextBook, CreateDocRequest, UpdateTocRequest, CreateBookRequest,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..domain.index import DomainGeneralIndex
from ..models.chunk_db import DocumentChunkDao, DocumentChunkEntity
from ..models.document_db import (
    KnowledgeDocumentDao,
    KnowledgeDocumentEntity,
)
from ..models.knowledge_refresh_record_db import (
    KnowledgeRefreshRecordDao,
    KnowledgeRefreshRecordEntity,
)
from ..models.knowledge_space_graph_relation_db import KnowledgeSpaceGraphRelationEntity, KnowledgeSpaceGraphRelationDao
from ..models.knowledge_task_db import KnowledgeTaskEntity, KnowledgeTaskDao
from ..models.models import KnowledgeSpaceDao, KnowledgeSpaceEntity
from ..models.rag_span_db import RagFlowSpanDao
from ..models.settings_db import SettingsDao, SettingsEntity
from ..models.yuque_db import KnowledgeYuqueEntity, KnowledgeYuqueDao
from ..operators.knowledge_space import SpaceRetrieverOperator
from ..operators.split_query import SplitQueryOperator
from ..operators.summary import SummaryOperator
from ..retriever.knowledge_space import KnowledgeSpaceRetriever
from ..storage_manager import StorageManager
from ..transformer.tag_extractor import TagsExtractor
from ...agent.db.gpts_app import GptsAppDao

logger = logging.getLogger(__name__)


BASE_YUQUE_URL = "https://yuque.com"
REFRESH_OPERATOR = "derisk"
DEFAULT_EMPTY_HOST = "empty_host"
REFRESH_HOUR = "REFRESH_HOUR"
DEFAULT_CHUNK_STRATEGY = "Automatic"
DEFAULT_MARKDOWN_STRATEGY = "CHUNK_BY_MARKDOWN_HEADER"


class SyncStatus(Enum):
    TODO = "待处理"
    FAILED = "失败"
    RUNNING = "处理中"
    FINISHED = "可用"
    RETRYING = "重试中"
    EXTRACTING = "提取中"


class KnowledgeAccessLevel(Enum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


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
        refresh_record_dao: Optional[KnowledgeRefreshRecordDao] = None,
        graph_relation_dao: Optional[KnowledgeSpaceGraphRelationDao] = None,
        settings_dao: Optional[SettingsDao] = None,
        yuque_dao: Optional[KnowledgeYuqueDao] = None,
        rag_span_dao: Optional[RagFlowSpanDao] = None,
        gpts_app_dao: Optional[GptsAppDao] = None,
    ):
        self._system_app = system_app
        self._dao: KnowledgeSpaceDao = dao
        self._document_dao: KnowledgeDocumentDao = document_dao
        self._chunk_dao: DocumentChunkDao = chunk_dao
        self._yuque_dao: KnowledgeYuqueDao = yuque_dao
        self._task_dao: KnowledgeTaskDao = task_dao
        self._refresh_record_dao: KnowledgeRefreshRecordDao = refresh_record_dao
        self._graph_relation_dao: KnowledgeSpaceGraphRelationDao = graph_relation_dao
        self._settings_dao: SettingsDao = settings_dao
        self._rag_span_dao: RagFlowSpanDao = rag_span_dao
        self._gpts_app_dao: GptsAppDao = gpts_app_dao
        self._serve_config = config

        self._knowledge_id_stores = {}
        self._max_yuque_length = 20
        self._max_semaphore = 20
        self._semaphore = Semaphore(self._max_semaphore)
        self._default_page = 1
        self._default_page_size = 10000

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
        self._yuque_dao = self._yuque_dao or KnowledgeYuqueDao()
        self._task_dao = self._task_dao or KnowledgeTaskDao()
        self._refresh_record_dao = self._refresh_record_dao or KnowledgeRefreshRecordDao()
        self._graph_relation_dao = self._graph_relation_dao or KnowledgeSpaceGraphRelationDao()
        self._settings_dao = self._settings_dao or SettingsDao()
        self._refresh_record_dao = (
            self._refresh_record_dao or KnowledgeRefreshRecordDao()
        )
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
            request.knowledge_type = KnowledgeAccessLevel.PRIVATE.name

        knowledge_id = str(uuid.uuid4())
        request.knowledge_id = knowledge_id
        request.gmt_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        request.gmt_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._dao.create(request)
        return knowledge_id

    def update_document_by_space_name(self, knowledge_id: str, space_name: str):
        logger.info(f"update_document_by_space_name knowledge_id: {knowledge_id}, space_name: {space_name}")

        # update doc
        def update_document(doc, name):
            doc.space = name
            self._document_dao.update_knowledge_document(document=doc)

        # get docs
        docs = self._document_dao.get_knowledge_documents(
            query=KnowledgeDocumentEntity(knowledge_id=knowledge_id),
            page=self._default_page,
            page_size=self._default_page_size
        )
        logger.info(f"docs len is {len(docs)}")

        # submit task with thread pool
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(update_document, doc, space_name) for doc in docs]

            concurrent.futures.wait(futures)

        return True


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

            # update document
            self.update_document_by_space_name(update.knowledge_id, update.name)

        if update.desc:
            knowledge_space.desc = update.desc
        if update.category:
            knowledge_space.category = update.category
        if update.tags:
            knowledge_space.tags = update.tags
        if update.knowledge_type:
            knowledge_space.knowledge_type = update.knowledge_type
        if update.refresh:
            knowledge_space.refresh = (
                update.refresh if update.refresh == "true" else "false"
            )

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

    def create_document(self, request: DocumentServeRequest) -> DocumentServeResponse:
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
        if request.doc_file and request.doc_type == KnowledgeType.DOCUMENT.name:
            doc_file = request.doc_file
            safe_filename = os.path.basename(doc_file.filename)
            custom_metadata = {
                "space_name": space.name,
                "doc_name": doc_file.filename,
                "doc_type": request.doc_type,
            }
            if not request.doc_name:
                request.doc_name = doc_file.filename
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
        if request.doc_name:
            doc_query.update({"doc_name": request.doc_name})
        if space.knowledge_id:
            doc_query.update({"knowledge_id": space.knowledge_id})
        documents = self._document_dao.get_list(doc_query)
        custom_metadata = request.meta_data
        if len(documents) > 0:
            if request.doc_type == KnowledgeType.DOCUMENT.name:
                # 删除重名的文件
                self.delete_document_by_doc_id(knowledge_id=request.knowledge_id, doc_id=documents[0].doc_id)
                logger.info(f"delete document success, doc id is {documents[0].doc_id}")
            else:
                raise Exception(f"document name:{request.doc_name} have already named")
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
            "meta_data": custom_metadata,
            "result": "",
        }
        res = self._document_dao.create(document)
        if doc_id is None:
            raise Exception(f"create document failed, {request.doc_name}")
        return res


    async def sync_single_document(self, request: KnowledgeDocumentRequest):
        logger.info(f"sync_single_document request is {request}")

        if not request.doc_id:
            raise Exception("doc_id is required")
        if not request.chunk_parameters:
            request.chunk_parameters = ChunkParameters(
                chunk_strategy="Automatic",
                chunk_size=512,
                chunk_overlap=50,
            )

        # async run
        asyncio.create_task(
            self.create_knowledge_document_and_sync(
                knowledge_id=request.knowledge_id,
                request=request,
                doc_id=request.doc_id,
            )
        )

        # update status running
        docs = self._document_dao.get_knowledge_documents(query=KnowledgeDocumentEntity(doc_id=request.doc_id, knowledge_id=request.knowledge_id))
        if not docs:
            raise Exception(f"doc_id:{request.doc_id} not found")

        doc = docs[0]
        doc.status = SyncStatus.EXTRACTING.name
        self._document_dao.update_knowledge_document(document=doc)

        return request.doc_id


    async def sync_document(
        self,
        requests: List[KnowledgeSyncRequest],
        knowledge_id_stores: Optional[dict] = None,
    ) -> List:
        """Create a new document entity

        Args:
            request (KnowledgeSpaceRequest): The request

        Returns:
            SpaceServeResponse: The response
        """
        logger.info(
            f"sync_document requests len is {len(requests)}, knowledge_id_stores is {knowledge_id_stores}"
        )

        doc_ids = []
        for sync_request in requests:
            docs = self._document_dao.documents_by_doc_ids([sync_request.doc_id])
            if len(docs) == 0:
                raise Exception(
                    f"there are document called, doc_id: {sync_request.doc_id}"
                )
            doc = docs[0]
            knowledge_id = doc.knowledge_id
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
                chunk_parameters = self.convert_to_chunk_parameters(
                    chunk_parameters=doc.chunk_params
                )
            logger.info(f"chunk_parameters is {chunk_parameters}")

            knowledge_id_store = None
            if knowledge_id_stores is not None:
                logger.info(f"update knowledge_id_stores is {knowledge_id_stores}")

                knowledge_id_store = knowledge_id_stores.get(knowledge_id)

            await self._sync_knowledge_document(
                knowledge_id,
                doc,
                chunk_parameters,
                sync_request.yuque_doc_uuid,
                knowledge_id_store=knowledge_id_store,
                extract_image=sync_request.extract_image,
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

        apps = self._gpts_app_dao.get_gpts_apps_by_knowledge_id(
            knowledge_id=knowledge_id
        )
        if not apps:
            return None

        # get agents
        agents = [app.app_name for app in apps]
        logger.info(
            f"get_agents_by_knowledge_id agents len is {len(agents)} name is {agents}"
        )

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
            logger.error(
                f"delete knowledge_id not invalid, agents {used_agents} used knowledge_id {knowledge_id}"
            )

            raise Exception(
                f"该知识库被以下agent关联不能删除{used_agents}"
            )

        document_query = KnowledgeDocumentEntity(knowledge_id=space.knowledge_id)
        documents = self._document_dao.get_documents(document_query)
        if documents:
            storage_connector = self.get_or_update_knowledge_id_store(
                knowledge_id=space.knowledge_id
            )
            # delete vectors
            storage_connector.delete_vector_name(space.name)
            for document in documents:
                # delete chunks
                self._chunk_dao.raw_delete(doc_id=document.doc_id)
                # delete yuque docs
                self._yuque_dao.raw_delete(
                    query=KnowledgeYuqueEntity(doc_id=document.doc_id)
                )

            # delete documents
            self._document_dao.raw_delete(document_query)

        # delete graph relation
        if space.storage_type == KnowledgeGraphType.AKG.name:
            self._graph_relation_dao.raw_delete(
                query=KnowledgeSpaceGraphRelationEntity(knowledge_id=space.knowledge_id)
            )

        # delete space
        self._dao.delete(query_request)
        return True

    def update_document(self, request: DocumentServeRequest):
        """update knowledge document

        Args:
            - space_id: space id
            - request: KnowledgeDocumentRequest
        """
        if not request.doc_id:
            raise Exception("doc_id is required")
        document = self._document_dao.get_one({"doc_id": request.doc_id})
        entity = self._document_dao.from_response(document)
        if request.doc_name:
            entity.doc_name = request.doc_name
            update_chunk = self._chunk_dao.get_one({"doc_id": entity.doc_id})
            if update_chunk:
                update_chunk.doc_name = request.doc_name
                self._chunk_dao.update({"id": update_chunk.id}, update_chunk)
        if request.doc_id:
            entity.doc_id = request.doc_id
            update_chunks = self._chunk_dao.get_list({"doc_id": entity.doc_id})
            if update_chunks:
                if request.meta_data:
                    vector_store = self.storage_manager.create_vector_store(
                        index_name=request.knowledge_id
                    )
                    if entity.meta_data == "null":
                        entity.meta_data = "{}"
                    doc_meta = json.loads(entity.meta_data or "{}")
                    for key, value in request.meta_data.items():
                        doc_meta[key] = value
                    for update_chunk in update_chunks:
                        metadata = json.loads(update_chunk.meta_data)
                        for key, value in request.meta_data.items():
                            metadata[key] = value
                        if vector_store:
                            filters = [MetadataFilter(
                                key="doc_id", value=request.doc_id
                            )]
                            vector_store.update(
                                set_data={"metadata": metadata},
                                filters=MetadataFilters(filters=filters),
                            )
                            update_chunk.meta_data = json.dumps(
                                metadata, ensure_ascii=False
                            )
                        self.update_chunk(request=update_chunk)
                    entity.meta_data = json.dumps(
                                doc_meta, ensure_ascii=False
                    )
        self._document_dao.update(
            {"doc_id": entity.doc_id}, self._document_dao.to_request(entity)
        )

    def delete_document(self, document_id: str) -> Optional[DocumentServeResponse]:
        """Delete a Flow entity

        Args:
            uid (str): The uid

        Returns:
            SpaceServeResponse: The data after deletion
        """

        query_request = {"doc_id": document_id}
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
            vector_store_connector = self.get_or_update_knowledge_id_store(
                knowledge_id=knowledge_id
            )

            # delete vector by ids
            vector_store_connector.delete_by_ids(vector_ids)
        # delete chunks
        self._chunk_dao.raw_delete(docuemnt.doc_id)
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

    def update_chunks(self, request: ChunkServeRequest):
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
            await self._sync_knowledge_document(
                knowledge_id=space_id,
                doc=doc,
                chunk_parameters=chunk_parameters,
                extract_image=sync_request.extract_image,
            )
            doc_ids.append(doc.id)
        return doc_ids


    def update_doc_params(self, doc: KnowledgeDocumentEntity, extract_image: bool):
        logger.info(f"update_doc_params doc params is {doc.doc_params}, extract_image is {extract_image}")

        try:
            doc_params = json.loads(doc.doc_params) if doc.doc_params else {}
        except Exception as e:
            logger.error(
                f"update_doc_params error doc_id is {doc.id}, doc_params is {doc.doc_params}, exception is {str(e)}"
            )
            doc_params = {}
        doc_params.update({"extract_image": extract_image})

        return json.dumps(doc_params, ensure_ascii=False)


    async def _sync_knowledge_document(
        self,
        knowledge_id,
        doc: KnowledgeDocumentEntity,
        chunk_parameters: ChunkParameters,
        yuque_doc_uuid: Optional[str] = None,
        knowledge_id_store: Optional[IndexStoreBase] = None,
        extract_image: bool = False,
    ) -> None:
        """sync knowledge document chunk into vector store"""
        logger.info(
            f"_sync_knowledge_document start, chunk_parameters is {chunk_parameters} 当前线程数：{threading.active_count()}, knowledge_id_store is {knowledge_id_store}"
        )

        space = self.get({"knowledge_id": knowledge_id})

        if knowledge_id_store is None:
            storage_connector = self.get_or_update_knowledge_id_store(
                knowledge_id=knowledge_id
            )
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
                self._system_app,
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
            # labels = {"label": doc.summary} if doc.summary else {}
            meta_data = {
                "doc_id": doc.doc_id,
                "knowledge_id": knowledge_id,
                "knowledge_name": space.name,
                "doc_name": doc.doc_name,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "modified_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if doc.meta_data and doc.meta_data != "null":
                meta_data.update(json.loads(doc.meta_data) if doc.meta_data else {})
            # meta_data = json.loads(doc.meta_data) if doc.meta_data else {}
            knowledge = KnowledgeFactory.create(
                datasource=knowledge_content,
                knowledge_type=KnowledgeType.get_by_value(doc.doc_type),
                metadata=meta_data,
                doc_token=doc.doc_token,
                yuque_doc_uuid=yuque_doc_uuid or "",
                **meta_data or {},
            )

        doc.status = SyncStatus.RUNNING.name
        # set default chunk strategy
        if not chunk_parameters:
            chunk_parameters = self.get_default_chunk_parameters()
        if not chunk_parameters.chunk_strategy:
            chunk_parameters.chunk_strategy = "Automatic"
        doc.chunk_params = json.dumps(chunk_parameters, cls=ChunkParametersEncoder)

        doc.gmt_modified = datetime.now()
        domain_index = DomainGeneralIndex()
        # document ETL(extract -> transform -> load) process
        chunks = await domain_index.extract(knowledge, chunk_parameters, extract_image)

        doc.doc_params = self.update_doc_params(doc, extract_image)

        chunk_entities = []
        for chunk_doc in chunks:
            if chunk_doc.metadata:
                chunk_doc.metadata["doc_id"] = doc.doc_id
                chunk_doc.metadata["knowledge_id"] = knowledge_id
                chunk_doc.metadata["doc_name"] = doc.doc_name
                chunk_doc.metadata["create_time"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                chunk_doc.metadata["modified_time"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                chunk_doc.metadata["doc_type"] = doc.doc_type
            chunk_entities.append(
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
            )

        self._chunk_dao.create_documents_chunks(chunk_entities)
        doc.chunk_size = len(chunks)

        await blocking_func_to_async(
            self._system_app, self._document_dao.update_knowledge_document, doc
        )

        asyncio.create_task(
            self.async_doc_process(
                domain_index,
                chunks,
                storage_connector,
                doc,
                space,
                knowledge_content,
                extract_image=extract_image,
            )
        )
        logger.info(f"begin save document chunks, doc:{doc.doc_name}")


    def get_vector_and_update_chunk(self, save_chunks: List):
        vector_ids = []
        insert_chunks = []
        for save_chunk in save_chunks:
            query_chunk = {"chunk_id": save_chunk.chunk_id}
            exist_chunk = self._chunk_dao.get_one(query_chunk)
            if exist_chunk:
                self._chunk_dao.update(query_chunk, save_chunk)
            else:
                insert_chunks.append(save_chunk)
            vector_ids.append(save_chunk.vector_id)
        self._chunk_dao.create_documents_chunks(insert_chunks)
        logger.info(f"get_vector_and_update_chunk vector_ids:{vector_ids}")

        return vector_ids

    async def aget_vector_and_update_chunk(self, save_chunks: List):
        return await blocking_func_to_async(
            self._system_app, self.get_vector_and_update_chunk, save_chunks
        )

    @trace("async_doc_process")
    async def async_doc_process(
        self,
        domain_index: DomainGeneralIndex,
        chunks,
        storage_connector,
        doc,
        space,
        knowledge_content: str,
        extract_image: bool = False,
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
            with (root_tracer.start_span(
                "app.knowledge.assembler.persist",
                metadata={"doc": doc.doc_name},
            )):
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
                    if extract_image:
                        context = space.context
                        vlm_model = context.get("vlm_model") if context else None
                        image_extractor = ImageExtractor(
                            llm_client=self.llm_client,
                            model_name=vlm_model or "Qwen2.5-VL-72B-Instruct"
                        )
                        chunks = await domain_index.transform(
                            chunks=chunks,
                            image_extractor=image_extractor,
                        )
                    save_chunks = await domain_index.load(
                        chunks=chunks,
                        vector_store=storage_connector,
                        max_chunks_once_load=max_chunks_once_load,
                        max_threads=max_threads,
                    )
                    logger.info(
                        f"async_doc_process end 当前线程数: {threading.active_count()}"
                    )

                    vector_ids = await self.aget_vector_and_update_chunk(save_chunks)
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

    async def knowledge_search(self, request: KnowledgeSearchRequest) -> List[Chunk]:
        """Retrieve the service."""
        logger.info(f"knowledge_search request is {request}")
        if request.mode == RetrieverStrategy.EXACT.value:
            request.enable_split_query = False
            request.enable_summary = False
        search_task = self.build_knowledge_search_dag(request=request)
        return await search_task.call(call_data={"query": request.query})

    def build_knowledge_search_dag(self, request: KnowledgeSearchRequest):
        """Build a DAG for knowledge search."""
        with DAG(
            "derisk_knowledge_search_dag", tags={"derisk_rag": "derisk_rag"}
        ) as _dag:
            # Create an input task
            input_task = InputOperator(SimpleCallDataInputSource())
            knowledge_operator = SpaceRetrieverOperator(
                knowledge_ids=request.knowledge_ids,
                rerank_top_k=request.top_k,
                single_knowledge_top_k=request.single_knowledge_top_k,
                similarity_score_threshold=request.similarity_score_threshold,
                rerank_score_threshold=request.score_threshold,
                retrieve_mode=request.mode,
                llm_model=request.summary_model,
                rerank=request.enable_rerank,
                rerank_model=request.rerank_model,
                metadata_filters=request.metadata_filters,
                tag_filters=request.tag_filters,
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
                    prompt=request.summary_prompt,
                    task_name="生成总结",
                )
                if request.enable_split_query:
                    query_split_operator = SplitQueryOperator(task_name="问题拆解", llm_client=llm_client, model_name=request.split_query_model, prompt=request.split_query_prompt)
                    (
                        input_task
                        >> query_split_operator
                        >> knowledge_operator
                        >> summary_operator
                    )
                else:
                    input_task >> knowledge_operator >> summary_operator
                return summary_operator
            else:
                if request.enable_split_query:
                    query_split_operator = SplitQueryOperator(task_name="问题拆解", llm_client=llm_client, model_name=request.split_query_model, prompt=request.split_query_prompt)
                    (input_task >> query_split_operator >> knowledge_operator)
                else:
                    input_task >> knowledge_operator
        return knowledge_operator

    async def aget_space_context_by_space_id(self, knowledge_id):
        return await blocking_func_to_async(
            self._system_app, self.get_space_context_by_space_id, knowledge_id
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
            self._system_app, self.create_knowledge_document, knowledge_id, request
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
        if request.doc_type == KnowledgeType.YUQUEURL.name:
            for doc in documents:
                if doc.content == request.content:
                    logger.error(
                        f"yuque doc url is {doc.content} {doc.doc_name} have already exist"
                    )

                    raise Exception(
                        f"yuque doc url is {doc.content} {doc.doc_name} have already exist"
                    )
        elif len(documents) > 0:
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
        meta_data = {}
        for tag in request.tags if request.tags else []:
            meta_data[tag.get("name")] = tag.get("value")
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
            meta_data=json.dumps(meta_data, ensure_ascii=False),
            result="",
            chunk_params=json.dumps(
                request.chunk_parameters, cls=ChunkParametersEncoder
            ),
        )

        id = self._document_dao.create_knowledge_document(document)

        if request.doc_type == KnowledgeType.YUQUEURL.name:
            #  create yuque doc
            yuque_id = str(uuid.uuid4())
            yuque = KnowledgeYuqueEntity(
                yuque_id=yuque_id,
                doc_id=doc_id,
                knowledge_id=knowledge_id,
                token=request.doc_token,
            )
            self._yuque_dao.create_knowledge_yuque(docs=[yuque])

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"create_knowledge_document cost time is {cost_time} seconds")

        if id is None:
            raise Exception(f"create document failed, {request.doc_name}")
        return doc_id

    def _get_vector_connector(self, knowledge_id):
        spaces = self._dao.get_knowledge_space_by_knowledge_ids([knowledge_id])
        if spaces is None:
            logger.error(
                f"get_vector_connector space is None, knowledge_id is {knowledge_id}"
            )

            raise Exception(
                f"get_vector_connector space is None, knowledge_id is {knowledge_id}"
            )
        space = spaces[0]

        storage_connector = self.storage_manager.get_storage_connector(
            index_name=knowledge_id, storage_type=space.storage_type
        )

        return storage_connector

    async def adocuments_by_doc_ids(self, doc_ids) -> List[KnowledgeDocumentEntity]:
        return await blocking_func_to_async(
            self._system_app, self._document_dao.documents_by_doc_ids, doc_ids
        )

    async def abatch_document_sync(
        self,
        knowledge_id,
        sync_requests: List[KnowledgeSyncRequest],
        space_context: Optional[dict] = None,
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
        logger.info(
            f"abatch_document_sync start, 当前线程数：{threading.active_count()}"
        )

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
            await self._sync_knowledge_document(
                knowledge_id,
                doc,
                chunk_parameters,
                sync_request.yuque_doc_uuid,
                knowledge_id_store,
                extract_image=sync_request.extract_image,
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
        doc_id: str,
        space_context: Optional[dict] = None,
        knowledge_id_store: Optional[dict] = None,
    ):
        start_time = timeit.default_timer()
        logger.info(
            f"create_knowledge_document_and_sync start, 当前线程数：{threading.active_count()}"
        )

        # build param
        knowledge_sync_request = KnowledgeSyncRequest(
            doc_id=doc_id,
            chunk_parameters=request.chunk_parameters,
            extract_image= request.extract_image,
        )
        if (
            request.doc_type is not None
            and request.doc_type == KnowledgeType.YUQUEURL.name
        ):
            logger.info(f"update yuque info doc_id: {doc_id}")

            knowledge_sync_request.yuque_doc_uuid = request.yuque_doc_uuid

        doc_ids = await self.abatch_document_sync(
            knowledge_id=knowledge_id,
            sync_requests=[knowledge_sync_request],
            space_context=space_context,
            knowledge_id_store=knowledge_id_store,
        )
        logger.info(f"doc_id is {doc_id}， doc_ids is {doc_ids}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"new_create_knowledge_document_and_sync cost time is {cost_time} seconds"
        )

        return doc_id

    def build_yuque_url(self, request: YuqueRequest):
        if request.group_login is None:
            raise Exception("group_login is None")
        if request.book_slug is None:
            raise Exception("book_slug is None")
        if request.yuque_doc_id is None:
            raise Exception("yuque_doc_id is None")

        yuque_url = f"{BASE_YUQUE_URL}/{request.group_login}/{request.book_slug}/{request.yuque_doc_id}"
        logger.info(f"yuque_url is {yuque_url}")

        return yuque_url

    def build_knowledge_sync_request(self, request: YuqueRequest):
        logger.info(f"build_knowledge_sync_request request is {request}")

        if request.yuque_url is None:
            raise Exception("yuque_url is None")
        if request.yuque_name is None:
            raise Exception("yuque_name is None")
        if request.chunk_parameters is None:
            raise Exception("chunk_parameters is None")

        return KnowledgeDocumentRequest(
            space_id=request.knowledge_id,
            doc_name=request.yuque_name,
            content=request.yuque_url,
            doc_token=request.yuque_token,
            doc_type=KnowledgeType.YUQUEURL.name,
            chunk_parameters=request.chunk_parameters,
            yuque_group_login=request.group_login,
            yuque_book_slug=request.book_slug,
            yuque_doc_slug=request.yuque_doc_id,
            yuque_doc_uuid=request.yuque_doc_uuid,
            extract_image=request.extract_image,
        )

    def get_yuque_doc_form_url(self, yuque_url: str, yuque_token: str):
        logger.info(
            f"get_yuque_doc_form_url yuque_url is {yuque_url}, yuque_token is {yuque_token}"
        )

        # check params
        if yuque_url is None:
            raise Exception("yuque url is None")
        if yuque_token is None:
            raise Exception("yuque token is None")
        if yuque_url.count("/") < 5:
            raise Exception(f"yuque url {yuque_url} is invalid")

        _, _, _, group, book_slug, doc_id = yuque_url.split("/", 5)
        web_reader = AntYuqueLoader(access_token=yuque_token)
        doc_detail = web_reader.single_doc(
            group=group, book_slug=book_slug, doc_id=doc_id
        )
        if doc_detail is None:
            raise Exception(f"document is None, check yuque url: {yuque_url}")
        logger.info(f"get_yuque_name_form_url document is {doc_detail.get('title')}")

        return doc_detail

    async def aget_yuque_doc_form_url(self, yuque_url: str, yuque_token: str):
        return await blocking_func_to_async(
            self._system_app, self.get_yuque_doc_form_url, yuque_url, yuque_token
        )

    def update_yuque_info_by_doc_id(self, doc_id: int, request: YuqueRequest):
        logger.info(
            f"update_yuque_info_by_doc_id doc_id is {doc_id}, request is {request}"
        )

        if doc_id is None:
            raise Exception("doc_id is None")
        if request.group_login is None:
            raise Exception("group_login is None")
        if request.book_slug is None:
            raise Exception("book_slug is None")
        if request.yuque_doc_id is None:
            raise Exception("yuque_doc_id is None")

        # get document
        query = KnowledgeDocumentEntity(id=doc_id)
        documents = self._document_dao.get_knowledge_documents(query)
        if documents is None or len(documents) == 0:
            raise Exception(f"document is None, check doc id : {doc_id}")
        document = documents[0]

        # update yuque info
        document.yuque_group_login = request.group_login
        document.yuque_book_slug = request.book_slug
        document.yuque_doc_slug = request.yuque_doc_id

        # update db
        update = self._document_dao.update_knowledge_document(document)
        logger.info(f"update is {update}")

        return update

    def get_yuque_doc_from_uuid(
        self, yuque_token: str, group_login: str, book_slug: str, doc_uuid: str
    ):
        logger.info(
            f"get_yuque_doc_from_uuid yuque_token is {yuque_token}, {group_login}, {book_slug}, {doc_uuid}"
        )

        # get tocs
        web_reader = AntYuqueLoader(access_token=yuque_token)
        table_of_contents = web_reader.get_toc_by_group_login_and_book_slug(
            group_login=group_login, book_slug=book_slug
        )

        # find doc by uuid
        doc = None
        for toc in table_of_contents:
            if toc.get("uuid") == doc_uuid:
                logger.info(f"find doc success by uuid {toc}")

                if toc.get("type") == "DOC":
                    doc = web_reader.single_doc(
                        group=group_login, book_slug=book_slug, doc_id=toc.get("slug")
                    )
                else:
                    doc = {
                        "id": toc.get("id"),
                        "type": toc.get("type"),
                        "title": toc.get("title"),
                    }
                return doc
        logger.info(f"find doc failed by uuid {doc}")

        return doc

    async def aget_yuque_doc_from_uuid(
        self, yuque_token: str, group_login: str, book_slug: str, doc_uuid: str
    ):
        return await blocking_func_to_async(
            self._system_app,
            self.get_yuque_doc_from_uuid,
            yuque_token,
            group_login,
            book_slug,
            doc_uuid,
        )

    def get_yuque_doc_uuid(
        self, yuque_token: str, group_login: str, book_slug: str, doc_slug: str
    ):
        logger.info(f"get_yuque_doc_uuid start")

        # get tocs
        web_reader = AntYuqueLoader(access_token=yuque_token)
        table_of_contents = web_reader.get_toc_by_group_login_and_book_slug(
            group_login=group_login, book_slug=book_slug
        )
        yuque_doc_uuid = "UUID NOT FOUND"
        for toc in table_of_contents:
            if toc.get("slug") == doc_slug:
                logger.info(f"find doc uuid success! {toc.get('slug')}")

                yuque_doc_uuid = toc.get("uuid")

                break
        logger.info(f"find yuque doc uuid:  {yuque_doc_uuid}")

        return yuque_doc_uuid

    async def aget_yuque_doc_uuid(
        self, yuque_token: str, group_login: str, book_slug: str, doc_slug: str
    ):
        return await blocking_func_to_async(
            self._system_app,
            self.get_yuque_doc_uuid,
            yuque_token,
            group_login,
            book_slug,
            doc_slug,
        )

    async def add_yuque_param_to_request(self, request: YuqueRequest):
        # build yuque url
        yuque_url = self.build_yuque_url(request=request)
        request.yuque_url = yuque_url

        # update yuque info in request
        try:
            yuque_doc = await self.aget_yuque_doc_form_url(
                yuque_url=yuque_url, yuque_token=request.yuque_token
            )

            request.yuque_name = yuque_doc.get("title") + "_" + request.book_slug
            # 获取真正的yuque doc uuid, doc id 部分文档为空
            yuque_doc_uuid = await self.aget_yuque_doc_uuid(
                yuque_token=request.yuque_token,
                group_login=request.group_login,
                book_slug=request.book_slug,
                doc_slug=request.yuque_doc_id,
            )
            request.yuque_doc_uuid = yuque_doc_uuid
        except Exception as e:
            logger.error(f"get yuque doc name failed")

            if "Not Found for url" in str(e):
                # case 1: doc slug is uuid
                yuque_doc = await self.aget_yuque_doc_from_uuid(
                    yuque_token=request.yuque_token,
                    group_login=request.group_login,
                    book_slug=request.book_slug,
                    doc_uuid=request.yuque_doc_id,
                )
                if yuque_doc is not None:
                    if yuque_doc.get("id"):
                        logger.info(
                            f"find doc by uuid, doc type is doc, need to sync!{yuque_doc}"
                        )

                        request.yuque_name = (
                            yuque_doc.get("title") + "_" + request.book_slug
                        )

                        request.yuque_doc_uuid = request.yuque_doc_id
                        request.yuque_doc_id = str(yuque_doc.get("slug"))
                        request.yuque_url = self.build_yuque_url(request=request)
                    else:
                        logger.error(
                            f"find doc by uuid, doc type is title, no need to sync! {yuque_doc}"
                        )

                        return ""
                else:
                    # case 2: doc slug is invalid
                    logger.error(
                        f"check yuque url: {yuque_url} and token: {request.yuque_token} again!"
                    )

                    request.yuque_name = "error_" + yuque_url

        return request, yuque_url

    async def create_single_yuque_knowledge(
        self,
        knowledge_id,
        request: YuqueRequest,
        space_context: dict,
        knowledge_id_store: Optional[dict] = None,
    ):
        start_time = timeit.default_timer()
        logger.info(
            f"create_single_yuque_knowledge start, 当前线程数：{threading.active_count()}"
        )

        try:
            # update yuque params
            request, yuque_url = await self.add_yuque_param_to_request(request=request)

            # build knowledge_sync_request
            knowledge_sync_request = self.build_knowledge_sync_request(request=request)

            # generate doc_id
            doc_id = await self.acreate_knowledge_document(
                knowledge_id=knowledge_id, request=knowledge_sync_request
            )
            logger.info(
                f"create_single_yuque_knowledge yuque url is {yuque_url}, doc_id is {doc_id}"
            )

            asyncio.create_task(
                self.create_knowledge_document_and_sync(
                    knowledge_id=knowledge_id,
                    request=knowledge_sync_request,
                    space_context=space_context,
                    doc_id=doc_id,
                    knowledge_id_store=knowledge_id_store,
                )
            )

        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}")

            doc_id = None
        finally:
            end_time = timeit.default_timer()
            cost_time = round(end_time - start_time, 2)
            logger.info(
                f"create_single_yuque_knowledge cost time is {cost_time} seconds, 当前线程数：{threading.active_count()}"
            )

            return doc_id

    async def limited_create_single_yuque_knowledge(
        self, knowledge_id, request, space_context
    ):
        logger.info(
            f"limited_create_single_yuque_knowledge start semaphore is, yuque slug is {request.yuque_doc_id}"
        )

        return await self.create_single_yuque_knowledge(
            knowledge_id=knowledge_id, request=request, space_context=space_context
        )

    async def create_batch_yuque_knowledge_and_sync(
        self, requests: List[YuqueRequest], knowledge_id_stores: Optional[dict] = None
    ):
        logger.info(
            f"create_batch_yuque_knowledge_and_sync requests len is {len(requests)}, 当前线程数：{threading.active_count()} "
        )
        start_time = timeit.default_timer()

        space_context = await self.aget_space_context_by_space_id(
            requests[0].knowledge_id
        )
        request = requests[0]
        if not knowledge_id_stores or knowledge_id_stores[request.knowledge_id] is None:
            knowledge_id_store = self.get_or_update_knowledge_id_store(
                knowledge_id=requests[0].knowledge_id
            )
        else:
            knowledge_id_store = knowledge_id_stores[request.knowledge_id]

        doc_id = await self.create_single_yuque_knowledge(
            knowledge_id=request.knowledge_id,
            request=request,
            space_context=space_context,
            knowledge_id_store=knowledge_id_store,
        )
        doc_ids = [doc_id]
        logger.info(f"doc ids len is {len(doc_ids)}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(
            f"create_batch_yuque_knowledge_and_sync cost time is {cost_time} seconds"
        )

        return doc_ids

    def offline_create_batch_yuque_knowledge_and_sync(
        self, requests: List[YuqueRequest]
    ):
        logger.info(
            f"offline_create_batch_yuque_knowledge_and_sync start, 当前线程数：{threading.active_count()}, len is {len(requests)}"
        )

        # insert to db
        tasks = []
        datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
        microsecond_str = f"{datetime.now().microsecond:06d}"
        batch_id = f"{datetime_str}{microsecond_str}"
        for request in requests:
            task = KnowledgeTaskEntity(
                task_id=str(uuid.uuid4()),
                knowledge_id=request.knowledge_id,
                doc_type=KnowledgeType.YUQUEURL.name,
                doc_content=self.build_yuque_url(request),
                yuque_token=request.yuque_token,
                group_login=request.group_login,
                book_slug=request.book_slug,
                yuque_doc_id=request.yuque_doc_id,
                chunk_parameters=json.dumps(
                    request.chunk_parameters, cls=ChunkParametersEncoder
                ),
                status=TaskStatusType.TODO.name,
                owner=request.owner or "",
                batch_id=batch_id,
                retry_times=0,
            )
            tasks.append(task)

        self._task_dao.create_knowledge_task(tasks=tasks)

        return True

    async def online_create_batch_yuque_knowledge_and_sync(
        self, requests: List[YuqueRequest]
    ):
        logger.info(
            f"online_create_batch_yuque_knowledge_and_sync start, len is {len(requests)}"
        )

        # check params
        if not requests:
            logger.info(
                f"online_create_batch_yuque_knowledge_and_sync requests is empty"
            )

            return True

        # init knowledge_id_store
        knowledge_id_store = self.get_or_update_knowledge_id_store(
            knowledge_id=requests[0].knowledge_id
        )
        logger.info(
            f"online_create_batch_yuque_knowledge_and_sync get_or_update_knowledge_id_store knowledge_id_store is {knowledge_id_store}"
        )

        knowledge_id_stores = self._knowledge_id_stores

        # async docs
        async def process_requests(self, requests):
            # 控制最大并发数
            async def process_one(request):
                async with self._semaphore:
                    try:
                        return await self.create_batch_yuque_knowledge_and_sync(
                            requests=[request], knowledge_id_stores=knowledge_id_stores
                        )
                    except Exception as e:
                        logger.error(f"Request {request} failed: {str(e)}")

                        # 隔离异常，返回标记
                        return None

            # 并行执行所有请求
            tasks = [process_one(req) for req in requests]
            doc_ids = await asyncio.gather(*tasks)

            # 过滤掉失败项（None）
            return [doc_id for doc_id in doc_ids if doc_id is not None]

        doc_ids = await process_requests(self, requests)
        logger.info(
            f"online_create_batch_yuque_knowledge_and_sync doc_ids is {doc_ids}"
        )

        return True

    async def create_batch_yuque_knowledge_and_sync_v2(
        self, requests: List[YuqueRequest]
    ):
        logger.info(
            f"create_batch_yuque_knowledge_and_sync requests len is {len(requests)}, 当前线程数: {threading.active_count()}"
        )
        start_time = timeit.default_timer()

        try:
            if len(requests) <= self._max_yuque_length:
                # 少量文档 在线导入
                is_success = await self.online_create_batch_yuque_knowledge_and_sync(
                    requests=requests
                )
            else:
                # 大量文档 离线导入
                is_success = self.offline_create_batch_yuque_knowledge_and_sync(
                    requests=requests
                )

            end_time = timeit.default_timer()
            cost_time = round(end_time - start_time, 2)
            logger.info(
                f"create_batch_yuque_knowledge_and_sync cost time is {cost_time} seconds, is_success is {is_success}, 当前线程数: {threading.active_count()}"
            )

            return True
        except Exception as e:
            logger.error(f"create_batch_yuque_knowledge_and_sync error, {str(e)}")

            raise Exception(f"create_batch_yuque_knowledge_and_sync error, {str(e)}")



    async def create_yuque_book(self, request: YuqueRequest):
        logger.info(f"create_yuque_book request is {request}")

        # check params
        if not request.yuque_token or not request.group_login or not request.book_slug or not request.knowledge_id:
            raise Exception("yuque_token, group_login, book_slug and knowledge_id are required")

        # check exists
        yuque_docs = self._yuque_dao.get_knowledge_yuque(query=KnowledgeYuqueEntity(knowledge_id=request.knowledge_id,
                                                                                    group_login=request.group_login,
                                                                                    book_slug=request.book_slug))
        if yuque_docs:
            raise Exception(f"yuque book {request.book_slug} is already existed")

        # get all docs
        web_reader = AntYuqueLoader(access_token=request.yuque_token)
        docs = web_reader.get_docs_by_group_book_slug(group_login=request.group_login, book_slug=request.book_slug)
        logger.info(f"create_yuque_book docs len is {len(docs)}")

        # sync docs
        requests = []
        for doc in docs:
            new_request = YuqueRequest(yuque_token=request.yuque_token, knowledge_id=request.knowledge_id,
                                       group_login=request.group_login, book_slug=request.book_slug,
                                       chunk_parameters=request.chunk_parameters, yuque_doc_id=str(doc.get('slug')))
            requests.append(new_request)

        return await self.create_batch_yuque_knowledge_and_sync_v2(requests=requests)

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
            chunk_strategy="Automatic",
            chunk_size=500,
            chunk_overlap=100,
            separator="\n",
        )


    def get_default_strategy_detail(self):
        return StrategyDetail(
            strategy=DEFAULT_CHUNK_STRATEGY,
            name="智能分段",
            description="split document by automatic"
        )

    def convert_to_chunk_parameters(self, chunk_parameters: Optional[str] = None):
        logger.info(
            f"convert_to_chunk_parameters chunk_parameters is {chunk_parameters}"
        )

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
            logger.error(
                f"convert_to_chunk_parameters failed, use default chunk param, error is {str(e)}"
            )

            return self.get_default_chunk_parameters()

    def build_yuque_request(self, task: KnowledgeTaskEntity):
        return YuqueRequest(
            knowledge_id=task.knowledge_id,
            yuque_token=task.yuque_token,
            group_login=task.group_login,
            book_slug=task.book_slug,
            yuque_doc_id=task.yuque_doc_id,
            chunk_parameters=self.convert_to_chunk_parameters(task.chunk_parameters),
        )

    async def start_task(
        self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None
    ):
        logger.info(
            f"start_task start task, task id is {task.task_id}, 当前线程数: {threading.active_count()}"
        )

        request = self.build_yuque_request(task=task)

        if not task.start_time:
            task.start_time = (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)

        try:
            doc_id = await self.create_batch_yuque_knowledge_and_sync(
                requests=[request], knowledge_id_stores=knowledge_id_stores
            )
        except Exception as e:
            logger.error(f"start_task error, {str(e)}")
            doc_id = ""
            task.error_msg = str(e)
        host = self.get_host_ip()

        # insert doc_id to db
        if doc_id:
            task.doc_id = doc_id[0]
            task.host = host
            task.status = TaskStatusType.RUNNING.name
            task.error_msg = ""
        else:
            task.status = TaskStatusType.FAILED.name
        task.gmt_modified = (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)

        self._task_dao.update_knowledge_task_batch(tasks=[task])
        return True

    def check_timeout(self, task: KnowledgeTaskEntity):
        start_time = task.start_time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        difference = abs(
            datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")
            - datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        )
        is_timeout = difference > timedelta(minutes=3)
        logger.info(f"check_timeout is timeout {is_timeout}")

        return is_timeout

    def check_retry_times(self, task: KnowledgeTaskEntity):
        retry_times = task.retry_times if task.retry_times else 0
        can_retry = retry_times < 2
        logger.info(f"check_retry_times can retry is {can_retry}")

        return can_retry

    async def retry_doc(
        self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None
    ):
        logger.info(
            f"retry_doc start task, task id is {task.task_id}, knowledge_id_stores is {knowledge_id_stores}"
        )

        await self.sync_document(
            requests=[KnowledgeSyncRequest(doc_id=task.doc_id)],
            knowledge_id_stores=knowledge_id_stores,
        )

        return True

    async def check_doc_sync_status(
        self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None
    ):
        logger.info(
            f"check_doc_sync_status, task id is {task.task_id}, doc_id is {task.doc_id}"
        )

        doc_id = task.doc_id
        knowledge_id = task.knowledge_id
        doc = self.get_document_by_doc_id(knowledge_id=knowledge_id, doc_id=doc_id)
        if not doc or not doc.status:
            logger.error(
                f"check_doc_sync_status doc is None, {doc_id}, task id is {task.task_id}"
            )

            task.status = TaskStatusType.FINISHED.name
            task.error_msg = "doc not found, task force failed"
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self._task_dao.update_knowledge_task_batch(tasks=[task])
            return True

        if doc.status == SyncStatus.FINISHED.name:
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.status = TaskStatusType.SUCCEED.name
        elif (
            doc.status == SyncStatus.RUNNING.name
            or doc.status == SyncStatus.RETRYING.name
        ):
            is_timeout = self.check_timeout(task=task)
            if is_timeout:
                task.status = TaskStatusType.FINISHED.name
                task.error_msg = "timeout failed"
                task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif doc.status == SyncStatus.FAILED.name or doc.status == SyncStatus.TODO.name:
            task.status = TaskStatusType.RUNNING.name
            retry = self.check_retry_times(task=task)
            if retry:
                task.retry_times += 1 if task.retry_times else 1

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

    def end_task(
        self,
        task: Optional[KnowledgeTaskEntity] = None,
        error_msg: Optional[str] = None,
    ):
        logger.info(
            f"end_task start, task id is {task.task_id}, task status is {task.status}"
        )

        task.status = TaskStatusType.FINISHED.name
        task.error_msg = error_msg
        task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._task_dao.update_knowledge_task_batch(tasks=[task])
        return True

    async def retry_task(
        self, task: KnowledgeTaskEntity, knowledge_id_stores: Optional[dict] = None
    ):
        logger.info(
            f"retry_task start, task id is {task.task_id}， knowledge_id_stores is {knowledge_id_stores}"
        )

        task.status = TaskStatusType.RUNNING.name
        retry = self.check_retry_times(task=task)
        if retry:
            task.retry_times = 0 if task.retry_times is None else task.retry_times + 1

            if task.doc_id:
                try:
                    await self.retry_doc(
                        task=task, knowledge_id_stores=knowledge_id_stores
                    )
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
                ignore_status=[
                    TaskStatusType.SUCCEED.name,
                    TaskStatusType.FINISHED.name,
                ]
            )
            for knowledge_id in knowledge_ids:
                if (
                    self._knowledge_id_stores is None
                    or knowledge_id not in self._knowledge_id_stores.keys()
                ):
                    logger.info(
                        f"auto_sync init knowledge id index store {knowledge_id}, self._knowledge_id_stores len is {len(self._knowledge_id_stores.keys())}"
                    )

                    self._knowledge_id_stores[knowledge_id] = (
                        self._get_vector_connector(knowledge_id=knowledge_id)
                    )
        except Exception as e:
            logger.error(f"init_knowledge_id_stores error, {str(e)}")

            raise Exception(f"init_knowledge_id_stores error, {str(e)}")

        return self._knowledge_id_stores

    async def auto_sync(self):
        # get task
        tasks = self._task_dao.get_knowledge_tasks_by_status(
            ignore_status=[TaskStatusType.SUCCEED.name, TaskStatusType.FINISHED.name],
            limit=1,
        )
        if len(tasks) == 0:
            # 延长冷启动时间，同步速率不变
            await asyncio.sleep(10)
            return True
        task = tasks[0]

        # check host
        current_host = self.get_host_ip()
        if not task.host:
            logger.info(f"task host is None, update host : {current_host}")

            task.host = current_host
            self._task_dao.update_knowledge_task_batch(tasks=[task])
        elif current_host != task.host:
            logger.info(
                f"current host is {current_host}, task host is {task.host}, break"
            )

            return True
        else:
            try:
                # init knowledge id index store
                knowledge_id_stores = self.init_knowledge_id_stores()

                if task.status == TaskStatusType.TODO.name:
                    # 未开始
                    await self.start_task(
                        task=task, knowledge_id_stores=knowledge_id_stores
                    )
                elif task.status == TaskStatusType.RUNNING.name:
                    # 已开始，有doc_id
                    await self.check_doc_sync_status(task=task)
                elif task.status == TaskStatusType.FAILED.name:
                    # 已开始，没有doc_id
                    await self.retry_task(
                        task=task, knowledge_id_stores=knowledge_id_stores
                    )
                else:
                    # 异常情况
                    self.end_task(
                        task=task, error_msg="task status is abnormal, force task end"
                    )
            except Exception as e:
                logger.error(f"auto_sync error, {str(e)}")

                self.end_task(
                    task=task, error_msg="auto sync error, force task end: " + str(e)
                )
            return True

    def check_active_threads(self):
        if threading.active_count() > 600:
            logger.warning(f"当前线程数： {threading.active_count()}, stop sync task! ")

            return False

        return True

    async def auto_refresh(self):
        logger.info(f"auto_refresh start {datetime.now()}")

        # 有running的任务，直接返回
        host = self.get_host_ip()
        records = self._refresh_record_dao.get_knowledge_refresh_records(
            query=KnowledgeRefreshRecordEntity(
                status=TaskStatusType.RUNNING.name, host=host
            ),
            page=1,
            page_size=1,
        )
        if records:
            logger.info(
                f"auto_refresh record {records[0].refresh_id} knowledge_id {records[0].knowledge_id} is running, break"
            )

            return True

        # 没有running的任务，捞一个任务执行
        records = self._refresh_record_dao.get_knowledge_refresh_records(
            query=KnowledgeRefreshRecordEntity(
                status=TaskStatusType.TODO.name, host=DEFAULT_EMPTY_HOST
            ),
            page=1,
            page_size=1,
        )
        if not records:
            logger.info("auto_refresh no knowledge space need to refresh")

            return True

        record = records[0]
        logger.info(
            f"auto_refresh start, refresh id is {record.refresh_id}, knowledge id is {record.knowledge_id}"
        )

        # 先锁定表数据
        record.host = host
        record.status = TaskStatusType.RUNNING.name
        record.gmt_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._refresh_record_dao.update_knowledge_refresh_records_batch(
            records=[record]
        )

        # 再启动保鲜
        knowledge_id = record.knowledge_id
        refresh_id = record.refresh_id
        refresh = await self.refresh_knowledge(
            knowledge_id=knowledge_id, refresh_id=refresh_id
        )
        if refresh:
            status = TaskStatusType.SUCCEED.name
        else:
            status = TaskStatusType.FINISHED.name

        # 查询最新的表记录(可能有错误信息)，再更新
        latest_records = self._refresh_record_dao.get_knowledge_refresh_records(
            query=KnowledgeRefreshRecordEntity(refresh_id=refresh_id)
        )
        if not latest_records:
            logger.error(
                f"auto_refresh record {record.refresh_id} knowledge_id {record.knowledge_id} is not exist, break"
            )

            return False
        latest_record = latest_records[0]
        latest_record.status = status
        self._refresh_record_dao.update_knowledge_refresh_records_batch(
            records=[latest_record]
        )
        logger.info(
            f"auto_refresh end, refresh id is {record.refresh_id}, knowledge id is {record.knowledge_id}"
        )

        return True

    def insert_unique_refresh_records(
        self, records: List[KnowledgeRefreshRecordEntity]
    ):
        logger.info(
            f"insert_unique_refresh_records start, records len is {len(records)}"
        )

        for record in records:
            # 只有在记录不存在时才插入
            exists = self._refresh_record_dao.check_record_exists(
                knowledge_id=record.knowledge_id, refresh_time=record.refresh_time
            )
            logger.info(
                f"insert_unique_refresh_records exists: {record.knowledge_id}, {record.refresh_time}, {exists}"
            )

            if not exists:
                try:
                    logger.info(
                        f"insert_unique_refresh_records insert record {record.refresh_id}, {record.knowledge_id}"
                    )

                    self._refresh_record_dao.create_knowledge_refresh_records(
                        records=[record]
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to insert record {record.refresh_id}, {record.knowledge_id} error: {e}"
                    )

    def init_refresh_records(self):
        logger.info(f"init_refresh_records start {datetime.now()}")

        # 查找需要保鲜的知识空间
        spaces = self._dao.get_knowledge_space(
            query=KnowledgeSpaceEntity(refresh="true")
        )
        if not spaces:
            logger.info(f"spaces is empty, no need to refresh, break")

            return True
        knowledge_ids = [space.knowledge_id for space in spaces if space.knowledge_id]
        logger.info(f"auto_refresh knowledge_ids {knowledge_ids} need to refresh !")

        # 把数据写入到保鲜记录表中
        records = []
        for knowledge_id in knowledge_ids:
            refresh_id = str(uuid.uuid4())
            refresh_time = datetime.now().strftime("%Y-%m-%d")
            status = TaskStatusType.TODO.name
            operator = REFRESH_OPERATOR
            host = DEFAULT_EMPTY_HOST
            records.append(
                KnowledgeRefreshRecordEntity(
                    refresh_id=refresh_id,
                    knowledge_id=knowledge_id,
                    host=host,
                    refresh_time=refresh_time,
                    status=status,
                    operator=operator,
                )
            )

        # 使用乐观锁机制插入数据
        self.insert_unique_refresh_records(records)

        return True

    def check_can_refresh(self):
        # 规则1: 保鲜记录都执行完成，不需要再进行保鲜
        records = self._refresh_record_dao.get_not_finished_refresh_records(
            ignore_status=[TaskStatusType.SUCCEED.name, TaskStatusType.FINISHED.name]
        )

        if not records:
            logger.info(
                "check_can_refresh refresh records is empty, no need to refresh"
            )

            return False
        logger.info(f"check_can_refresh records len is {len(records)}, need to refresh")

        return True

    async def auto_refresh_periodic(self, interval: Optional[int] = 60 * 1):
        logger.info(
            f"auto_refresh_periodic start {datetime.now()}, interval is {interval}"
        )

        # 每隔1分钟执行一次，直到处理完所有的保鲜任务
        while True:
            if self.check_can_refresh():
                await self.auto_refresh()
                await asyncio.sleep(interval)
                logger.info(f"auto_refresh_periodic sleep {interval} seconds")

                continue
            logger.info(f"auto_refresh_periodic end {datetime.now()}")

            break


    def get_refresh_hour(self):
        try:
            settings = self._settings_dao.get_settings(query=SettingsEntity(setting_key=REFRESH_HOUR))
            refresh_hour = int(settings[0].value) if settings else 0
        except Exception as e:
            logger.error(f"get_refresh_hour error: {str(e)}")
            refresh_hour = 0
        logger.info(f"run_refresh_task start query db: refresh hour is {refresh_hour}")

        return refresh_hour



    async def run_refresh_task(self):
        logger.info(f"run_refresh_task start {datetime.now()}")

        while True:
            refresh_hour = self.get_refresh_hour()
            now = datetime.now()
            next_run_time = now.replace(hour=refresh_hour, minute=0, second=0, microsecond=0)

            # 如果当前时间已经超过目标时间，则设置为明天同一时间
            if now >= next_run_time:
                next_run_time += timedelta(days=1)

            # 计算距离下次执行的秒数
            wait_seconds = (next_run_time - now).total_seconds()
            logger.info(f"auto_refresh_periodic wait hours is {wait_seconds/3600}h, next_run_time is {next_run_time}")

            # 等待至定时的时间点，然后直到全部保鲜完成
            await asyncio.sleep(wait_seconds)
            try:
                # 避免重复初始化
                self.init_refresh_records()

                # 重复执行，直到全部完成
                await self.auto_refresh_periodic()

            except Exception as e:
                logger.error(f"Refresh task failed, {str(e)}")

    async def run_periodic(self, interval: Optional[int] = 5):
        logger.info(f"run_periodic start, interval is {interval}")

        # 等待主程序运行成功再开启定时任务
        await asyncio.sleep(60)

        # 启动保鲜任务
        asyncio.create_task(self.run_refresh_task())

        while True:
            try:
                # 线程数过高 服务降级
                if self.check_active_threads():
                    await self.auto_sync()
                else:
                    logger.info("线程过多，进行线程信息dump")
                    from derisk_serve.utils.thread_util import dump_threads_to_file
                    dump_threads_to_file()
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

    async def init_auto_sync(self, interval: Optional[int] = 5):
        logger.info(f"init_auto_sync start, interval is {interval}")

        asyncio.create_task(self.run_periodic(interval=interval))

        logger.info(f"init_auto_sync end, interval is {interval}")
        return True

    def update_knowledge_task(self, request: KnowledgeTaskRequest):
        logger.info(f"update_knowledge_task start, request is {request}")

        if request.task_id is None:
            raise Exception("task_id is None")

        # query task
        tasks = self._task_dao.get_knowledge_tasks(
            query=KnowledgeTaskEntity(task_id=request.task_id)
        )
        if not tasks or len(tasks) != 1:
            raise Exception(f"task_id {request.task_id} can not be found")
        task = tasks[0]
        logger.info(
            f"update_knowledge_task task_id is {task.task_id}, task status is {task.status}"
        )

        # update task
        task.status = request.status if request.status else TaskStatusType.FINISHED.name

        return self._task_dao.update_knowledge_task_batch(tasks=[task])

    def build_knowledge_task_response(
        self,
        knowledge_id: str,
        tasks: List[KnowledgeTaskEntity],
        group_login: Optional[str] = None,
        book_slug: Optional[str] = None,
    ):
        logger.info(
            f"build_knowledge_task_response start, knowledge_id is {knowledge_id}, tasks len is {len(tasks)}"
        )

        total_tasks_count = len(tasks)
        succeed_tasks_count = 0
        running_tasks_count = 0
        failed_tasks_count = 0
        todo_tasks_count = 0
        last_task_operator = ""

        if not tasks:
            logger.info(f"build_knowledge_task_response tasks is None ")

            # 没有等待运行的任务，全部数据从doc表中获取
            all_docs = self._document_dao.get_documents_by_yuque(
                knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug
            )
            logger.info(f"get_yuque_knowledge_outlines all_docs len is {len(all_docs)}")

            for doc in all_docs:
                if doc.status == SyncStatus.FINISHED.name:
                    succeed_tasks_count += 1
                elif doc.status == SyncStatus.RUNNING.name:
                    running_tasks_count += 1
                elif doc.status == SyncStatus.TODO.name:
                    todo_tasks_count += 1
                else:
                    failed_tasks_count += 1
            # 这里不统计失败任务
            total_tasks_count = len(all_docs) - failed_tasks_count
            spaces = self._dao.get_knowledge_space_by_knowledge_ids(
                knowledge_ids=[knowledge_id]
            )
            if not spaces:
                raise Exception(f"knowledge_id {knowledge_id} can not be found")
            last_task_operator = spaces[0].owner
        else:
            for task in tasks:
                last_task_operator = task.owner
                if task.status == TaskStatusType.TODO.name:
                    todo_tasks_count += 1
                elif task.status in (
                    TaskStatusType.SUCCEED.name,
                    TaskStatusType.FINISHED.name,
                ):
                    succeed_tasks_count += 1
                else:
                    running_tasks_count += 1

        # update failed tasks
        failed_docs = self._document_dao.get_documents_by_yuque(
            knowledge_id=knowledge_id,
            group_login=group_login,
            book_slug=book_slug,
            status=TaskStatusType.FAILED.name,
        )
        failed_tasks_count = len(failed_docs)
        total_tasks_count += failed_tasks_count
        logger.info(
            f"build_knowledge_task_response failed_tasks_count is {failed_tasks_count}"
        )

        if total_tasks_count != (
            succeed_tasks_count
            + running_tasks_count
            + todo_tasks_count
            + failed_tasks_count
        ):
            logger.info(
                f"todo_tasks_count is {todo_tasks_count}, succeed_tasks_count is {succeed_tasks_count}, running_tasks_count is {running_tasks_count}, total_tasks_count {total_tasks_count}"
            )

            raise Exception("tasks count is not equal to total tasks count")

        # return result
        return KnowledgeTaskResponse(
            knowledge_id=knowledge_id,
            total_tasks_count=total_tasks_count,
            succeed_tasks_count=succeed_tasks_count,
            running_tasks_count=running_tasks_count,
            failed_tasks_count=failed_tasks_count,
            todo_tasks_count=todo_tasks_count,
            last_task_operator=last_task_operator,
        )

    def get_knowledge_task(self, knowledge_id: str):
        logger.info(f"get knowledge task knowledge_id is {knowledge_id}")

        if not knowledge_id:
            raise Exception("knowledge_id is None")

        # get all tasks
        tasks = self._task_dao.get_knowledge_tasks(
            query=KnowledgeTaskEntity(knowledge_id=knowledge_id),
            page=self._default_page,
            page_size=self._default_page_size,
        )
        logger.info(f"tasks len is {len(tasks)}")

        # build result
        knowledge_task_response = self.build_knowledge_task_response(
            knowledge_id=knowledge_id, tasks=tasks
        )
        logger.info(
            f"get knowledge task knowledge_id is {knowledge_id} {knowledge_task_response}"
        )

        return knowledge_task_response

    def get_knowledge_task_with_book_slug(
        self, knowledge_id: str, group_login: str, book_slug: str
    ):
        logger.info(
            f"get_knowledge_task_with_book_slug knowledge_id is {knowledge_id}, group_login is {group_login}, book_slug is {book_slug}"
        )

        if not knowledge_id:
            raise Exception("knowledge_id is None")
        if not group_login:
            raise Exception("group_login is None")
        if not book_slug:
            raise Exception("book_slug is None")

        # get all tasks
        tasks = self._task_dao.get_knowledge_tasks(
            query=KnowledgeTaskEntity(
                knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug
            ),
            page=self._default_page,
            page_size=self._default_page_size,
        )
        logger.info(f"tasks len is {len(tasks)}")

        # build result
        knowledge_task_response = self.build_knowledge_task_response(
            knowledge_id=knowledge_id,
            tasks=tasks,
            group_login=group_login,
            book_slug=book_slug,
        )
        logger.info(
            f"get_knowledge_task_with_book_slug knowledge_id is {knowledge_id} {knowledge_task_response}"
        )

        return knowledge_task_response

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

    def update_group_login_token_dict_offline(
        self, knowledge_id: str, group_login_token_dict: dict
    ):
        logger.info(
            f"update_group_login_token_dict_offline group_login_token_dict len is {len(group_login_token_dict.keys())}"
        )

        try:
            if not knowledge_id:
                return group_login_token_dict

            offline_tasks = self._task_dao.get_knowledge_tasks(
                query=KnowledgeTaskEntity(knowledge_id=knowledge_id),
                ignore_status=[
                    TaskStatusType.SUCCEED.name,
                    TaskStatusType.FINISHED.name,
                ],
                page=self._default_page,
                page_size=self._default_page_size,
            )
            if not offline_tasks:
                return group_login_token_dict

            offline_dict = {
                task.group_login: task.yuque_token
                for task in offline_tasks
                if task.yuque_token and task.group_login
            }

            update_group_login_token_dict_offline = group_login_token_dict
            for offline_group_login in offline_dict.keys():
                if (
                    offline_group_login
                    and offline_group_login not in group_login_token_dict.keys()
                ):
                    logger.info(f"update offline group {offline_group_login}")

                    update_group_login_token_dict_offline[offline_group_login] = (
                        offline_dict[offline_group_login]
                    )
            logger.info(
                f"update_group_login_token_dict_offline len is {len(offline_dict.keys())}"
            )

            return update_group_login_token_dict_offline
        except Exception as e:
            logger.error(f"update_group_login_token_dict_offline error {e}")

            return group_login_token_dict

    def get_group_login_token_dict(self, knowledge_id: str):
        logger.info(f"get_group_login_token_dict space_id: {knowledge_id}")
        start_time = timeit.default_timer()

        # get yuque docs
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(knowledge_id=knowledge_id)
        )

        # get dict
        group_login_token_dict = {
            yuque_doc.group_login: yuque_doc.token
            for yuque_doc in yuque_docs
            if yuque_doc.token is not None and yuque_doc.group_login is not None
        }

        # 增加离线目录
        group_login_token_dict = self.update_group_login_token_dict_offline(
            knowledge_id=knowledge_id, group_login_token_dict=group_login_token_dict
        )

        logger.info(
            f"group_login_token_dict: len is {len(group_login_token_dict.keys())} {group_login_token_dict}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"get_group_login_token_dict cost time is {cost_time} seconds")

        return group_login_token_dict

    def get_user_details_by_token(self, yuque_token: str):
        logger.info(f"show_yuque_group_knowledge yuque_token is {yuque_token}")

        web_reader = AntYuqueLoader(access_token=yuque_token)
        user_details = web_reader.get_user_details_by_token()

        return user_details

    def update_yuque_info(
        self,
        knowledge_id: str,
        group_login: str,
        group_name: str,
        token: str,
        token_type: str,
    ):
        logger.info(
            f"update_knowledge_yuque knowledge_id: {knowledge_id}, group_login: {group_login}, group_name: {group_name}, token_type: {token_type}"
        )
        start_time = timeit.default_timer()

        # get yuque docs
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(
                knowledge_id=knowledge_id, group_login=group_login, token=token
            )
        )

        # update yuque docs
        update_yuque_docs = []
        for yuque_doc in yuque_docs:
            yuque_doc.group_login_name = group_name
            yuque_doc.token_type = token_type
            update_yuque_docs.append(yuque_doc)

        updated_ids = self._yuque_dao.update_knowledge_yuque_batch(
            yuque_docs=update_yuque_docs
        )
        logger.info(f"update_yuque_info updated_ids: {updated_ids}")

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"update_yuque_info cost time is {cost_time} seconds")

        return updated_ids

    def find_group_name_by_user_id(
        self, user_id: str, group_login: str, yuque_user_token: str
    ):
        logger.info(
            f"find_group_name_by_user_id {user_id}, {group_login}, {yuque_user_token}"
        )

        # get user all group info
        web_reader = AntYuqueLoader(access_token=yuque_user_token)
        user_groups = web_reader.get_user_groups_by_token(user_id=user_id)
        group_login_name_dict = {
            group.get("login"): group.get("name") for group in user_groups
        }

        # find group login name
        group_name = group_login_name_dict.get(group_login)
        logger.info(f"find_group_name_by_user_id {user_id} {group_name}")

        return group_name

    def get_group_books(
        self,
        knowledge_id: str,
        group_login: str,
        yuque_token: str,
        book_details: [YuqueDocDetail],
    ) -> [YuqueGroupBook]:
        logger.info(f"get_group_books book_details len is: {len(book_details)}")
        start_time = timeit.default_timer()

        if len(book_details) == 0:
            logger.info(f"book_details len is: 0 ")

            return []

        # get group info
        user_details = self.get_user_details_by_token(yuque_token=yuque_token)
        if user_details is None:
            logger.error(f"can not found user info for {yuque_token}")

            raise Exception("获取用户group信息失败")

        if user_details.get("type") == "Group":
            # 团队空间授权token，获取group名字
            group_login = user_details.get("login")
            group_name = user_details.get("name")
        elif user_details.get("type") == "User":
            user_id = user_details.get("login")
            user_name = user_details.get("name")
            logger.info(f"find user info {user_id} {user_name}")

            # 用户空间授权token 获取group名字
            group_name = self.find_group_name_by_user_id(
                user_id=user_id, group_login=group_login, yuque_user_token=yuque_token
            )
        else:
            logger.error(
                f"not support type {user_details.get('type')} by token {yuque_token}"
            )

            raise Exception(
                "获取用户group信息失败, 不支持类型" + str(user_details.get("type"))
            )

        # update yuque table
        self.update_yuque_info(
            knowledge_id=knowledge_id,
            group_login=group_login,
            group_name=group_name,
            token=yuque_token,
            token_type=user_details.get("type"),
        )

        # get book info
        yuque_group_books = []
        for book_detail in book_details:
            yuque_group_book = YuqueGroupBook(
                book_slug=book_detail.book_slug,
                book_name=book_detail.name,
                group_login=group_login,
                group_name=group_name,
                knowledge_id=knowledge_id,
            )
            yuque_group_book.type = "TOKEN"
            yuque_group_books.append(yuque_group_book)
        logger.info(
            f"get_group_books yuque_group_books len is: {len(yuque_group_books)}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"get_group_books cost time is {cost_time} seconds")

        return yuque_group_books

    async def aget_group_books(
        self,
        knowledge_id: str,
        group_login,
        yuque_token: str,
        book_details: [YuqueDocDetail],
    ):
        return await blocking_func_to_async(
            self._system_app,
            self.get_group_books,
            knowledge_id,
            group_login,
            yuque_token,
            book_details,
        )

    def get_yuque_books_by_group_login(self, group_login: str, yuque_token: str):
        logger.info(
            f"get_yuque_books_by_group_login group_login: {group_login}, yuque_token: {yuque_token}"
        )
        get_books_start_time = timeit.default_timer()

        web_reader = AntYuqueLoader(access_token=yuque_token)

        # find all books with deep search
        books = web_reader.get_books_by_group_login(
            group_login=group_login, offset=0, page_size=100, temp_books=[]
        )

        get_books_end_time = timeit.default_timer()
        get_books_cost_time = round(get_books_end_time - get_books_start_time, 2)
        logger.info(
            f"get_yuque_books_by_group_login {group_login} cost time is {get_books_cost_time} seconds"
        )

        return books

    def update_book_slug_dict_offline(
        self, knowledge_id: str, group_login: str, book_slug_dict: dict
    ):
        logger.info(
            f"update_book_slug_dict_offline knowledge_id: {knowledge_id}, group_login: {group_login}, book_slug_dict len is : {len(book_slug_dict.keys())}"
        )

        try:
            if not knowledge_id or not group_login:
                return book_slug_dict

            offline_tasks = self._task_dao.get_knowledge_tasks(
                query=KnowledgeTaskEntity(
                    knowledge_id=knowledge_id, group_login=group_login
                ),
                ignore_status=[
                    TaskStatusType.SUCCEED.name,
                    TaskStatusType.FINISHED.name,
                ],
                page=self._default_page,
                page_size=self._default_page_size,
            )
            if not offline_tasks:
                return book_slug_dict

            for task in offline_tasks:
                book_slug = task.book_slug
                if book_slug and book_slug not in book_slug_dict.keys():
                    logger.info(f"update book slug {book_slug}")

                    book_slug_dict[book_slug] = group_login
            logger.info(
                f"update_book_slug_dict_offline len is {len(book_slug_dict.keys())}"
            )

            return book_slug_dict
        except Exception as e:
            logger.error(f"update_book_slug_dict_offline error: {e}")

            return book_slug_dict

    def filter_import_books(self, knowledge_id: str, group_login: str, books: dict):
        logger.info(
            f"filter_import_books space_id: {knowledge_id}, group_login is {group_login}, books len is: {len(books)}"
        )
        start_time = timeit.default_timer()

        # get import books dict
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(knowledge_id=knowledge_id)
        )
        book_slug_dict = {
            document.book_slug: document.group_login
            for document in yuque_docs
            if document.book_slug is not None
        }
        # 增加离线目录
        book_slug_dict = self.update_book_slug_dict_offline(
            knowledge_id=knowledge_id,
            group_login=group_login,
            book_slug_dict=book_slug_dict,
        )

        # filter
        import_books = [
            book for book in books if book.get("slug") in book_slug_dict.keys()
        ]
        logger.info(
            f"book_slug_dict is {len(book_slug_dict.keys())} import_books is {len(import_books)}"
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"filter_import_books cost time is {cost_time} seconds")

        return import_books

    def get_yuque_group_docs(
        self,
        knowledge_id: str,
        group_login: str,
        yuque_token: str,
        ignore_docs: bool = False,
    ):
        logger.info(
            f"show_yuque_group_knowledge space_id: {knowledge_id}, group_login: {group_login}, yuque_token: {yuque_token}, {ignore_docs}"
        )
        get_book_details_start_time = timeit.default_timer()

        # check params
        if group_login is None:
            raise Exception("group_login is None")
        if yuque_token is None:
            raise Exception("yuque_token is None")

        # get all books
        books = self.get_yuque_books_by_group_login(
            group_login=group_login, yuque_token=yuque_token
        )

        if knowledge_id is not None:
            logger.info("show import books")

            # filter import books
            books = self.filter_import_books(
                knowledge_id=knowledge_id, group_login=group_login, books=books
            )

        # get book info
        book_details = []
        for book in books:
            book_details.append(
                YuqueBookDetail(book_slug=book.get("slug"), name=book.get("name"))
            )

        get_book_details_end_time = timeit.default_timer()
        get_book_details_cost_time = round(
            get_book_details_end_time - get_book_details_start_time, 2
        )
        logger.info(
            f"get_yuque_group_docs {group_login} cost time is {get_book_details_cost_time} seconds"
        )
        logger.info(f"book details: {len(book_details)}")

        return book_details

    async def aget_yuque_group_docs(
        self,
        knowledge_id: str,
        group_login: str,
        yuque_token: str,
        ignore_docs: bool = False,
    ):
        return await blocking_func_to_async(
            self._system_app,
            self.get_yuque_group_docs,
            knowledge_id,
            group_login,
            yuque_token,
            ignore_docs,
        )

    async def get_single_group_books(
        self, knowledge_id: str, yuque_token: str, group_login: str
    ):
        start_time = timeit.default_timer()

        # get book info
        book_details = await self.aget_yuque_group_docs(
            knowledge_id=knowledge_id, group_login=group_login, yuque_token=yuque_token
        )

        # build group book info
        temp_group_books = await self.aget_group_books(
            knowledge_id=knowledge_id,
            group_login=group_login,
            yuque_token=yuque_token,
            book_details=book_details,
        )

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"get_single_group_books cost time is {cost_time} seconds")

        return temp_group_books

    async def get_texts_dir(self, knowledge_id: str, doc_type: str = None):
        logger.info(f"get_texts_dir knowledge_id is {knowledge_id}, doc_type is {doc_type}")

        texts = []
        try:
            if not doc_type:
                doc_type = KnowledgeType.TEXT.name
            docs = self._document_dao.get_knowledge_documents(query=KnowledgeDocumentEntity(knowledge_id=knowledge_id, doc_type=doc_type),
                                                              page=self._default_page, page_size=self._default_page_size)
            if not docs:
                logger.info(f"get_texts_dir docs is empty {knowledge_id}")

                return texts

            for doc in docs:
                if doc.status in [SyncStatus.FINISHED.name, SyncStatus.RUNNING.name, SyncStatus.EXTRACTING.name]:
                    texts.append(TextBook(doc_name=doc.doc_name, doc_id=doc.doc_id, status=doc.status))
        except Exception as e:
            logger.error(f"get_texts_dir error: {e}")

        logger.info(f"get_texts_dir texts is {texts}")

        return texts


    async def get_group_books_dir(self, knowledge_id: str):
        logger.info(f"get_group_books_dir knowledge_id is {knowledge_id}")

        group_books = []
        try:
            # get all yuque_token and group_login
            group_login_token_dict = self.get_group_login_token_dict(
                knowledge_id=knowledge_id
            )

            if len(group_login_token_dict.keys()) != 0:
                # get group books
                tasks = [
                    self.get_single_group_books(
                        knowledge_id=knowledge_id,
                        yuque_token=group_login_token_dict[group_login],
                        group_login=group_login,
                    )
                    for group_login in group_login_token_dict.keys()
                ]
                results = await asyncio.gather(*tasks)
                for result in results:
                    group_books.extend(result)
        except Exception as e:
            logger.error(f"get_group_books_dir error: {e}")

        logger.info(f"get_group_books_dir group_books is {group_books}")

        return group_books


    async def get_yuque_dir(self, knowledge_id: str):
        logger.info(f"get_yuque_dir space_id: {knowledge_id}")
        start_time = timeit.default_timer()

        if knowledge_id is None:
            raise Exception("space_id is None")

        tasks = [
            self.get_group_books_dir(knowledge_id=knowledge_id),
            self.get_texts_dir(knowledge_id=knowledge_id, doc_type=KnowledgeType.TEXT.name),
            self.get_texts_dir(knowledge_id=knowledge_id, doc_type=KnowledgeType.DOCUMENT.name)
        ]
        group_books, texts, files = await asyncio.gather(*tasks)

        # build response
        yuque_dir_detail = YuqueDirDetail(qas=[], group_books=group_books, texts=texts, files=files)

        end_time = timeit.default_timer()
        cost_time = round(end_time - start_time, 2)
        logger.info(f"get_yuque_dir cost time is {cost_time} seconds")

        return yuque_dir_detail


    def get_all_yuque_docs_by_group_and_book(self, group_login: str, book_slug: str, yuque_token: str):
        logger.info(f"get_all_yuque_docs_by_group_and_book group_login: {group_login}, book_slug: {book_slug}")

        # get tocs
        web_reader = AntYuqueLoader(access_token=yuque_token)
        table_of_contents = web_reader.get_toc_by_group_login_and_book_slug(
            group_login=group_login, book_slug=book_slug
        )

        # build response
        yuque_doc_details = []
        for toc in table_of_contents:
            doc_slug = toc.get("slug") if toc.get("child_uuid") == "" else toc.get("uuid")
            yuque_doc_detail = YuqueDocDetail(
                child_doc_slug=toc.get("child_uuid"),
                doc_slug=doc_slug,
                parent_doc_slug=toc.get("parent_uuid"),
                prev_doc_slug=toc.get("prev_uuid"),
                sibling_doc_slug=toc.get("sibling_uuid"),
                title=toc.get("title"),
                type=toc.get("type"),
            )
            yuque_doc_details.append(yuque_doc_detail)
        logger.info(f"get_all_yuque_docs_by_group_and_book yuque_doc_details len is {len(yuque_doc_details)}")

        return yuque_doc_details


    def build_yuque_book_details(self, books, group_login, yuque_token):
        start_time = timeit.default_timer()
        book_details = []
        futures = []

        # 创建线程池并提交任务
        with ThreadPoolExecutor() as executor:
            for idx, book in enumerate(books):
                book_slug = book.get("slug")
                future = executor.submit(
                    self.get_all_yuque_docs_by_group_and_book,
                    group_login=group_login,
                    book_slug=book_slug,
                    yuque_token=yuque_token
                )
                # 存储 future 和对应的 book 信息
                futures.append((idx, future, book))

        # 按原始顺序收集结果
        for idx, future, book in sorted(futures, key=lambda x: x[0]):
            docs = future.result()
            book_details.append(
                YuqueBookDetail(
                    book_slug=book.get("slug"),
                    name=book.get("name"),
                    docs=docs
                )
            )
        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(f"build_yuque_book_details cost time is {cost_time} seconds, book_details len is {len(book_details)}")

        return book_details

    async def get_book_dir(self, knowledge_id: str, group_login: str, yuque_token: str):
        logger.info(f"get_book_dir knowledge_id is {knowledge_id}")
        start_time = timeit.default_timer()

        # find all books with deep search
        web_reader = AntYuqueLoader(access_token=yuque_token)
        books = web_reader.get_books_by_group_login(
            group_login=group_login, offset=0, page_size=100, temp_books=[]
        )
        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(f"get_book_dir books len is {len(books)}, cost time is {cost_time} seconds")

        # build book details
        return self.build_yuque_book_details(books, group_login, yuque_token)


    def get_import_doc_uuid_dict(self, knowledge_id: str):
        logger.info(f"get_import_doc_slug_dict knowledge_id is {knowledge_id}")

        # get yuque docs
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(knowledge_id=knowledge_id)
        )

        # get doc_id dict
        doc_ids = [doc.doc_id for doc in yuque_docs if doc.doc_id is not None]
        docs = self._document_dao.get_documents(
            query=KnowledgeDocumentEntity(id=None), doc_ids=doc_ids
        )
        doc_id_dict = {doc.doc_id: doc for doc in docs if doc.doc_id is not None}

        if not doc_id_dict:
            return {}

        # get doc_uuid dict
        import_doc_uuid_dict = {
            yuque_doc.doc_uuid: doc_id_dict[yuque_doc.doc_id]
            for yuque_doc in yuque_docs
            if yuque_doc.doc_id in doc_id_dict.keys()
        }
        logger.info(f"import_doc_uuid_dict is {import_doc_uuid_dict}")

        return import_doc_uuid_dict

    def update_doc_sync_info_dict(
        self,
        group_login: str,
        book_slug: str,
        import_doc_uuid_dict: dict,
        toc: dict,
        import_doc_uuid_knowledge_tasks: Optional[dict] = None,
    ):
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

        if import_doc_uuid_knowledge_tasks:
            logger.info(
                f"update_doc_sync_info_dict offline tasks len is {len(import_doc_uuid_knowledge_tasks.keys())}"
            )

            if doc_uuid in import_doc_uuid_knowledge_tasks.keys():
                logger.info(
                    f"update_doc_sync_info_dict find doc_uuid in knowledge_task {doc_uuid}, {import_doc_uuid_knowledge_tasks[doc_uuid].task_id}"
                )

                doc_sync_info_dict["selected"] = True
                doc_sync_info_dict["file_status"] = "todo"
                doc_sync_info_dict["progress"] = "0"

        return doc_sync_info_dict

    def create_yuque_doc_detail(
        self,
        group_login: str,
        book_slug: str,
        import_doc_uuid_dict: dict,
        toc: dict,
        import_doc_uuid_knowledge_tasks: Optional[dict] = None,
    ):
        # update status dict
        doc_sync_info_dict = self.update_doc_sync_info_dict(
            group_login=group_login,
            book_slug=book_slug,
            import_doc_uuid_dict=import_doc_uuid_dict,
            toc=toc,
            import_doc_uuid_knowledge_tasks=import_doc_uuid_knowledge_tasks,
        )

        if toc.get("child_uuid") == "":
            doc_slug = toc.get("slug")
        else:
            doc_slug = toc.get("uuid")

        # return response
        return YuqueDocDetail(
            child_doc_slug=toc.get("child_uuid"),
            doc_slug=doc_slug,
            file_id=doc_sync_info_dict.get("file_id"),
            file_status=doc_sync_info_dict.get("file_status"),
            parent_doc_slug=toc.get("parent_uuid"),
            prev_doc_slug=toc.get("prev_uuid"),
            progress=doc_sync_info_dict.get("progress"),
            selected=doc_sync_info_dict.get("selected"),
            sibling_doc_slug=toc.get("sibling_uuid"),
            title=toc.get("title"),
            type=toc.get("type"),
        )

    def get_import_doc_uuid_knowledge_tasks(
        self,
        knowledge_id: str,
        group_login: str,
        book_slug: str,
        table_of_contents: Optional[Any] = None,
    ) -> dict:
        logger.info(
            f"get_import_doc_uuid_knowledge_tasks knowledge_id: {knowledge_id}, group_login: {group_login}, book_slug: {book_slug}"
        )

        if knowledge_id is None:
            raise Exception("knowledge_id is None")
        if group_login is None:
            raise Exception("group_login is None")
        if book_slug is None:
            raise Exception("book_slug is None")

        # 获取doc_slug 和 doc_uuid的映射关系 (有重复的数据)
        doc_slug_uuid_dict = {
            toc.get("slug"): toc.get("uuid")
            for toc in table_of_contents
            if toc.get("type") == "DOC" and toc.get("slug") is not None
        }

        # 从任务表获取离线的导入任务, 过滤掉已经同步过的
        tasks = self._task_dao.get_knowledge_tasks(
            query=KnowledgeTaskEntity(
                knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug
            ),
            ignore_status=[
                TaskStatusType.SUCCEED.name,
                TaskStatusType.FINISHED.name,
                TaskStatusType.RUNNING.name,
            ],
            page=self._default_page,
            page_size=self._default_page_size,
        )
        logger.info(
            f"get_import_doc_uuid_knowledge_tasks tasks len is {len(tasks)}, doc_slug_uuid_dict len is {len(doc_slug_uuid_dict.keys())}"
        )

        import_doc_uuid_knowledge_tasks = {}
        for task in tasks:
            if task.yuque_doc_id in doc_slug_uuid_dict.keys():
                doc_uuid = doc_slug_uuid_dict[task.yuque_doc_id]

                import_doc_uuid_knowledge_tasks[doc_uuid] = task
            else:
                logger.info(
                    f"get_doc_uuid_from_task doc_uuid is None {task.task_id}, {task.yuque_doc_id}"
                )
        logger.info(
            f"get_import_doc_uuid_knowledge_tasks dict len is {len(import_doc_uuid_knowledge_tasks.keys())}"
        )

        return import_doc_uuid_knowledge_tasks

    def get_yuque_doc_details_by_book(
        self,
        knowledge_id: Optional[str] = None,
        group_login: str = None,
        book_slug: str = None,
        yuque_token: str = None,
    ):
        logger.info(
            f"get_yuque_doc_details_by_book group_login: {group_login}, book_slug: {book_slug}, yuque_token: {yuque_token}"
        )
        get_toc_start_time = timeit.default_timer()

        if group_login is None:
            raise Exception("group_login is None")
        if book_slug is None:
            raise Exception("book_slug is None")
        if yuque_token is None:
            raise Exception("yuque_token is None")

        # get tocs
        web_reader = AntYuqueLoader(access_token=yuque_token)
        table_of_contents = web_reader.get_toc_by_group_login_and_book_slug(
            group_login=group_login, book_slug=book_slug
        )

        # get import doc slug dict
        if knowledge_id is None:
            knowledge_id = ""
        import_doc_uuid_dict = self.get_import_doc_uuid_dict(knowledge_id=knowledge_id)

        # get import doc uuid by offline knowledge tasks
        import_doc_uuid_knowledge_tasks = self.get_import_doc_uuid_knowledge_tasks(
            knowledge_id=knowledge_id,
            group_login=group_login,
            book_slug=book_slug,
            table_of_contents=table_of_contents,
        )

        yuque_doc_details = []
        for toc in table_of_contents:
            yuque_doc_detail = self.create_yuque_doc_detail(
                group_login,
                book_slug,
                import_doc_uuid_dict,
                toc,
                import_doc_uuid_knowledge_tasks,
            )
            yuque_doc_details.append(yuque_doc_detail)

        get_toc_end_time = timeit.default_timer()
        get_toc_cost_time = round(get_toc_end_time - get_toc_start_time, 2)
        logger.info(
            f"get_yuque_doc_details_by_book {group_login} {book_slug} cost time is {get_toc_cost_time} seconds"
        )
        logger.info(
            f"get_yuque_doc_details_by_book yuque_doc_details is {len(yuque_doc_details)}"
        )

        return yuque_doc_details

    def get_yuque_token_by_knowledge_id_offline(
        self, knowledge_id: str, group_login: str
    ):
        logger.info(
            f"get_yuque_token_by_knowledge_id_offline knowledge_id is {knowledge_id}, group_login is {group_login}"
        )

        try:
            tasks = self._task_dao.get_knowledge_tasks(
                query=KnowledgeTaskEntity(
                    knowledge_id=knowledge_id, group_login=group_login
                ),
                ignore_status=[
                    TaskStatusType.SUCCEED.name,
                    TaskStatusType.FINISHED.name,
                ],
                page=self._default_page,
                page_size=self._default_page_size,
            )
            if not tasks:
                return None

            token = tasks[0].yuque_token
            logger.info(f"get_yuque_token_by_knowledge_id_offline token is {token}")

            return token
        except Exception as e:
            logger.info(f"get_yuque_token_by_knowledge_id_offline exception is {e}")

            return None

    def get_yuque_book_docs(self, knowledge_id: str, group_login: str, book_slug: str):
        logger.info(
            f"get_yuque_book_docs knowledge_id: {knowledge_id}, group_login: {group_login}, book_slug: {book_slug}"
        )

        # get yuque token
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(
                knowledge_id=knowledge_id,
                group_login=group_login,

            )
        )

        if yuque_docs and yuque_docs[0].token:
            yuque_token = yuque_docs[0].token
        else:
            # 更新离线token
            yuque_token = self.get_yuque_token_by_knowledge_id_offline(
                knowledge_id=knowledge_id, group_login=group_login
            )
        if not yuque_token:
            logger.info(
                f"get_yuque_book_docs yuque_token is None: {knowledge_id} {group_login}"
            )

            raise Exception(
                f"not find yuque_token {knowledge_id} {group_login} with online and offline data"
            )

        yuque_doc_details = self.get_yuque_doc_details_by_book(
            knowledge_id=knowledge_id,
            group_login=group_login,
            book_slug=book_slug,
            yuque_token=yuque_token,
        )
        logger.info(f"yuque_doc_details len is {len(yuque_doc_details)}")

        return yuque_doc_details

    async def adelete_document_by_doc_id(
        self, knowledge_id: str, doc_id: str, knowledge_id_store: Optional[Any] = None
    ):
        return await blocking_func_to_async(
            self._system_app,
            self.delete_document_by_doc_id,
            knowledge_id,
            doc_id,
            knowledge_id_store,
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

    def delete_document_by_doc_id(
        self, knowledge_id: str, doc_id: str, knowledge_id_store: Optional[Any] = None
    ):
        logger.info(f"delete_document_by_doc_id {knowledge_id} {doc_id}")

        # get document
        document = self.get_document_by_doc_id(knowledge_id=knowledge_id, doc_id=doc_id)
        if document is None:
            return True

        # delete vector_id
        vector_ids = document.vector_ids
        if vector_ids:
            if knowledge_id_store is None:
                knowledge_id_store = self.get_or_update_knowledge_id_store(
                    knowledge_id=knowledge_id
                )

            vector_store_connector = knowledge_id_store
            vector_store_connector.delete_by_ids(vector_ids)

        # delete chunks
        self._chunk_dao.raw_delete(doc_id=doc_id)

        # delete yuque docs
        self._yuque_dao.raw_delete(query=KnowledgeYuqueEntity(doc_id=doc_id))

        # delete document
        return self._document_dao.raw_delete(KnowledgeDocumentEntity(doc_id=doc_id))

    async def delete_document_by_space_id(
        self, knowledge_id: str, knowledge_id_store: Optional[Any] = None
    ):
        logger.info(
            f"delete_document_by_space_id {knowledge_id}, knowledge_id_store is {knowledge_id_store}"
        )

        # get document
        document_query = KnowledgeDocumentEntity(knowledge_id=knowledge_id)
        documents = self._document_dao.get_documents(document_query)
        doc_ids = [doc.doc_id for doc in documents]

        tasks = [
            self.adelete_document_by_doc_id(
                knowledge_id=knowledge_id,
                doc_id=doc_id,
                knowledge_id_store=knowledge_id_store,
            )
            for doc_id in doc_ids
        ]
        results = await asyncio.gather(*tasks)
        for result in results:
            logger.info(f"delete_document_by_doc_id {result}")

        return True

    def get_or_update_knowledge_id_store(self, knowledge_id: str):
        logger.info(
            f"get_or_update_knowledge_id_store {knowledge_id}, 当前线程数：{threading.active_count()}"
        )

        if knowledge_id is None:
            raise Exception("knowledge_id is required")

        if (
            self._knowledge_id_stores is None
            or knowledge_id not in self._knowledge_id_stores.keys()
        ):
            logger.info(
                f"update knowledge_id_stores {self._knowledge_id_stores}, len is {len(self._knowledge_id_stores.keys())}"
            )

            # update knowledge_id_stores
            self._knowledge_id_stores[knowledge_id] = self._get_vector_connector(
                knowledge_id=knowledge_id
            )

        knowledge_id_store = self._knowledge_id_stores[knowledge_id]

        return knowledge_id_store

    async def delete_documents(
        self, knowledge_id: Optional[str] = None, doc_id: Optional[str] = None
    ):
        logger.info(
            f"delete_documents knowledge_id is {knowledge_id} doc_id is {doc_id}, 当前线程数：{threading.active_count()}"
        )

        knowledge_id_store = self.get_or_update_knowledge_id_store(
            knowledge_id=knowledge_id
        )
        if doc_id is None:
            await self.delete_document_by_space_id(
                knowledge_id=knowledge_id, knowledge_id_store=knowledge_id_store
            )
        else:
            await self.adelete_document_by_doc_id(
                knowledge_id=knowledge_id,
                doc_id=doc_id,
                knowledge_id_store=knowledge_id_store,
            )
        logger.info(
            f"delete_documents end knowledge_id is {knowledge_id} doc_id is {doc_id}, 当前线程数：{threading.active_count()}"
        )

    async def delete_yuque_knowledge(
        self,
        knowledge_id: Optional[str] = None,
        request: Optional[KnowledgeDocumentRequest] = None,
    ):
        # find yuque doc_id
        yuque_url = f"{BASE_YUQUE_URL}/{request.yuque_group_login}/{request.yuque_book_slug}/{request.yuque_doc_slug}"
        docs = self._document_dao.get_documents(
            query=KnowledgeDocumentEntity(knowledge_id=knowledge_id, content=yuque_url)
        )
        if docs is None or len(docs) == 0:
            logger.info(f"not found doc by yuque_url {yuque_url}")

            return True
        doc_id = docs[0].doc_id

        # delete
        return await self.adelete_document_by_doc_id(
            knowledge_id=knowledge_id, doc_id=doc_id
        )

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

        # filter
        yuque_url = f"{BASE_YUQUE_URL}/{request.yuque_group_login}/{request.yuque_book_slug}/{request.yuque_doc_slug}"

        doc_ids = [
            doc.doc_id
            for doc in documents
            if doc.doc_type == KnowledgeType.YUQUEURL.name and doc.content == yuque_url
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


    def get_extract_image_from_doc_params(self, doc_params: str):
        extract_image = False
        try:
            if doc_params:
                extract_image = json.loads(doc_params).get("extract_image", False)
        except Exception as e:
            logger.error(f"get_extract_image_from_doc_params error {e}")

        return extract_image

    async def split_yuque_knowledge(self, request: YuqueRequest):
        logger.info(f"split_yuque_knowledge start, {request}")

        knowledge_id = request.knowledge_id
        doc_id = request.doc_id

        if knowledge_id is None:
            raise Exception("knowledge_id is required")
        if doc_id is None:
            raise Exception("doc_id is required")

        # get document
        document = self.get_document_by_doc_id(knowledge_id=knowledge_id, doc_id=doc_id)

        if document is None:
            logger.info(f"document is None, {doc_id}")

            return True

        # delete vector_id
        if document.vector_ids is not None:
            vector_store_connector = self.get_or_update_knowledge_id_store(
                knowledge_id=knowledge_id
            )
            vector_store_connector.delete_by_ids(document.vector_ids)

        # delete chunks
        self._chunk_dao.raw_delete(doc_id)

        if document.doc_type == KnowledgeType.YUQUEURL.name:
            # get yuque doc uuid
            yuque_docs = self._yuque_dao.get_knowledge_yuque(
                query=KnowledgeYuqueEntity(doc_id=doc_id)
            )
            if yuque_docs is None or len(yuque_docs) == 0:
                logger.error(f"yuque docs not found, {doc_id}")

                raise Exception("yuque docs not found by " + doc_id)

            yuque_doc_uuid = yuque_docs[0].doc_uuid
            request.yuque_doc_uuid = yuque_doc_uuid

            # delete yuque docs
            self._yuque_dao.raw_delete(query=KnowledgeYuqueEntity(doc_id=doc_id))
        elif document.doc_type == KnowledgeType.DOCUMENT.name or document.doc_type == KnowledgeType.TEXT.name:
            logger.info(f"split_yuque_knowledge support {document.doc_type}")
        else:
            logger.error(f"document type not support, {doc_id}")

            raise Exception(f"document type not support {document.doc_type}")

        # update doc status
        document.status = SyncStatus.TODO.name
        self._document_dao.update_knowledge_document(document)

        # async run
        request.knowledge_id = knowledge_id

        # 获取是否解析图片语义变量
        extract_image = self.get_extract_image_from_doc_params(document.doc_params)
        request.extract_image = extract_image

        await self.sync_document(requests=[request])
        logger.info(f"split_yuque_knowledge success {doc_id}")

        return True

    def remove_html_tags(self, text: str):
        try:
            # 移除html标签
            cleaned_text = re.sub(r"<[^>]+>", "", text)

            # 移除超链接
            match = re.search(r"\[.*?\]\(.*?\)(.*)", cleaned_text)
            if match:
                cleaned_text = match.group(1)

            # 移除多余的空格
            cleaned_text = cleaned_text.strip()
            logger.info(
                f"remove_html_tags text is {text}, cleaned_text is {cleaned_text}"
            )

            return cleaned_text
        except Exception as e:
            logger.error(f"remove_html_tags error: text is {text}, {str(e)}")

            return ""

    def get_header_split(self, doc_id: str):
        # check is_header_split
        docs = self._document_dao.get_documents(
            query=KnowledgeDocumentEntity(doc_id=doc_id)
        )
        if docs is None or len(docs) != 1:
            logger.error(f"get_header_split doc is None or more than one {doc_id}")

            raise Exception("get_header_split doc error")
        doc = docs[0]
        chunk_params = json.loads(doc.chunk_params)
        is_header_split = False
        if chunk_params:
            chunk_strategy = chunk_params.get("chunk_strategy")
            if chunk_strategy and (
                chunk_strategy == ChunkStrategy.CHUNK_BY_MARKDOWN_HEADER.name
                or chunk_strategy == "Automatic"
            ):
                logger.info(f"get_chunks chunk_strategy is {chunk_strategy}")

                is_header_split = True
        logger.info(f"get_header_split is_header_split is {is_header_split}")

        return is_header_split

    def get_chunks_by_outline(self, knowledge_id: str, doc_id: str, outline: str):
        # get filter chunks
        chunks = self.get_chunks(
            request=ChunkEditRequest(
                doc_id=doc_id, knowledge_id=knowledge_id, first_level_header=outline
            )
        )

        chunk_ids = [str(chunk.chunk_id) for chunk in chunks]
        logger.info(f"get_chunks_by_outline chunk_ids is {len(chunk_ids)}")

        return chunk_ids

    def get_yuque_knowledge_outlines(self, knowledge_id: str, doc_id: str):
        start_time = timeit.default_timer()
        logger.info(f"get_yuque_knowledge_outlines start, {knowledge_id} {doc_id}")

        if knowledge_id is None or doc_id is None:
            raise Exception(
                "knowledge_id and doc_id is required: " + knowledge_id + " " + doc_id
            )

        # get yuque info
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(doc_id=doc_id, knowledge_id=knowledge_id)
        )
        if yuque_docs is None or len(yuque_docs) == 0:
            logger.error(f"yuque document is None, {doc_id}")

            raise Exception("yuque document not found by " + doc_id)
        yuque_doc = yuque_docs[0]

        # get outlines
        web_reader = AntYuqueLoader(access_token=yuque_doc.token)
        outlines = web_reader.get_outlines_by_group_book_slug(
            group_login=yuque_doc.group_login,
            book_slug=yuque_doc.book_slug,
            doc_slug=yuque_doc.doc_slug,
        )
        logger.info(f"get_yuque_knowledge_outlines outlines is {outlines}")

        # filter headers 1
        is_header_split = self.get_header_split(doc_id=doc_id)

        yuque_outlines = YuqueOutlines(is_header_split=is_header_split)

        if is_header_split is False:
            logger.info("get_yuque_knowledge_outlines is_header_split is False, return")

            yuque_outlines.outline_chunks = []
            return yuque_outlines

        def process_outline(outline):
            outline_cleaned = self.remove_html_tags(outline)
            chunks = self.get_chunks_by_outline(
                knowledge_id=knowledge_id, doc_id=doc_id, outline=outline_cleaned
            )

            return OutlineChunk(first_level_header=outline_cleaned, chunks=chunks)

        # 并行处理
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 过滤标题为空或者空字符串
            outlines = [outline for outline in outlines.keys() if outline]
            outline_chunks = list(executor.map(process_outline, outlines))

        # 过滤掉标题下面chunks为空的情况
        outline_chunks = [
            outline_chunk
            for outline_chunk in outline_chunks
            if len(outline_chunk.chunks) > 0
        ]

        yuque_outlines.outline_chunks = outline_chunks

        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(
            f"get_yuque_knowledge_outlines yuque_outlines is {yuque_outlines}, cost time is {cost_time} seconds"
        )

        return yuque_outlines

    def delete_yuque_book(self, knowledge_id: str, group_login: str, book_slug: str):
        # get yuque doc_id
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(
                knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug
            )
        )
        if not yuque_docs:
            raise Exception(f"yuque books {book_slug} can not be found")
        logger.info(f"yuque docs len is {len(yuque_docs)} ")

        knowledge_id_store = self.get_or_update_knowledge_id_store(
            knowledge_id=knowledge_id
        )

        # delete yuque doc id
        def task(yuque_doc):
            return self.delete_document_by_doc_id(
                knowledge_id=knowledge_id,
                doc_id=yuque_doc.doc_id,
                knowledge_id_store=knowledge_id_store,
            )

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(task, yuque_doc): yuque_doc for yuque_doc in yuque_docs
            }

            for future in as_completed(futures):
                future.result()

        return True

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
    
    
    def get_doc_sync_strategy(
        self, doc_id: Optional[str] = None
    ):
        logger.info(f"get_doc_strategy {doc_id}")

        # get all strategies
        chunk_strategies = self.get_all_chunk_strategies()

        # get doc strategy from db
        doc_strategy = DEFAULT_CHUNK_STRATEGY
        docs = self._document_dao.get_knowledge_documents(query=KnowledgeDocumentEntity(doc_id=doc_id))
        if not docs:
            logger.error(f"get_doc_strategy doc {doc_id} is None, use default strategy")
        else:
            doc = docs[0]
            chunk_params = self.convert_to_chunk_parameters(doc.chunk_params)
            doc_strategy = chunk_params.chunk_strategy if chunk_params.chunk_strategy else DEFAULT_CHUNK_STRATEGY
        logger.info(f"get_doc_strategy doc strategy is {doc_strategy}")

        # filter by doc strategy
        doc_strategy_detail = self.get_default_strategy_detail()
        if doc_strategy:
            for strategy_detail in chunk_strategies:
                if strategy_detail.strategy == doc_strategy:
                    logger.info(f"find doc strategy {doc_strategy} in chunk strategies {strategy_detail}")

                    doc_strategy_detail = strategy_detail
                    break
        logger.info(f"doc_strategy_detail is {strategy_detail}")

        return doc_strategy_detail
    


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
            self._system_app,
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
            self._system_app, self.get_chunk_id_dict_by_space_id, knowledge_id
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
            self._system_app, self.get_doc_id_dict, knowledge_id
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
        yuque_url = meta_data.get("yuque_url") if meta_data is not None else ""
        doc_type = KnowledgeType.YUQUEURL.name if yuque_url else KnowledgeType.TEXT
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
            yuque_url=yuque_url,
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

    def get_header_from_meta_data(self, meta_data: dict):
        logger.info(f"get_header_from_meta_data request is: {meta_data}")

        if not meta_data:
            return None

        header = None
        header_keys = [f"Header{i}" for i in range(1, 8)]
        # 找到一个即返回
        for key in header_keys:
            header = meta_data.get(key)
            if header is not None:
                logger.info(f"get_header_from_meta_data find header is {header}")

                break
        logger.info(f"get_header_from_meta_data end header is {header}")

        return header

    def get_chunks(self, request: ChunkEditRequest):
        logger.info(f"get_chunks request is:{request}")

        if request.knowledge_id is None:
            raise Exception("knowledge_id is required")

        if request.doc_id is None:
            raise Exception("doc_id is required")

        # get chunks
        chunk_responses = self._chunk_dao.get_list(
            {"knowledge_id": request.knowledge_id, "doc_id": request.doc_id}
        )

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
                header = self.get_header_from_meta_data(meta_data=meta_data)
                if header is not None and request.first_level_header in header:
                    logger.info(
                        f"get chunks first_level_header success: {header}, {request.first_level_header}"
                    )

                    filter_chunks.append(chunk)
            chunk_responses = filter_chunks
        logger.info(
            f"chunks size is {len(chunk_responses)}, filter size is {len(filter_chunks)}, is_header_split is {is_header_split}"
        )

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

        vector_store_connector = self.get_or_update_knowledge_id_store(
            knowledge_id=doc.knowledge_id
        )
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
        # entity.chunk_id = chu
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
            meta_data = json.loads(entity.meta_data) if entity.meta_data else {}
            for tag in request.tags:
                if tag.get("name") in meta_data:
                    meta_data[tag.get("name")] = tag.get("value")
            entity.meta_data = json.dumps(meta_data, ensure_ascii=False)
            entity.tags = json.dumps(request.tags, ensure_ascii=False)

        if request.questions is not None:
            # 添加问题
            if len(request.questions) == 0:
                request.questions = ""
            questions = [
                remove_trailing_punctuation(question) for question in request.questions
            ]
            entity.questions = json.dumps(questions, ensure_ascii=False)

        if (request.content is None or request.content == entity.content) and not request.tags:
            logger.info(f"content is null or content is not modify: {entity.content}")
        else:
            logger.info(f"content is modify: {entity.content}")

            entity = self.update_chunk_content(entity=entity, request=request)

        self._chunk_dao.update_chunk(entity)
        logger.info(f"update chunk success {entity.chunk_id}")

        return True

    def delete_chunk(self, request: ChunkEditRequest):
        logger.info("delete chunk request is {request}")

        if not request.knowledge_id:
            raise Exception("knowledge_id is required")
        if not request.chunk_id:
            raise Exception("chunk_id is required")

        # find chunk
        chunks = self._chunk_dao.get_document_chunks(
            query=DocumentChunkEntity(chunk_id=request.chunk_id)
        )
        if not chunks:
            raise Exception(f"chunk {request.chunk_id} is not existed")

        chunk = chunks[0]
        # delete vector
        if chunk.vector_id:
            vector_store_connector = self.get_or_update_knowledge_id_store(
                knowledge_id=request.knowledge_id
            )

            # delete vector by ids
            vector_store_connector.delete_by_ids(chunk.vector_id)

        # delete chunk
        self._chunk_dao.delete_chunk(chunk_id=request.chunk_id)

        return True

    def find_version_from_yuque_info(
        self, token: str, group_login: str, book_slug: str, doc_slug: str
    ):
        logger.info(
            f"find_version_from_yuque_info token is {token}, group_login is {group_login}, book_slug is {book_slug}, doc_slug is {doc_slug}"
        )

        if not token:
            raise Exception("token is required")
        if not group_login:
            raise Exception("group_login is required")
        if not book_slug:
            raise Exception("book_slug is required")
        if not doc_slug:
            raise Exception("doc_slug is required")

        yuque_url = f"{BASE_YUQUE_URL}/{group_login}/{book_slug}/{doc_slug}"
        doc_detail = self.get_yuque_doc_form_url(yuque_url=yuque_url, yuque_token=token)
        if not doc_detail or not doc_detail.get("latest_version_id"):
            return None
        latest_version_id = str(doc_detail.get("latest_version_id"))
        logger.info(f"find_version_from_yuque_info result is {latest_version_id}")

        return latest_version_id

    async def refresh_single_doc(self, knowledge_id: str, doc_id: str):
        if not knowledge_id:
            raise Exception("knowledge_id is required")
        if not doc_id:
            raise Exception("doc_id is required")

        # doc_id 不变，内容重新切分，版本更新
        refresh = await self.split_yuque_knowledge(
            request=YuqueRequest(knowledge_id=knowledge_id, doc_id=doc_id)
        )

        logger.info(f"refresh_single_doc result is {refresh}")
        return refresh

    async def refresh_doc_id(self, knowledge_id: str, doc_id: str):
        logger.info(
            f"refresh_doc_id knowledge_id is {knowledge_id}, doc_id is {doc_id}"
        )

        if not knowledge_id:
            raise Exception("knowledge_id is required")
        if not doc_id:
            raise Exception("doc_id is required")

        # find yuque url latest_version_id
        yuque_docs = self._yuque_dao.get_knowledge_yuque(
            query=KnowledgeYuqueEntity(knowledge_id=knowledge_id, doc_id=doc_id)
        )

        if not yuque_docs:
            logger.info(
                f"refresh_doc_id knowledge_id is {knowledge_id}, doc_id is {doc_id}, yuque_docs is empty, need to refresh"
            )

            refresh = await self.refresh_single_doc(
                knowledge_id=knowledge_id, doc_id=doc_id
            )
        else:
            yuque_doc = yuque_docs[0]
            latest_version_id = yuque_doc.latest_version_id

            group_login = yuque_doc.group_login
            book_slug = yuque_doc.book_slug
            doc_slug = yuque_doc.doc_slug
            title = yuque_doc.title
            current_version_id = self.find_version_from_yuque_info(
                token=yuque_doc.token,
                group_login=group_login,
                book_slug=book_slug,
                doc_slug=doc_slug,
            )

            if not latest_version_id or latest_version_id != current_version_id:
                logger.info(
                    f"refresh_doc_id knowledge_id is {knowledge_id}, doc_id is {doc_id}, latest_version_id is {latest_version_id}, current_version_id is {current_version_id}, {title} need to refresh"
                )

                refresh = await self.refresh_single_doc(
                    knowledge_id=knowledge_id, doc_id=doc_id
                )
            else:
                logger.info(
                    f"refresh_doc_id knowledge_id is {knowledge_id}, doc_id is {doc_id}, latest_version_id is {latest_version_id}, current_version_id is {current_version_id}, {title} no need to refresh"
                )

                refresh = True
        logger.info(f"refresh_doc_id result is {refresh}, doc_id is {doc_id}")

        return refresh

    async def refresh_doc_ids(
        self, knowledge_id: str, doc_ids: List[str], refresh_id: Optional[str] = None
    ):
        logger.info(
            f"refresh_doc_ids knowledge_id is {knowledge_id}, doc_ids is {doc_ids}， 当前线程数：{threading.active_count()}"
        )
        start_time = timeit.default_timer()

        refresh = False
        tasks = []
        for doc_id in doc_ids:
            if not doc_id:
                logger.info(
                    f"refresh_doc_ids knowledge_id is {knowledge_id}, doc_id is {doc_id}"
                )
                continue

            # 添加任务
            tasks.append(self.process_doc_id(knowledge_id, doc_id, refresh_id))

        # 等待任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"An error occurred: {result}")
            elif result is not None:
                # 至少有一个成功的刷新
                refresh = True

        cost_time = round(timeit.default_timer() - start_time, 2)
        logger.info(
            f"refresh_doc_ids knowledge_id is {knowledge_id}, doc_ids len is {len(doc_ids)}, cost time is {cost_time} seconds，  当前线程数：{threading.active_count()}"
        )

        return refresh

    async def update_error_msg_to_refresh_record(
        self, refresh_id: str, current_error_msg: str
    ):
        logger.info(
            f"update_error_msg_to_record refresh_id is {refresh_id}, error_msg is {current_error_msg}"
        )

        records = self._refresh_record_dao.get_knowledge_refresh_records(
            query=KnowledgeRefreshRecordEntity(refresh_id=refresh_id)
        )
        if not records:
            logger.error(
                f"refresh_doc_ids error, refresh_id is {refresh_id}, records is empty"
            )
            return None

        record = records[0]
        record.error_msg = (record.error_msg or "") + current_error_msg
        record.error_msg = (
            record.error_msg[1:]
            if record.error_msg and record.error_msg.startswith(";")
            else record.error_msg
        )
        self._refresh_record_dao.update_knowledge_refresh_records_batch([record])

    async def process_doc_id(
        self, knowledge_id: str, doc_id: str, refresh_id: Optional[str]
    ):
        logger.info(
            f"process_doc_id start knowledge_id is {knowledge_id}, doc_id is {doc_id}, refresh_id is {refresh_id}"
        )

        try:
            refresh = await self.refresh_doc_id(
                knowledge_id=knowledge_id, doc_id=doc_id
            )
            return refresh
        except Exception as e:
            logger.error(f"refresh_doc_id error, doc_id is {doc_id}, error is {e}")

            # 更新失败原因
            if refresh_id:
                await self.update_error_msg_to_refresh_record(
                    refresh_id=refresh_id,
                    current_error_msg=f";doc_id:{doc_id}, error:{str(e)}",
                )

            return None  # 返回 None 表示没有成功更新

    async def refresh_knowledge(
        self, knowledge_id: str, refresh_id: Optional[str] = None
    ):
        logger.info(f"refresh_knowledge knowledge_id is {knowledge_id}")

        if not knowledge_id:
            raise Exception("knowledge_id is required")

        docs = self._document_dao.get_knowledge_documents(
            query=KnowledgeDocumentEntity(knowledge_id=knowledge_id),
            page=self._default_page,
            page_size=self._default_page_size,
        )
        if not docs:
            logger.info("refresh_knowledge docs is empty, no need to refresh")

            return True

        doc_ids = [doc.doc_id for doc in docs if doc.doc_id]
        refresh = await self.refresh_doc_ids(
            knowledge_id=knowledge_id, doc_ids=doc_ids, refresh_id=refresh_id
        )
        logger.info(
            f"refresh_knowledge result {refresh}, knowledge_id is {knowledge_id}"
        )

        return refresh

    def delete_refresh_records(
        self, refresh_id: Optional[str] = None, refresh_time: Optional[str] = None
    ):
        logger.info(f"delete_refresh_records request is {refresh_id}, {refresh_time}")

        self._refresh_record_dao.delete_knowledge_refresh_records(
            refresh_id=refresh_id, refresh_time=refresh_time
        )
        return True


    def update_yuque_docs(self, group_login: Optional[str] = None, book_slug: Optional[str] = None, request: Optional[CreateDocRequest] = None):
        logger.info(f"update_yuque_docs start, group_login is {group_login}, book_slug is {book_slug}, request is {request}")

        if request.public is None:
            logger.error("update_yuque_docs error, public is required")

            raise Exception("public is required")
        if not request.token:
            logger.error("update_yuque_docs error, token is required")

            raise Exception("token is required")

        # get all docs
        tocs = self.get_yuque_toc(group_login, book_slug, request.token)
        if not tocs:
            logger.info("update_yuque_docs tocs is empty, no need to update")

            return True

        # update doc public
        yuque_ids = [toc.get("id") for toc in tocs if toc.get("id")]
        for yuque_id in yuque_ids:
            web_reader = AntYuqueLoader(access_token=request.token)
            yuque_doc = web_reader.update_yuque_doc(group_login, book_slug, yuque_id, request)
            if not yuque_doc:
                logger.error(f"update_yuque_docs error, yuque_id is {yuque_id}")

                raise Exception(f"update_yuque_docs error, update_yuque_doc is empty, yuque_id is {yuque_id}")

        return True



    def create_yuque_doc(self, group_login: Optional[str] = None, book_slug: Optional[str] = None, request: Optional[CreateDocRequest] = None):
        logger.info(f"create_yuque_doc request is {group_login}, {book_slug}, {request}")

        if not group_login or not book_slug or not request:
            raise Exception("group_login, book_slug and request are required")
        if not request.token or not request.slug or not request.title or not request.body:
            raise Exception("request param is invalid")

        # 创建语雀文档
        web_reader = AntYuqueLoader(access_token=request.token)
        yuque_doc = web_reader.create_doc_by_group_book_slug(group_login, book_slug, request)

        if not yuque_doc or not yuque_doc.get("id"):
            raise Exception("create_yuque_doc failed")
        yuque_doc_id = yuque_doc.get("id")

        return yuque_doc_id



    def get_yuque_toc(self, group_login: Optional[str] = None, book_slug: Optional[str] = None, yuque_token: Optional[str] = None):
        logger.info(f"get_yuque_toc request is {group_login}, {book_slug}, {yuque_token}")

        if not group_login or not book_slug or not yuque_token:
            raise Exception("group_login and book_slug and yuque_token are required")

        # 查询语雀目录
        web_reader = AntYuqueLoader(access_token=yuque_token)
        tocs = web_reader.get_toc_by_group_login_and_book_slug(group_login, book_slug)
        logger.info(f"get_yuque_toc res is {tocs}")

        return tocs


    def get_yuque_doc(self, group_login: Optional[str] = None, book_slug: Optional[str] = None, doc_slug:Optional[str]=None, yuque_token: Optional[str] = None):
        logger.info(f"get_yuque_doc request is {group_login}, {book_slug}, {doc_slug}, {yuque_token}")

        if not group_login or not book_slug or not doc_slug or not yuque_token:
            raise Exception("group_login and book_slug and doc_slug and yuque_token are required")

        # 查询语雀文档
        web_reader = AntYuqueLoader(access_token=yuque_token)
        doc = web_reader.single_doc(group_login, book_slug, doc_slug)
        logger.info(f"get_yuque_doc res is {doc}")

        # 解析图片uml信息
        return web_reader.get_uml_content_from_doc(doc)


    def update_yuque_toc(self, group_login: Optional[str] = None, book_slug: Optional[str] = None, request: Optional[UpdateTocRequest] = None):
        logger.info(f"update_yuque_toc request is {group_login}, {book_slug}, {request}")

        if not group_login or not book_slug or not request:
            raise Exception("group_login, book_slug and request are required")
        if not request.token or not request.action or not request.action_mode:
            raise Exception("request param is invalid")

        # 更新语雀目录
        web_reader = AntYuqueLoader(access_token=request.token)
        tocs = web_reader.update_toc_by_group_login_and_book_slug(group_login, book_slug, request)
        logger.info(f"update_yuque_toc res is {tocs}")

        return tocs

    def build_toc_tree(self, tocs: []):
        logger.info(f"build_toc_tree tocs len is {len(tocs)}")

        toc_tree = []
        max_level = max(toc.get("level") for toc in tocs)
        for level in range(max_level + 1):
            level_tocs = [toc for toc in tocs if toc.get("level") == level]
            toc_tree.append(level_tocs)

        return toc_tree


    def get_should_import_uuid_dict(self, tocs: [], import_source_uuid_dict: Dict):
        logger.info(f"get_should_import_uuid_dict start, tocs len is {len(tocs)}, import_source_uuid_dict len is {len(import_source_uuid_dict.keys())}")

        # 1.先找到所有DOC的uuid 以及 有父节点的uuid
        import_uuid_dict = {toc.get("uuid"): True for toc in tocs if toc.get("type") == "DOC" and toc.get("uuid") in import_source_uuid_dict.keys()}
        parent_uuid_dict = {toc.get("uuid"): toc.get("parent_uuid") for toc in tocs if toc.get("parent_uuid")}
        logger.info(f"import_uuid_dict len is {len(import_uuid_dict.keys())}, parent_uuid_dict len id {len(parent_uuid_dict.keys())}")

        # 2.挨个向上遍历，最上层的分组标记为True (O(M*N)
        should_import_uuid_dict = {}
        for uuid in import_uuid_dict.keys():
            should_import_uuid_dict[uuid] = True
            parent_uuid = parent_uuid_dict.get(uuid)
            while parent_uuid:
                logger.info(f"uuid is {uuid}, parent_uuid is {parent_uuid}, update True")

                # 减枝
                if parent_uuid in should_import_uuid_dict.keys():
                    logger.info("parent_uuid in should_import_uuid_dict.keys(), break")

                    break

                should_import_uuid_dict[parent_uuid] = True
                parent_uuid = parent_uuid_dict.get(parent_uuid)
        logger.info(f"get_should_import_uuid_dict end len is {len(should_import_uuid_dict.keys())}")

        return should_import_uuid_dict

    def get_target_uuid_from_toc(self, doc_tocs: Optional[List] = None, doc_id: Optional[str] = None, title: Optional[str] = None, level: Optional[int] = None, parent_uuid: Optional[str] = None):
        logger.info(f"get_target_uuid_from_toc doc_toc len is {len(doc_tocs)}, doc_id is {doc_id}, title is {title}, level is {level}, parent_uuid is {parent_uuid}")

        if not doc_tocs:
            return None

        target_uuid = None
        for toc in doc_tocs:
            # case1: 有内容的文档根据doc id查找uuid
            if doc_id and  toc.get("doc_id") and toc.get("doc_id") == doc_id:
                target_uuid = toc.get("uuid")
                logger.info(f"find target_uuid {target_uuid}, doc_id is {doc_id}, title is {title}")

                break
            # case2: 无内容的文档根据title查找uuid
            if title and toc.get("title") and toc.get("title") == title and toc.get("level") == level:
                if parent_uuid:
                    if toc.get("parent_uuid") == parent_uuid:
                        # 保证同一个父目录下，标题要唯一
                        target_uuid = toc.get("uuid")
                        logger.info(f"find target_uuid {target_uuid}, doc_id is {doc_id}, title is {title}")

                        break
                    else:
                        continue
                else:
                    target_uuid = toc.get("uuid")
                    logger.info(f"find target_uuid {target_uuid}, doc_id is {doc_id}, title is {title}")

                    break
        if not target_uuid:
            logger.error(f"not find target_uuid, doc_id is {doc_id}, title is {title}")

            raise Exception(f"not find target_uuid doc_id is {doc_id}, title is {title}, level is {level}")

        logger.info(f"get_target_uuid_from_toc target_uuid is {target_uuid}")

        return target_uuid



    def get_import_source_uuid_dict(self, knowledge_id: str, group_login: str, book_slug: str):
        logger.info(f"get_import_source_uuid_dict start knowledge_id is {knowledge_id}, group_login is {group_login}, book_slug is {book_slug}")

        yuque_docs = self._yuque_dao.get_knowledge_yuque(query=KnowledgeYuqueEntity(knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug))
        if not yuque_docs:
            return {}
        import_source_uuid_dict = {yuque_doc.doc_uuid: yuque_doc for yuque_doc in yuque_docs}
        logger.info(f"get_import_source_uuid_dict end knowledge_id is {knowledge_id}, group_login is {group_login}, book_slug is {book_slug}, import_source_uuid_dict len is {len(import_source_uuid_dict.keys())}")

        return import_source_uuid_dict


    def update_backup_doc_uuid(self, import_source_uuid_dict: dict, source_dest_uuid_dict: dict):
        logger.info(f"update_backup_doc_uuid start import_source_uuid_dict len is {len(import_source_uuid_dict.keys())}, source_dest_uuid_dict len is {len(source_dest_uuid_dict.keys())}")

        if not import_source_uuid_dict or not source_dest_uuid_dict:
            logger.info("import_source_uuid_dict or source_dest_uuid_dict is empty, no need to update")

            return True

        # 更新备份的uuid
        yuque_docs = []
        for source_uuid in import_source_uuid_dict.keys():
            yuque_doc = import_source_uuid_dict.get(source_uuid)
            target_uuid = source_dest_uuid_dict.get(source_uuid)
            if not target_uuid:
                logger.error(f"not find target_uuid, source_uuid is {source_uuid}, target_uuid is {target_uuid}")

                continue
            yuque_doc.backup_doc_uuid = target_uuid
            yuque_docs.append(yuque_doc)

        # 批量更新
        self._yuque_dao.update_knowledge_yuque_batch(yuque_docs=yuque_docs)
        return True


    def get_source_dest_uuid_dict(self, source_web_reader: AntYuqueLoader, dest_web_reader:AntYuqueLoader,
                                  group_login: str, book_slug: str, dest_group_login: str,
                                  toc_tree: [], import_source_uuid_dict: Dict, should_import_uuid_dict: Dict):
        logger.info(f"get_source_dest_uuid_dict start toc_tree len is {len(toc_tree)}, import_source_uuid_dict len is {len(import_source_uuid_dict.keys())}, should_import_uuid_dict len is {len(should_import_uuid_dict.keys())}")
        
        count = 0
        source_dest_uuid_dict = {}
        for tocs in toc_tree:
            for toc in tocs:
                count += 1
                level = toc.get("level")
                source_uuid = toc.get("uuid")
                type = toc.get("type")
                title = toc.get("title")
                slug = toc.get("slug")
                url = toc.get("url")
                parent_uuid = toc.get("parent_uuid")
                logger.info(f"start process {count} doc title {title}, type is {type}, level is {level}, source_uuid is {source_uuid}, parent_uuid is {parent_uuid}， source_dest_uuid_dict[parent_uuid] is {source_dest_uuid_dict.get(parent_uuid)}")

                # 判断当前节点是否需要被处理
                if source_uuid not in should_import_uuid_dict.keys():
                    logger.info("uuid is not import and child uuid is not import, skip")

                    continue

                # 组装 更新目录请求
                update_toc_request = UpdateTocRequest(
                    action="appendNode",
                    action_mode="child",
                    type=type,
                    title=title,
                    slug=slug
                )
                if parent_uuid and source_dest_uuid_dict.get(parent_uuid):
                    # 父目录存在，指定更新到父目录下；父目录不存在，更新到当前根目录下
                    update_toc_request.target_uuid = source_dest_uuid_dict[parent_uuid]

                if type == "TITLE":
                    # 创建分组节点：没有内容，纯目录；直接创建目录（更新目录接口-创建场景）
                    doc_tocs = dest_web_reader.update_toc_by_group_login_and_book_slug(dest_group_login, book_slug, update_toc_request)
                    logger.info(f"update_toc_by_group_login_and_book_slug success! doc tocs len is {len(doc_tocs)}")

                    target_uuid = self.get_target_uuid_from_toc(doc_tocs, None, title, level, source_dest_uuid_dict.get(parent_uuid))
                elif type == "DOC":
                    # 创建文档节点：有内容，是文档：先创建文档，再更新到目录下（更新目录接口-更新场景）
                    single_doc = source_web_reader.single_doc(group_login, book_slug, slug)
                    format = single_doc.get("format")
                    if format == "lake":
                        content = single_doc.get("body_lake")
                    else:
                        content = single_doc.get("body")
                    content = content + " " if not content else content
                    create_doc_request = CreateDocRequest(
                        title=title,
                        body=content,
                        slug=slug,
                    )
                    doc = dest_web_reader.create_doc_by_group_book_slug(dest_group_login, book_slug, create_doc_request)
                    doc_id = doc.get("id")

                    # 更新文档id
                    update_toc_request.doc_ids = [doc_id]
                    doc_tocs = dest_web_reader.update_toc_by_group_login_and_book_slug(dest_group_login, book_slug, update_toc_request)

                    # 判断是否更新成功
                    doc_ids = [toc.get('doc_id') for toc in doc_tocs if toc.get('type') == "DOC"]
                    if doc_id in doc_ids:
                        logger.info(f"update_toc_by_group_login_and_book_slug success! doc id is {doc_id} title is {title}")
                    else:
                        logger.error(f"update_toc_by_group_login_and_book_slug fail! doc id is {doc_id} title is {title}")

                        raise Exception(f"update_toc_by_group_login_and_book_slug fail! doc id is {doc_id} title is {title}")

                    target_uuid = self.get_target_uuid_from_toc(doc_tocs, doc_id)
                elif type == 'LINK':
                    # 创建外链节点

                    # 更新url和打开方式
                    update_toc_request.url=url
                    update_toc_request.open_window=1
                    doc_tocs = dest_web_reader.update_toc_by_group_login_and_book_slug(dest_group_login, book_slug, update_toc_request)
                    target_uuid = self.get_target_uuid_from_toc(doc_tocs, None, title, level, source_dest_uuid_dict.get(parent_uuid))
                else:
                    logger.error(f"not support type {type}")

                    raise Exception("not support type")
                source_dest_uuid_dict[source_uuid] = target_uuid
                logger.info(f"create {type} doc {title} success! source_dest_uuid_dict len is {len(source_dest_uuid_dict.keys())}")

        return source_dest_uuid_dict

    def backup_yuque_toc(self, knowledge_id: str, source_group_token: str, dest_group_token: str, group_login: str, book_slug: str, dest_group_login: str):
        logger.info(f"backup_yuque_toc start, knowledge_id is {knowledge_id}, source_group_token is {source_group_token}, dest_group_token is {dest_group_token}, group_login is {group_login}")

        # 1.查询所有的目录toc
        dest_web_reader = AntYuqueLoader(access_token=dest_group_token)
        source_web_reader = AntYuqueLoader(access_token=source_group_token)
        tocs = source_web_reader.get_toc_by_group_login_and_book_slug(group_login, book_slug)

        # 2.组装目录树：根据level或者depth [{}, []]
        toc_tree = self.build_toc_tree(tocs)

        # 3.获取已导入的文档uuid列表
        import_source_uuid_dict = self.get_import_source_uuid_dict(knowledge_id, group_login, book_slug)

        # 4.递归获取应该被导入的uuid（包括分组节点）
        should_import_uuid_dict = self.get_should_import_uuid_dict(tocs, import_source_uuid_dict)

        # 5.生成备份uuid以及获取映射关系dict：source_uuid -> dest_uuid
        source_dest_uuid_dict = self.get_source_dest_uuid_dict(source_web_reader, dest_web_reader, group_login,
                                                               book_slug, dest_group_login, toc_tree,
                                                               import_source_uuid_dict, should_import_uuid_dict)

        # 6.批量更新映射关系，写入到数据库中
        self.update_backup_doc_uuid(import_source_uuid_dict=import_source_uuid_dict, source_dest_uuid_dict=source_dest_uuid_dict)
        logger.info(f"backup_yuque_toc success,  knowledge_id is {knowledge_id}")

        return True


    def check_book_exist_and_create(self, dest_group_token: str, dest_group_login: str, book_slug: str, book_name: str, book_desc: str):
        logger.info(f"check_book_exist_and_create start, dest_group_token is {dest_group_token}, dest_group_login is {dest_group_login}, book_slug is {book_slug}")

        # 1.判断当前知识库是否已经存在
        dest_web_reader = AntYuqueLoader(access_token=dest_group_token)
        books = dest_web_reader.get_books_by_group_login(group_login=dest_group_login, offset=0, page_size=100, temp_books=[])
        logger.info(f"all books len is {len(books)}")

        if books:
            for book in books:
                if book.get("slug") == book_slug and book.get("name") == book_name:
                    logger.info(f"book is exist! {book_slug}, {book_name}, no need to create")

                    return True

        logger.info(f"book is not exist! {book_slug}, {book_name} need to create")

        # 2.不存在就创建知识库
        create_book_request = CreateBookRequest(
            name=book_name,
            slug=book_slug,
            description=book_desc,
            public="1"
        )
        data = dest_web_reader.create_book(dest_group_login, create_book_request)
        logger.info(f"create_book res is {data}")

        return True


    def check_book_doc_exist_and_delete(self, dest_group_token: str, dest_group_login: str, book_slug: str, book_name: str):
        logger.info(f"check_book_doc_esixt_and_delete start, dest_group_token is {dest_group_token}, dest_group_login is {dest_group_login}, book_slug is {book_slug}, book_name is {book_name}")

        # 1.查询知识库下所有的文档
        dest_web_reader = AntYuqueLoader(access_token=dest_group_token)
        tocs = dest_web_reader.get_toc_by_group_login_and_book_slug(dest_group_login, book_slug)
        logger.info(f"all tocs len is {len(tocs)}")

        if not tocs:
            logger.info(f"tocs is empty! no need to delete")

            return True

        # 2.删除知识库下所有的文档
        delete_cnt = 0
        for toc in tocs:
            doc_id = toc.get("doc_id")
            child_uuid = toc.get("child_uuid")
            level = toc.get("level")
            # 只删除最外层目录或者文档即可
            if level != 0:
                continue
            delete_cnt += 1

            if child_uuid or not doc_id:
                # 删除分组节点
                logger.info(f"doc_id is empty, doc type is {toc.get('type')}, title is {toc.get('title')} need to delete outline")

                update_toc_request = UpdateTocRequest(
                    action="removeNode",
                    action_mode="child",
                    node_uuid=toc.get("uuid")
                )
                dest_web_reader.update_toc_by_group_login_and_book_slug(dest_group_login, book_slug, update_toc_request)
            else:
                # 删除文档节点
                logger.info(f"doc_id is not empty, need to delete doc, title is {toc.get('title')}")

                dest_web_reader.delete_doc(dest_group_login, book_slug, doc_id)
            logger.info(f"delete doc success! doc_id is {doc_id}, title is {toc.get('title')}")
        logger.info(f"delete all doc success, delete_cnt len is {delete_cnt}")

        return True


    async def backup_yuque_book(self, knowledge_id: str, source_group_token: str, dest_group_token: str, group_login: str, book_slug: str, book_details: {}, dest_group_login: str):
        logger.info(f"backup_yuque_book knowledge_id is {knowledge_id}, token is {source_group_token}, {dest_group_token}, group_login is {group_login}, book_slug is {book_slug}")

        book_name = book_details.get("name")
        book_desc = book_details.get("description")

        # 1.创建知识库，如果知识库已经存在，那么就不用创建
        self.check_book_exist_and_create(dest_group_token, dest_group_login, book_slug, book_name, book_desc)

        # 2.移动到指定分组--todo,语雀团队暂时没有接口支持

        # 3.删除知识库下的文档
        self.check_book_doc_exist_and_delete(dest_group_token, dest_group_login, book_slug, book_name)

        # 4.重新创建文档及目录
        self.backup_yuque_toc(knowledge_id, source_group_token, dest_group_token, group_login, book_slug, dest_group_login)

        return True


    def get_book_slug_from_docs(self, group_login: str, yuque_docs: []):
        logger.info(f"get_book_slug_from_docs group_login is {group_login}, yuque_docs len is {len(yuque_docs)}")

        if not yuque_docs:
            return []

        book_slugs = set()
        for yuque_doc in yuque_docs:
            if not yuque_doc.book_slug:
                continue

            if yuque_doc.group_login == group_login:
                book_slugs.add(yuque_doc.book_slug)

        book_slugs = list(book_slugs)
        logger.info(f"get_book_slug_from_docs book_slugs is {book_slugs}")

        return book_slugs



    async def create_backup_knowledge(self, space: KnowledgeSpaceEntity, dest_group_token: str, dest_group_login: str):
        knowledge_id = space.knowledge_id

        # get yuque docs
        yuque_docs = self._yuque_dao.get_knowledge_yuque(query=KnowledgeYuqueEntity(knowledge_id=knowledge_id))
        if not yuque_docs:
            logger.info(f"create_backup_knowledge knowledge_id is {knowledge_id}, yuque_docs is empty, no need to backup")

            return True

        # get yuque group slugs
        token_group_dict = {doc.token : doc.group_login for doc in yuque_docs}
        if not token_group_dict:
            logger.info(f"create_backup_knowledge knowledge_id is {knowledge_id}, token_group_dict is empty, no need to backup")

            return True

        for token in token_group_dict.keys():
            web_reader = AntYuqueLoader(access_token=token)

            group_login = token_group_dict[token]
            book_slugs = self.get_book_slug_from_docs(group_login, yuque_docs)
            for book_slug in book_slugs:
                book_details = web_reader.get_book_slug_info(group_login, book_slug, token)

                # 备份知识book维度
                await self.backup_yuque_book(knowledge_id, token, dest_group_token, group_login, book_slug, book_details, dest_group_login)

        return True



    async def backup_knowledge(self, knowledge_id: str, request: CreateBookRequest):
        logger.info(f"backup_knowledge knowledge_id is {knowledge_id}")

        if not knowledge_id:
            raise Exception("knowledge_id is required")

        # get public knowledge
        spaces = self._dao.get_knowledge_space(query=KnowledgeSpaceEntity(knowledge_id=knowledge_id, knowledge_type=KnowledgeAccessLevel.PUBLIC.name))
        if not spaces:
            logger.info(f"backup_knowledge knowledge_id is {knowledge_id}, public spaces is empty, no need to backup")

            return True

        # 创建备份语雀知识库
        space = spaces[0]
        await self.create_backup_knowledge(space, request.dest_group_token, request.dest_group_login)

        return True


    async def backup_all_public_knowledge(self, request: CreateBookRequest):
        logger.info(f"backup_all_public_knowledge start, request is {request}f")

        # 1.查询所有的公开知识
        query = KnowledgeSpaceEntity(knowledge_type=KnowledgeAccessLevel.PUBLIC.name)
        if request.category:
            query.category = request.category
        spaces = self._dao.get_knowledge_space(query=query)
        if not spaces:
            logger.info(f"backup_all_public_knowledge spaces is empty, no need to backup")

            return True

        # 2.分别备份知识
        knowledge_ids = [space.knowledge_id for space in spaces if space.knowledge_id]
        logger.info(f"backup_all_public_knowledge knowledge_ids len is {len(knowledge_ids)}")

        async def backup_single_knowledge(knowledge_id, request):
            logger.info(f"backup knowledge_id is {knowledge_id}")
            try:
                asyncio.create_task(self.backup_knowledge(knowledge_id, request))
            except Exception as e:
                logger.error(f"backup_knowledge error, knowledge_id is {knowledge_id}, error is {e}, continue")

        # 使用 asyncio.gather 进行异步并行处理
        tasks = [asyncio.create_task(backup_single_knowledge(knowledge_id, request)) for knowledge_id in knowledge_ids]
        logger.info(f"backup_all_public_knowledge success tasks len is {len(tasks)}")

        return True


    async def abackup_all_public_knowledge(self, request: CreateBookRequest):
        logger.info(f"async backup_all_public_knowledge start, request is {request}")

        if request.async_run:
            logger.info(f"async_run is true, async run request is {request}")

            asyncio.create_task(self.backup_all_public_knowledge(request))
        else:
            logger.info(f"async_run is false, sync run request is {request}")

            await self.backup_all_public_knowledge(request)
        logger.info(f"async backup_all_public_knowledge end, request is {request}")

        return True


    def create_settings(self, request: SettingsRequest):
        logger.info(f"create_settings request is {request}")

        if not request.setting_key:
            raise Exception("setting_key is required")
        if not request.value:
            raise Exception("value is required")
        if not request.description:
            raise Exception("description is required")
        if not request.operator:
            raise Exception("operator is required")

        settings = self._settings_dao.get_settings(query=SettingsEntity(setting_key=request.setting_key))
        if settings:
            logger.info(f"create_settings settings is not empty, no need to create: {settings[0].setting_key}")

            return settings[0]

        self._settings_dao.create_settings(settings=[request])

        return True


    def update_settings(self, request: SettingsRequest):
        logger.info(f"update_settings request is {request}")

        if not request.setting_key:
            raise Exception("setting_key is required")

        # query setting
        settings = self._settings_dao.get_settings(query=SettingsEntity(setting_key=request.setting_key))
        if not settings:
            logger.info(f"settings {request.setting_key} is empty, no need to update")

            return False
        setting = settings[0]

        # update setting
        if request.value:
            setting.value = request.value
        if request.description:
            setting.description = request.description
        if request.operator:
            setting.operator = request.operator
        logger.info(f"update_settings setting is {setting}")

        self._settings_dao.update_setting(setting=setting)
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
