import logging
import os
import shutil
from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile

from derisk._private.config import Config
from derisk.configs import TAG_KEY_KNOWLEDGE_FACTORY_DOMAIN_TYPE
from derisk.configs.model_config import (
    KNOWLEDGE_UPLOAD_ROOT_PATH,
)
from derisk.core.awel.dag.dag_manager import DAGManager
from derisk.core.interface.file import FileStorageClient
from derisk.rag.retriever import BaseRetriever
from derisk.rag.retriever.embedding import EmbeddingRetriever
from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.i18n_utils import _
from derisk.util.tracer import SpanType, root_tracer
from derisk_app.knowledge.request.request import (
    ChunkEditRequest,
    ChunkQueryRequest,
    DocumentQueryRequest,
    DocumentRecallTestRequest,
    DocumentSummaryRequest,
    DocumentSyncRequest,
    GraphVisRequest,
    KnowledgeDocumentRequest,
    KnowledgeQueryRequest,
    KnowledgeSpaceRequest,
    SpaceArgumentRequest,
)
from derisk_app.knowledge.request.response import (
    ChunkQueryResponse,
    KnowledgeQueryResponse,
    ChunkDetailResponse,
)
from derisk_app.knowledge.service import KnowledgeService
from derisk_app.openapi.api_v1.api_v1 import (
    get_executor,
    no_stream_generator,
    stream_generator,
)
from derisk_app.openapi.api_view_model import Result
from derisk_ext.rag import ChunkParameters
from derisk_ext.rag.chunk_manager import ChunkStrategy
from derisk_ext.rag.knowledge.factory import KnowledgeFactory
from derisk_serve.rag.api.schemas import (
    ChunkServeRequest,
    DocumentServeRequest,
    KnowledgeConfigResponse,
    KnowledgeDomainType,
    KnowledgeStorageType,
    KnowledgeSyncRequest,
    SpaceServeRequest,
)

# from derisk_serve.rag.connector import VectorStoreConnector
from derisk_serve.rag.service.service import Service
from derisk_serve.rag.storage_manager import StorageManager
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

logger = logging.getLogger(__name__)

CFG = Config()
router = APIRouter()


knowledge_space_service = KnowledgeService()


def get_rag_service() -> Service:
    """Get Rag Service."""
    return Service.get_instance(CFG.SYSTEM_APP)


def get_dag_manager() -> DAGManager:
    """Get DAG Manager."""
    return DAGManager.get_instance(CFG.SYSTEM_APP)


def get_fs() -> FileStorageClient:
    return FileStorageClient.get_instance(CFG.SYSTEM_APP)


@router.post("/knowledge/space/add")
async def space_add(
    request: SpaceServeRequest, service: Service = Depends(get_rag_service)
):
    logger.info(f"/space/add params: {request}")
    try:
        await blocking_func_to_async(get_executor(), service.create_space, request)
        return Result.succ([])
    except Exception as e:
        logger.exception("space add exception!")
        return Result.failed(code="E000X", msg=f"space add error {e}")


@router.post("/knowledge/space/list")
async def space_list(request: KnowledgeSpaceRequest):
    logger.info(f"/space/list params: {request}")
    try:
        res = await blocking_func_to_async(
            get_executor(), knowledge_space_service.get_knowledge_space, request
        )
        return Result.succ(res)
    except Exception as e:
        logger.exception(f"Space list error!{str(e)}")
        return Result.failed(code="E000X", msg=f"space list error {e}")


@router.post("/knowledge/space/delete")
def space_delete(request: KnowledgeSpaceRequest):
    logger.info(f"/space/delete params: {request}")
    try:
        # delete Files in 'pilot/data/
        safe_space_name = os.path.basename(request.name)

        # obtain absolute paths of uploaded space-docfiles
        space_dir = os.path.abspath(
            os.path.join(KNOWLEDGE_UPLOAD_ROOT_PATH, safe_space_name)
        )
        try:
            if os.path.exists(space_dir):
                shutil.rmtree(space_dir)
        except Exception as e:
            logger.error(f"Failed to remove {safe_space_name}: {str(e)}")
        return Result.succ(knowledge_space_service.delete_space(request.name))
    except Exception as e:
        return Result.failed(code="E000X", msg=f"space delete error {e}")


@router.post("/knowledge/{space_id}/arguments")
async def arguments(space_id: str):
    logger.info(f"/knowledge/{space_id}/arguments params: {space_id}")
    try:
        res = await blocking_func_to_async(
            get_executor(), knowledge_space_service.arguments, space_id
        )
        return Result.succ(res)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"space arguments error {e}")


@router.post("/knowledge/{space_name}/recall_test")
async def recall_test(
    space_name: str,
    request: DocumentRecallTestRequest,
):
    logger.info(f"/knowledge/{space_name}/recall_test params: {request}")
    try:
        return Result.succ(
            await knowledge_space_service.recall_test(space_name, request)
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"{space_name} recall_test error {e}")


@router.get("/knowledge/{space_id}/recall_retrievers")
def recall_retrievers(
    space_id: str,
):
    logger.info(f"/knowledge/{space_id}/recall_retrievers params:")
    try:
        logger.info(f"get_recall_retrievers {space_id}")

        subclasses = set()

        def recursively_find_subclasses(cls):
            for subclass in cls.__subclasses__():
                subclasses.add(subclass)
                recursively_find_subclasses(subclass)

        recursively_find_subclasses(BaseRetriever)

        retrievers_with_name = []
        base_name_method = BaseRetriever.name.__func__
        for cls in subclasses:
            if hasattr(cls, "name"):
                cls_name_method = getattr(cls, "name")
                if cls_name_method.__func__ != base_name_method:
                    retrievers_with_name.append(cls)

        retriever_names = {}
        for retriever_cls in retrievers_with_name:
            try:
                name = retriever_cls.name()
                retriever_names[name] = retriever_cls
            except Exception as e:
                logger.error(f"Error calling name method on {retriever_cls}: {e}")

        return Result.succ(list(retriever_names.keys()))
    except Exception as e:
        return Result.failed(
            code="E000X", msg=f"{space_id} get_recall_retrievers error {e}"
        )


@router.post("/knowledge/{space_id}/argument/save")
async def arguments_save(space_id: str, argument_request: SpaceArgumentRequest):
    logger.info("/knowledge/space/argument/save params:")
    try:
        res = await blocking_func_to_async(
            get_executor(),
            knowledge_space_service.argument_save,
            space_id,
            argument_request,
        )
        return Result.succ(res)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"space save error {e}")




@router.post("/knowledge/{space_name}/document/add")
async def document_add(
    space_name: str,
    request: KnowledgeDocumentRequest,
    service: Service = Depends(get_rag_service),
):
    logger.info(f"/document/add params: {space_name}, {request}")
    try:
        # res = await blocking_func_to_async(
        #     get_executor(),
        #     knowledge_space_service.create_knowledge_document,
        #     space=space_name,
        #     request=request,
        # )
        # return Result.succ(res)
        document_request = DocumentServeRequest(
            doc_name=request.doc_name,
            doc_type=request.doc_type,
            space_name=space_name,
            content=request.content,
            meta_data=request.meta_data,
        )
        doc = service.create_document(document_request)
        return Result.succ(doc.id)
        # return Result.succ([])
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document add error {e}")


@router.post("/knowledge/{space_name}/document/edit")
def document_edit(
    space_name: str,
    request: KnowledgeDocumentRequest,
    service: Service = Depends(get_rag_service),
):
    logger.info(f"/document/edit params: {space_name}, {request}")
    space = service.get({"name": space_name})
    if space is None:
        return Result.failed(
            code="E000X",
            msg=f"knowledge_space {space_name} can not be found",
        )
    serve_request = DocumentServeRequest(**request.dict())
    serve_request.id = request.doc_id
    try:
        return Result.succ(service.update_document(request=serve_request))
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document edit error {e}")


@router.get("/knowledge/document/chunkstrategies")
def chunk_strategies():
    """Get chunk strategies"""
    logger.info("/document/chunkstrategies:")
    try:
        return Result.succ(
            [
                {
                    "strategy": strategy.name,
                    "name": strategy.value[2],
                    "description": strategy.value[3],
                    "parameters": strategy.value[1],
                    "suffix": [
                        knowledge.document_type().value
                        for knowledge in KnowledgeFactory.subclasses()
                        if strategy in knowledge.support_chunk_strategy()
                        and knowledge.document_type() is not None
                    ],
                    "type": set(
                        [
                            knowledge.type().value
                            for knowledge in KnowledgeFactory.subclasses()
                            if strategy in knowledge.support_chunk_strategy()
                        ]
                    ),
                }
                for strategy in ChunkStrategy
            ]
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"chunk strategies error {e}")


@router.get("/knowledge/space/config", response_model=Result[KnowledgeConfigResponse])
async def space_config() -> Result[KnowledgeConfigResponse]:
    """Get space config"""
    try:
        storage_list: List[KnowledgeStorageType] = []
        dag_manager: DAGManager = get_dag_manager()
        # Vector Storage
        vs_domain_types = [KnowledgeDomainType(name="Normal", desc="Normal")]
        dag_map = await blocking_func_to_async(
            get_executor(),
            dag_manager.get_dags_by_tag_key,
            TAG_KEY_KNOWLEDGE_FACTORY_DOMAIN_TYPE,
        )
        for domain_type, dags in dag_map.items():
            vs_domain_types.append(
                KnowledgeDomainType(
                    name=domain_type, desc=dags[0].description or domain_type
                )
            )

        storage_list.append(
            KnowledgeStorageType(
                name="VectorStore",
                desc=_("Vector Store"),
                domain_types=vs_domain_types,
            )
        )
        # Graph Storage
        storage_list.append(
            KnowledgeStorageType(
                name="KnowledgeGraph",
                desc=_("Knowledge Graph"),
                domain_types=[KnowledgeDomainType(name="Normal", desc="Normal")],
            )
        )
        # Full Text
        storage_list.append(
            KnowledgeStorageType(
                name="FullText",
                desc=_("Full Text"),
                domain_types=[KnowledgeDomainType(name="Normal", desc="Normal")],
            )
        )

        return Result.succ(
            KnowledgeConfigResponse(
                storage=storage_list,
            )
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"space config error {e}")


@router.post("/knowledge/{space_name}/document/list")
def document_list(space_name: str, query_request: DocumentQueryRequest):
    logger.info(f"/document/list params: {space_name}, {query_request}")
    try:
        return Result.succ(
            knowledge_space_service.get_knowledge_documents(space_name, query_request)
        )
    except Exception as e:
        logger.exception(f"document list error!{str(e)}")
        return Result.failed(code="E000X", msg=f"document list error {e}")


@router.post("/knowledge/{space_name}/graphvis")
def graph_vis(space_name: str, query_request: GraphVisRequest):
    logger.info(f"/document/list params: {space_name}, {query_request}")
    try:
        return Result.succ(
            knowledge_space_service.query_graph(
                space_name=space_name, limit=query_request.limit
            )
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"get graph vis error {e}")


@router.post("/knowledge/{space_name}/document/delete")
def document_delete(space_name: str, query_request: DocumentQueryRequest):
    logger.info(f"/document/list params: {space_name}, {query_request}")
    try:
        return Result.succ(
            knowledge_space_service.delete_document(space_name, query_request.doc_name)
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document delete error {e}")


@router.post("/knowledge/{space_name}/document/upload")
async def document_upload(
    space_name: str,
    doc_name: str = Form(...),
    doc_type: str = Form(...),
    doc_file: UploadFile = File(...),
    fs: FileStorageClient = Depends(get_fs),
    service: Service = Depends(get_rag_service),
):
    logger.info(f"/document/upload params: {space_name}")
    try:
        document_request = DocumentServeRequest(
            doc_name=doc_name,
            doc_type=doc_type,
            space_name=space_name,
        )
        if doc_file:
            document_request.doc_file = doc_file
        doc = service.create_document(document_request)
        return Result.succ(doc.id)
        # if doc_file:
        #     safe_filename = os.path.basename(doc_file.filename)
        #     # Sanitize inputs to prevent path traversal
        #     safe_space_name = os.path.basename(space_name)
        #
        #     custom_metadata = {
        #         "space_name": space_name,
        #         "doc_name": doc_name,
        #         "doc_type": doc_type,
        #     }
        #     bucket = "derisk_knowledge_file"
        #     file_uri = await blocking_func_to_async(
        #         get_executor(),
        #         fs.save_file,
        #         bucket,
        #         safe_filename,
        #         doc_file.file,
        #         custom_metadata=custom_metadata,
        #     )
        #
        #     try:
        #         request = KnowledgeDocumentRequest()
        #         request.doc_name = doc_name
        #         request.doc_type = doc_type
        #         request.content = file_uri
        #
        #         space_res = await blocking_func_to_async(
        #             get_executor(),
        #             knowledge_space_service.get_knowledge_space,
        #             KnowledgeSpaceRequest(name=safe_space_name),
        #         )
        #         if len(space_res) == 0:
        #             # create default space
        #             if "default" != safe_space_name:
        #                 raise Exception("you have not create your knowledge space.")
        #             await blocking_func_to_async(
        #                 get_executor(),
        #                 knowledge_space_service.create_knowledge_space,
        #                 KnowledgeSpaceRequest(
        #                     name=safe_space_name,
        #                     desc="first db-gpt rag application",
        #                     owner="derisk",
        #                 ),
        #             )
        #         res = await blocking_func_to_async(
        #             get_executor(),
        #             knowledge_space_service.create_knowledge_document,
        #             space=safe_space_name,
        #             request=request,
        #         )
        #         return Result.succ(res)
        #     except Exception as e:
        #         # Clean up temp file if anything goes wrong
        #         raise e

        # return Result.failed(code="E000X", msg="doc_file is None")
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document add error {e}")


@router.post("/knowledge/{space_name}/document/sync")
async def document_sync(
    space_name: str,
    request: DocumentSyncRequest,
    service: Service = Depends(get_rag_service),
):
    logger.info(f"Received params: {space_name}, {request}")
    try:
        knowledge_query = {}
        if request.knowledge_id:
            knowledge_query.update({"knowledge_id": request.knowledge_id})
        if space_name:
            knowledge_query.update({"name": space_name})
        knowledge_space = service.get(knowledge_query)
        if knowledge_space is None:
            return Result.failed(code="E000X", msg=f"space {space_name} not exist")
        if request.doc_ids is None or len(request.doc_ids) == 0:
            return Result.failed(code="E000X", msg="doc_ids is None")
        sync_request = KnowledgeSyncRequest(
            doc_id=request.doc_ids[0],
            knowledge_id=str(knowledge_space.knowledge_id),
            model_name=request.model_name,
        )
        sync_request.chunk_parameters = ChunkParameters(
            chunk_strategy="Automatic",
            chunk_size=request.chunk_size or 512,
            chunk_overlap=request.chunk_overlap or 50,
        )
        doc_ids = await service.sync_document(requests=[sync_request])
        return Result.succ(doc_ids)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document sync error {e}")


@router.post("/knowledge/{space_name}/document/sync_batch")
async def batch_document_sync(
    space_name: str,
    request: List[KnowledgeSyncRequest],
    service: Service = Depends(get_rag_service),
):
    logger.info(f"Received params: {space_name}, {request}")
    try:
        knowledge_query = {}
        if space_name:
            knowledge_query.update({"name": space_name})
            knowledge_space = service.get(knowledge_query)
        for sync_request in request:
            sync_request.knowledge_id = knowledge_space.knowledge_id
            doc = service.get_document({"id": sync_request.doc_id})
            sync_request.doc_id = doc.doc_id
        doc_ids = await service.sync_document(requests=request)
        # doc_ids = service.sync_document(
        #     space_name=space_name, sync_requests=request
        # )
        return Result.succ({"tasks": doc_ids})
    except Exception as e:
        logger.exception("document sync batch error!")
        return Result.failed(code="E000X", msg=f"document sync batch error {e}")


@router.post("/knowledge/{space_name}/chunk/list")
def chunk_list(
    space_name: str,
    query_request: ChunkQueryRequest,
    service: Service = Depends(get_rag_service),
):
    logger.info(f"/chunk/list params: {space_name}, {query_request}")
    try:
        doc_query = {"id": query_request.document_id}
        doc_res = service.get_document(doc_query)
        if not doc_res:
            raise Exception(f"can not found doc:{query_request.document_id}")
        query = {
            "id": query_request.id,
            "doc_id": doc_res.doc_id,
            "doc_name": query_request.doc_name,
            "doc_type": query_request.doc_type,
            "content": query_request.content,
        }
        chunk_res = service.get_chunk_list_page(
            query, query_request.page, query_request.page_size
        )
        chunks = [
            ChunkDetailResponse.to_chunk_serve_response(chunk)
            for chunk in chunk_res.items
        ]

        res = ChunkQueryResponse(
            data=chunks,
            total=chunk_res.total_count,
            page=chunk_res.page,
        )
        return Result.succ(res)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document chunk list error {e}")


@router.post("/knowledge/{space_name}/chunk/edit")
def chunk_edit(
    space_name: str,
    edit_request: ChunkEditRequest,
    service: Service = Depends(get_rag_service),
):
    logger.info(f"/chunk/edit params: {space_name}, {edit_request}")
    try:
        serve_request = ChunkServeRequest(**edit_request.dict())
        serve_request.id = edit_request.chunk_id
        return Result.succ(service.update_chunk(request=serve_request))
    except Exception as e:
        return Result.failed(code="E000X", msg=f"document chunk edit error {e}")


@router.post("/knowledge/{vector_name}/query")
def similarity_query(space_name: str, query_request: KnowledgeQueryRequest):
    logger.info(f"Received params: {space_name}, {query_request}")
    storage_manager = StorageManager.get_instance(CFG.SYSTEM_APP)
    vector_store_connector = storage_manager.create_vector_store(index_name=space_name)
    retriever = EmbeddingRetriever(
        top_k=query_request.top_k, index_store=vector_store_connector
    )
    chunks = retriever.retrieve(query_request.query)
    res = [
        KnowledgeQueryResponse(text=d.content, source=d.metadata["source"])
        for d in chunks
    ]
    return {"response": res}
