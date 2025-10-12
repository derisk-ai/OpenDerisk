import asyncio
import json
import logging
import urllib.parse
from functools import cache
from typing import List, Optional, Union, Any

from fastapi import (
    APIRouter,
    Depends,
    Form,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.util import PaginationResult, pypantic_utils
from derisk_app.openapi.api_view_model import APIToken
from derisk_ext.rag.chunk_manager import ChunkParameters
from derisk_serve.core import Result, blocking_func_to_async
from derisk_serve.rag.api.schemas import (
    DocumentServeRequest,
    DocumentServeResponse,
    KnowledgeRetrieveRequest,
    KnowledgeSyncRequest,
    SpaceServeRequest,
    SpaceServeResponse,
    KnowledgeSearchRequest,
    YuqueRequest,
    ChunkServeResponse,
    KnowledgeDocumentRequest,
    ChunkEditRequest, KnowledgeTaskRequest, SettingsRequest, CreateDocRequest,
    UpdateTocRequest, CreateBookRequest, KnowledgeSetting, QueryGraphProjectRequest, CreateGraphRelationRequest,
)
from derisk_serve.rag.config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig, SERVE_GRAPH_SERVICE_COMPONENT_NAME
from derisk_serve.rag.service.graph.graph_service import GraphService
from derisk_serve.rag.service.service import Service
from derisk_serve.rag.service.yuque_service import YuqueService

logger = logging.getLogger(__name__)


router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance"""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)

def get_graph_service() -> GraphService:
    """Get the graph service instance"""
    return global_system_app.get_component(SERVE_GRAPH_SERVICE_COMPONENT_NAME, GraphService)


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list

    Args:
        api_keys (str): The string api keys

    Returns:
        List[str]: The list of api keys
    """
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key

    If the api key is not set, allow all.

    Your can pass the token in you request header like this:

    .. code-block:: python

        import requests

        client_api_key = "your_api_key"
        headers = {"Authorization": "Bearer " + client_api_key}
        res = requests.get("http://test/hello", headers=headers)
        assert res.status_code == 200

    """
    if service.config.api_keys:
        api_keys = _parse_api_keys(service.config.api_keys)
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return token
    else:
        # api_keys not set; allow all
        return None


@router.get("/health", dependencies=[Depends(check_api_key)])
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


@router.get("/test_auth", dependencies=[Depends(check_api_key)])
async def test_auth():
    """Test auth endpoint"""
    return {"status": "ok"}


@router.post("/spaces")
async def create(
    request: SpaceServeRequest,
    service: Service = Depends(get_service),
) -> Result:
    """Create a new Space entity

    Args:
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.create_space(request))


@router.put("/spaces", dependencies=[Depends(check_api_key)])
async def update(
    request: SpaceServeRequest, service: Service = Depends(get_service)
) -> Result:
    """Update a Space entity

    Args:
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.update_space(request))


@router.delete(
    "/spaces/{knowledge_id}",
    response_model=Result[bool],
    dependencies=[Depends(check_api_key)],
)
async def delete(
    knowledge_id: str, service: Service = Depends(get_service)
) -> Result[bool]:
    """Delete a Space entity

    Args:
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"delete space: {knowledge_id}")

    # TODO: Delete the files in the space
    res = await blocking_func_to_async(global_system_app, service.delete, knowledge_id)
    return Result.succ(res)


@router.put(
    "/spaces/{knowledge_id}",
    response_model=Result[bool],
    dependencies=[Depends(check_api_key)],
)
async def update(
    knowledge_id: str,
    request: SpaceServeRequest,
    service: Service = Depends(get_service),
) -> Result[bool]:
    logger.info(f"update space: {knowledge_id} {request}")
    try:
        request.knowledge_id = knowledge_id

        return Result.succ(service.update_space_by_knowledge_id(update=request))
    except Exception as e:
        logger.error(f"update space error {e}")

        return Result.failed(err_code="E000X", msg=f"update space error {str(e)}")


@router.get(
    "/spaces/{knowledge_id}",
    response_model=Result[SpaceServeResponse],
)
async def query(
    knowledge_id: str,
    service: Service = Depends(get_service),
) -> Result[SpaceServeResponse]:
    """Query Space entities

    Args:
        knowledge_id (str): The knowledge_id
        service (Service): The service
    Returns:
        List[ServeResponse]: The response
    """
    request = {"knowledge_id": knowledge_id}
    return Result.succ(service.get(request))


@router.get(
    "/spaces",
    response_model=Result[PaginationResult[SpaceServeResponse]],
)
async def query_page(
    page: int = Query(default=1, description="current page"),
    page_size: int = Query(default=20, description="page size"),
    is_public: Optional[str] = Query(default=None, description="is_public"),
    service: Service = Depends(get_service),
) -> Result[PaginationResult[SpaceServeResponse]]:
    """Query Space entities

    Args:
        page (int): The page number
        page_size (int): The page size
        is_public (str): The is_public
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    request = {}
    if is_public:
        request["knowledge_type"] = "PUBLIC"
    return Result.succ(service.get_list_by_page(request, page, page_size))


@router.get(
    "/knowledge_ids",
)
async def get_knowledge_ids(
    category: Optional[str] = None,
    knowledge_type: Optional[str] = None,
    name_or_tag: Optional[str] = None,
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"get_knowledge_ids params: {category} {knowledge_type} {name_or_tag}")

    try:
        request = SpaceServeRequest(
            category=category, knowledge_type=knowledge_type, name_or_tag=name_or_tag
        )

        return Result.succ(service.get_knowledge_ids(request=request))
    except Exception as e:
        logger.error(f"get_knowledge_ids error {e}")

        return Result.failed(err_code="E000X", msg=f"get knowledge ids error {str(e)}")


@router.post("/spaces/{knowledge_id}/retrieve")
async def space_retrieve(
    knowledge_id: int,
    request: KnowledgeRetrieveRequest,
    service: Service = Depends(get_service),
) -> Result:
    """Create a new Document entity

    Args:
        knowledge_id (int): The space id
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    request.knowledge_id = knowledge_id
    space_request = {
        "knowledge_id": knowledge_id,
    }
    space = service.get(space_request)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    return Result.succ(await service.retrieve(request, space))


@router.post("/spaces/{knowledge_id}/documents/create-text")
async def create_document_text(
    knowledge_id: str,
    request: KnowledgeDocumentRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"create_document_text params: {knowledge_id}, {token}")

    try:
        request.knowledge_id = knowledge_id
        return Result.succ(
            await service.create_single_document_knowledge(
                knowledge_id=knowledge_id, request=request
            )
        )
    except Exception as e:
        logger.error(f"create_document_text error {e}")

        return Result.failed(
            err_code="E000X", msg=f"create document text error {str(e)}"
        )


@router.post("/spaces/{knowledge_id}/documents/create-file")
async def create_file(
    knowledge_id: str,
    file: UploadFile = File(...),
    file_params: str = Form(None),
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"create_document_file params: {knowledge_id}, {token}")

    try:
        document_request = DocumentServeRequest(
            doc_type="DOCUMENT",
            knowledge_id=knowledge_id,
            meta_data=json.loads(file_params) if file_params else {},
        )
        if file:
            document_request.doc_file = file
            file.filename = urllib.parse.unquote(file.filename, encoding='utf-8')
        doc = await blocking_func_to_async(
            global_system_app, service.create_document, document_request
        )
        doc_id = doc.doc_id
        asyncio.create_task(
            service.create_knowledge_document_and_sync(
                knowledge_id=knowledge_id,
                request=KnowledgeDocumentRequest(**document_request.dict()),
                doc_id=doc_id,
            )
        )
        return Result.succ(doc_id)
    except Exception as e:
        logger.error(f"create file error {e}")

        return Result.failed(
            err_code="E000X", msg=f"create document file error {str(e)}"
        )

@router.post("/spaces/{knowledge_id}/documents/upload")
async def upload_document(
    knowledge_id: str,
    file: UploadFile = File(...),
    file_params: str = Form(None),
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"document upload params: {knowledge_id}, {token}")

    try:
        document_request = DocumentServeRequest(
            doc_type="DOCUMENT",
            knowledge_id=knowledge_id,
            meta_data=json.loads(file_params) if file_params else {},
        )
        if file:
            document_request.doc_file = file
            file.filename = urllib.parse.unquote(file.filename, encoding='utf-8')
        doc = await blocking_func_to_async(
            global_system_app, service.create_document, document_request
        )
        doc_id = doc.doc_id

        return Result.succ(doc_id)
    except Exception as e:
        logger.error(f"upload document error {e}")

        return Result.failed(
            err_code="E000X", msg=f"upload document file error {str(e)}"
        )

@router.post("/spaces/{knowledge_id}/documents/sync")
async def sync_single_document(
    knowledge_id: str,
    request: KnowledgeDocumentRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"single document sync params: {knowledge_id}, {request}, {token}")

    try:
        request.knowledge_id = knowledge_id

        return Result.succ(await service.sync_single_document(request=request))
    except Exception as e:
        logger.error(f"single document sync error {e}")

        return Result.failed(err_code="E000X", msg=f"single document sync error {str(e)}")


@router.post("/spaces/{knowledge_id}/documents/create-yuque")
async def create_document_yuque(
    knowledge_id: str,
    request: YuqueRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    """Create a new Document entity

    Args:
        knowledge_id (str): knowledge_id
        request (YuqueRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"create_document_yuque params: {knowledge_id}, {token}")

    try:
        request.knowledge_id = knowledge_id
        return Result.succ(
            await service.create_batch_yuque_knowledge_and_sync(requests=[request])
        )
    except Exception as e:
        logger.error(f"create_document_yuque error {e}")

        return Result.failed(
            err_code="E000X", msg=f"create document yuque error {str(e)}"
        )


@router.post("/spaces/{knowledge_id}/documents/batch-create-yuque")
async def batch_create_document_yuque(
    knowledge_id: str,
    requests: List[YuqueRequest],
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"batch_create_document_yuque params: {knowledge_id}, {token}")

    try:
        for request in requests:
            request.knowledge_id = knowledge_id

        return Result.succ(
            await service.create_batch_yuque_knowledge_and_sync_v2(requests=requests)
        )
    except Exception as e:
        logger.error(f"batch_create_document_yuque error {e}")

        return Result.failed(
            err_code="E000X", msg=f"batch create document yuque error {str(e)}"
        )


@router.post("/spaces/documents/tasks/update")
def update_knowledge_task(
    request: KnowledgeTaskRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"auto_sync_document params: {token}")

    try:
        return Result.succ(service.update_knowledge_task(request=request))
    except Exception as e:
        logger.error(f"update_knowledge_task error {e}")

        return Result.failed(
            err_code="E000X", msg=f"update knowledge task  error {str(e)}"
        )


@router.get("/spaces/{knowledge_id}/tasks")
def get_knowledge_task(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"get_knowledge_task params: {token}")

    try:
        return Result.succ(service.get_knowledge_task(knowledge_id=knowledge_id))
    except Exception as e:
        logger.error(f"get_knowledge_task error {e}")

        return Result.failed(err_code="E000X", msg=f"get knowledge task error {str(e)}")


@router.get("/spaces/{knowledge_id}/{group_login}/{book_slug}/tasks")
def get_knowledge_task_with_book_slug(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"get_knowledge_task_with_book_slug params: {token}")

    try:
        return Result.succ(
            service.get_knowledge_task_with_book_slug(
                knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug
            )
        )
    except Exception as e:
        logger.error(f"get_knowledge_task_with_book_slug error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get knowledge task with book slug error {str(e)}"
        )


@router.delete("/spaces/{knowledge_id}/tasks")
def delete_knowledge_task(
    knowledge_id: str,
    request: KnowledgeTaskRequest = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"get_knowledge_task params: {token}")

    try:
        request.knowledge_id = knowledge_id

        return Result.succ(service.delete_knowledge_task(request=request))
    except Exception as e:
        logger.error(f"delete_knowledge_task error {e}")

        return Result.failed(
            err_code="E000X", msg=f"delete knowledge task error {str(e)}"
        )


@router.post("/spaces/documents/auto-run")
async def auto_run(
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"auto_run params: {token}")

    try:
        return Result.succ(await service.init_auto_sync())
    except Exception as e:
        logger.error(f"auto_run error {e}")

        return Result.failed(err_code="E000X", msg=f"auto run error {str(e)}")


@router.get("/spaces/{knowledge_id}/books/yuque/dir")
async def get_book_dir(
    knowledge_id: str,
    group_login: str,
    yuque_token: str = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"get_book_dir params: {knowledge_id}, {group_login}, {token}")

    try:
        return Result.succ(await service.get_book_dir(knowledge_id=knowledge_id, group_login=group_login, yuque_token=yuque_token))
    except Exception as e:
        logger.error(f"get_book_dir error {e}")

        return Result.failed(err_code="E000X", msg=f"get book dir error {str(e)}")


@router.post("/spaces/{knowledge_id}/documents/yuque/reimport")
async def reimport_yuque_knowledge(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"reimport_yuque_knowledge params: {knowledge_id},{token}")

    try:
        return Result.succ(await service.reimport_yuque_knowledge(knowledge_id=knowledge_id))
    except Exception as e:
        logger.error(f"reimport_yuque_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"reimport yuque knowledge error {str(e)}")


@router.get("/spaces/{knowledge_id}/documents/yuque/dir")
async def get_yuque_dir(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"get_yuque_dir params: {knowledge_id},{token}")

    try:
        return Result.succ(await service.get_yuque_dir(knowledge_id=knowledge_id))
    except Exception as e:
        logger.error(f"get_yuque_dir error {e}")

        return Result.failed(err_code="E000X", msg=f"get yuque dir error {str(e)}")


@router.get("/spaces/{knowledge_id}/documents/ls")
async def list_docs(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    doc_type: Optional[str] = None,
    display_tree: Optional[bool] = True,
    service: Service = Depends(get_service),
):
    logger.info(f"ls_docs params: {knowledge_id},{token}")

    try:
        return Result.succ(await service.list_docs(knowledge_id=knowledge_id, doc_type=doc_type, display_tree=display_tree))
    except Exception as e:
        logger.error(f"list_docs error {e}")

        return Result.failed(err_code="E000X", msg=f"list docs error {str(e)}")


@router.get("/spaces/{knowledge_id}/documents/read")
async def read_doc(
    knowledge_id: str,
    file_path: str,
    doc_id: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"read_doc params: {knowledge_id},{token}")

    try:
        return Result.succ(await service.read_doc(knowledge_id=knowledge_id, doc_id=doc_id, file_path=file_path))
    except Exception as e:
        logger.error(f"read_doc error {e}")

        return Result.failed(err_code="E000X", msg=f"read doc error {str(e)}")

@router.post("/spaces/{knowledge_id}/documents/write")
async def write_doc(
    knowledge_id: str,
    request: CreateDocRequest = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"write_doc params: {knowledge_id},{token}")

    try:
        return Result.succ(await service.check_exists_and_write_doc(knowledge_id=knowledge_id, request=request))
    except Exception as e:
        logger.error(f"write_doc error {e}")

        return Result.failed(err_code="E000X", msg=f"write doc error {str(e)}")


@router.get("/spaces/{knowledge_id}/documents/yuque/{group_login}/{book_slug}/docs")
async def get_yuque_book_docs(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(
        f"get_yuque_book_docs params: {knowledge_id}, {group_login}, {book_slug}, {token}"
    )

    try:
        return Result.succ(
            service.get_yuque_book_docs(
                knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug
            )
        )
    except Exception as e:
        logger.error(f"get_yuque_book_docs error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get yuque book docs error {str(e)}"
        )


@router.post("/spaces/{knowledge_id}/documents/delete")
async def delete_document_knowledge(
    knowledge_id: str,
    request: KnowledgeDocumentRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"delete_document_knowledge params: {request}, {token}")

    try:
        return Result.succ(
            await service.delete_documents(
                knowledge_id=knowledge_id, doc_id=request.doc_id
            )
        )
    except Exception as e:
        logger.error(f"delete_document_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"document delete error! {str(e)}")


@router.post(
    "/spaces/{knowledge_id}/documents/{group_login}/{book_slug}/{doc_slug}/retry"
)
async def retry_document_knowledge(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    doc_slug: str,
    request: KnowledgeDocumentRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"retry_document_knowledge params: {request}, {token}")
    try:
        request.knowledge_id = knowledge_id
        request.yuque_group_login = group_login
        request.yuque_book_slug = book_slug
        request.yuque_doc_slug = doc_slug

        return Result.succ(
            await service.retry_knowledge_space(
                knowledge_id=knowledge_id, request=request
            )
        )
    except Exception as e:
        logger.error(f"retry_document_knowledge error {e}")

        return Result.failed(
            err_code="E000X", msg=f"retry document knowledge error! {str(e)}"
        )


@router.delete("/spaces/{knowledge_id}/documents/{group_login}/{book_slug}/{doc_slug}")
async def delete_yuque_knowledge(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    doc_slug: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(
        f"delete_yuque_knowledge params: {knowledge_id}, {group_login}, {book_slug}, {token}"
    )
    try:
        request = KnowledgeDocumentRequest(
            knowledge_id=knowledge_id,
            yuque_group_login=group_login,
            yuque_book_slug=book_slug,
            yuque_doc_slug=doc_slug,
        )

        return Result.succ(
            await service.delete_yuque_knowledge(
                knowledge_id=knowledge_id, request=request
            )
        )
    except Exception as e:
        logger.error(f"delete_yuque_knowledge error {e}")

        return Result.failed(
            err_code="E000X", msg=f"delete yuque knowledge error! {str(e)}"
        )


@router.post("/spaces/{knowledge_id}/documents/{doc_id}/split")
async def split_yuque_knowledge(
    knowledge_id: str,
    doc_id: str,
    request: YuqueRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"split_yuque_knowledge params: {request}, {token}")

    try:
        request.knowledge_id = knowledge_id
        request.doc_id = doc_id
        return Result.succ(await service.split_yuque_knowledge(request=request))
    except Exception as e:
        logger.error(f"split_yuque_knowledge error {e}")

        return Result.failed(
            err_code="E000X", msg=f"split yuque knowledge error {str(e)}"
        )


@router.get("/spaces/{knowledge_id}/documents/{doc_id}/outlines")
def get_yuque_knowledge_outlines(
    knowledge_id: str,
    doc_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(
        f"get_yuque_knowledge_outlines params: {knowledge_id}, {doc_id}, {token}"
    )

    try:
        return Result.succ(
            service.get_yuque_knowledge_outlines(
                knowledge_id=knowledge_id, doc_id=doc_id
            )
        )
    except Exception as e:
        logger.error(f"get_yuque_knowledge_outlines error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get yuque knowledge outlines error {str(e)}"
        )

@router.get("/spaces/{knowledge_id}/documents/{doc_id}/outlines/all")
def get_yuque_knowledge_all_outlines(
    knowledge_id: str,
    doc_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(
        f"get_yuque_knowledge_all_outlines params: {knowledge_id}, {doc_id}, {token}"
    )

    try:
        return Result.succ(
            service.get_yuque_knowledge_all_outlines(
                knowledge_id=knowledge_id, doc_id=doc_id
            )
        )
    except Exception as e:
        logger.error(f"get_yuque_knowledge_all_outlines error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get yuque knowledge all outlines error {str(e)}"
        )

@router.post("/spaces/{knowledge_id}/documents/{group_login}/{book_slug}")
async def create_yuque_book(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    request: YuqueRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"create_yuque_book params: {knowledge_id}, {token}")

    try:
        request.knowledge_id=knowledge_id
        request.group_login=group_login
        request.book_slug=book_slug

        return Result.succ(
            await service.create_yuque_book(request=request)
        )
    except Exception as e:
        logger.error(f"create_yuque_book error {e}")

        return Result.failed(
            err_code="E000X", msg=f"create yuque book error {str(e)}"
        )


@router.delete("/spaces/{knowledge_id}/documents/{group_login}/{book_slug}")
async def delete_yuque_book(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(
        f"delete_yuque_book_docs params: {knowledge_id}, {group_login}, {book_slug}, {token}"
    )

    try:
        return Result.succ(
            service.delete_yuque_book(knowledge_id, group_login, book_slug)
        )
    except Exception as e:
        logger.error(f"delete_yuque_book_docs error {e}")

        return Result.failed(err_code="E000X", msg=f"delete yuque book error {str(e)}")


@router.get("/spaces/documents/chunkstrategies")
def get_chunk_strategies(
    suffix: Optional[str] = None,
    type: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"get_chunk_strategies params: {suffix}, {type} {token}")

    try:
        return Result.succ(service.get_chunk_strategies(suffix=suffix, type=type))

    except Exception as e:
        logger.error(f"get_chunk_strategies error {e}")

        return Result.failed(
            err_code="E000X", msg=f"chunk strategies get error! {str(e)}"
        )

@router.get("/spaces/documents/{doc_id}/chunkstrategy")
def get_doc_sync_strategy(
    doc_id: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"get_doc_strategy params: {doc_id} {token}")

    try:
        return Result.succ(service.get_doc_sync_strategy(doc_id=doc_id))

    except Exception as e:
        logger.error(f"get_doc_sync_strategy error {e}")

        return Result.failed(
            err_code="E000X", msg=f"doc chunk strategies get error! {str(e)}"
        )


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"search_knowledge params: {request}, {token}")
    try:
        # return Result.succ(await service.asearch_knowledge(request=request))
        knowledge_res = await service.knowledge_search(request=request)
        for document in knowledge_res.document_response_list:
            if document.metadata:
                document.knowledge_id = document.metadata.get("knowledge_id")
                document.doc_id = document.metadata.get("doc_id")
                document.yuque_url = document.metadata.get("yuque_url")
        return Result.succ(knowledge_res)
    except Exception as e:
        logger.error(f"search_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"search knowledge error! {str(e)}")


@router.get(
    "/spaces/{knowledge_id}/documents/{doc_id}"
)
async def query(
    knowledge_id: str,
    doc_id: str,
    service: Service = Depends(get_service),
) -> Result[DocumentServeResponse]:
    """Get Document

    Args:
        knowledge_id (str): The knowledge_id
        doc_id (str): The doc_id
        service (Service): The service
    Returns:
        List[ServeResponse]: The response
    """
    request = {"doc_id": doc_id, "knowledge_id": knowledge_id}
    return Result.succ(service.get_document(request))


@router.put(
    "/spaces/{knowledge_id}/documents/{doc_id}",
    response_model=Result[List],
)
async def update(
    knowledge_id: str,
    doc_id: str,
    request: Optional[DocumentServeRequest] = None,
    service: Service = Depends(get_service),
) -> Result[List[DocumentServeResponse]]:
    """Get Document

    Args:
        knowledge_id (str): The knowledge_id
        doc_id (str): The doc_id
        request (dict): The metadata
        service (Service): The service
    Returns:
        List[ServeResponse]: The response
    """
    request.knowledge_id = knowledge_id
    request.doc_id = doc_id
    return Result.succ(service.update_document(request))


@router.get(
    "/spaces/{knowledge_id}/documents",
    response_model=Result[List[DocumentServeResponse]],
)
async def query_page(
    knowledge_id: str,
    service: Service = Depends(get_service),
) -> Result[List[DocumentServeResponse]]:
    """Query Space entities

    Args:
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(
        service.get_document_list(
            {
                "knowledge_id": knowledge_id,
            }
        )
    )


@router.post("/documents/chunks/add")
async def add_documents_chunks(
    doc_name: str = Form(...),
    knowledge_id: int = Form(...),
    content: List[str] = Form(None),
    service: Service = Depends(get_service),
) -> Result:
    """ """


@router.post("/documents/sync", dependencies=[Depends(check_api_key)])
async def sync_documents(
    requests: List[KnowledgeSyncRequest], service: Service = Depends(get_service)
) -> Result:
    """Create a new Document entity

    Args:
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.sync_document(requests))


@router.post("/documents/batch_sync")
async def sync_documents(
    requests: List[KnowledgeSyncRequest],
    service: Service = Depends(get_service),
) -> Result:
    """Create a new Document entity

    Args:
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.sync_document(requests))


@router.post("/documents/{document_id}/sync")
async def sync_document(
    document_id: str,
    request: KnowledgeSyncRequest,
    service: Service = Depends(get_service),
) -> Result:
    """Create a new Document entity

    Args:
        request (SpaceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    request.doc_id = document_id
    if request.chunk_parameters is None:
        request.chunk_parameters = ChunkParameters(chunk_strategy="Automatic")
    return Result.succ(service.sync_document([request]))


@router.delete(
    "/spaces/{knowledge_id}/documents/{doc_id}",
    dependencies=[Depends(check_api_key)],
    response_model=Result[None],
)
async def delete_document(
    knowledge_id: str,
    doc_id: str,
    service: Service = Depends(get_service)
) -> Result[bool]:
    """Delete a Space entity

    Args:
        doc_id (str): doc_id
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"delete_document params: {knowledge_id}, {doc_id}")

    # TODO: Delete the files of the document
    res = await blocking_func_to_async(
        global_system_app, service.delete_document_by_doc_id, knowledge_id, doc_id
    )
    return Result.succ(res)


@router.get("/spaces/{knowledge_id}/documents/{doc_id}/chunks")
async def chunk_list(
    knowledge_id: str,
    doc_id: str,
    first_level_header: Optional[str] = None,
    service: Service = Depends(get_service),
) -> Result[List[ChunkServeResponse]]:
    """Query Space entities

    Args:
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"chunk_list params: {knowledge_id}, {doc_id}, {first_level_header}")
    try:
        request = ChunkEditRequest()
        request.knowledge_id = knowledge_id
        request.doc_id = doc_id
        request.first_level_header = first_level_header.strip()

        return Result.succ(service.get_chunks(request=request))
    except Exception as e:
        logger.error(f"chunk_list error {e}")

        return Result.failed(err_code="E000X", msg=f"get chunk  error! {str(e)}")


@router.get("/spaces/{knowledge_id}/documents/{doc_id}/full_text")
async def get_full_text(
    knowledge_id: str,
    doc_id: str,
    service: Service = Depends(get_service),
) -> Result[ChunkServeResponse]:
    """Query Space entities

    Args:
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"get_full_text params: {knowledge_id}, {doc_id}")
    try:
        request = ChunkEditRequest()
        request.knowledge_id = knowledge_id
        request.doc_id = doc_id

        return Result.succ(service.get_full_text(request=request))
    except Exception as e:
        logger.error(f"get_full_text error {e}")

        return Result.failed(err_code="E000X", msg=f"get full text  error! {str(e)}")


@router.put("/spaces/{knowledge_id}/documents/{doc_id}/chunks/{chunk_id}")
async def edit_chunk(
    knowledge_id: str,
    doc_id: str,
    chunk_id: str,
    request: ChunkEditRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"edit_chunk params: {request}, {token}")
    try:
        request.knowledge_id = knowledge_id
        request.doc_id = doc_id
        request.chunk_id = chunk_id

        return Result.succ(service.edit_chunk(request=request))
    except Exception as e:
        logger.error(f"edit_chunk error {e}")

        return Result.failed(err_code="E000X", msg=f"edit chunk  error! {str(e)}")


"""avoid router name conflict"""
@router.delete("/spaces/{knowledge_id}/chunks/{chunk_id}")
async def delete_chunk(
    knowledge_id: str,
    chunk_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"delete_chunk params: {knowledge_id}, {chunk_id}, {token}")
    try:
        request = ChunkEditRequest()
        request.knowledge_id = knowledge_id
        request.chunk_id = chunk_id

        return Result.succ(service.delete_chunk(request=request))
    except Exception as e:
        logger.error(f"delete_chunk error {e}")

        return Result.failed(err_code="E000X", msg=f"delete chunk  error! {str(e)}")

@router.post("/spaces/{knowledge_id}/documents/{group_login}/{book_slug}/refresh")
async def refresh_book(
    knowledge_id: str,
    group_login: str,
    book_slug: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(
        f"refresh_book params: {knowledge_id}, {group_login}, {book_slug}, {token}"
    )

    try:
        asyncio.create_task(service.refresh_knowledge_v2(knowledge_id=knowledge_id, group_login=group_login, book_slug=book_slug))

        return Result.succ(True)
    except Exception as e:
        logger.error(f"refresh_book error {e}")

        return Result.failed(
            err_code="E000X", msg=f"refresh book docs error {str(e)}"
        )


@router.post("/spaces/{knowledge_id}/refresh")
async def refresh_knowledge(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    """
    保鲜知识库：已导入的知识库和原始知识库保持一致
    """
    logger.info(f"refresh_knowledge params: {knowledge_id}, {token}")
    try:

        return Result.succ(await service.refresh_knowledge(knowledge_id=knowledge_id))
    except Exception as e:
        logger.error(f"refresh_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"refresh knowledge error! {str(e)}")


@router.post("/spaces/{knowledge_id}/refresh/v2")
async def refresh_knowledge_v2(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    """
    托管知识库：和原始知识库保持一致
    """
    logger.info(f"refresh_knowledge_v2 params: {knowledge_id}, {token}")
    try:
        asyncio.create_task(service.refresh_knowledge_v2(knowledge_id=knowledge_id))

        return Result.succ(True)
    except Exception as e:
        logger.error(f"refresh_knowledge_v2 error {e}")

        return Result.failed(err_code="E000X", msg=f"refresh knowledge v2 error! {str(e)}")


@router.post("/spaces/refresh/scheduled")
async def start_scheduled_refresh(
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    """
    手动触发一次：定时同步知识库
    """
    logger.info(f"start_scheduled_refresh params: {token}")
    try:
        return Result.succ(await service.start_scheduled_refresh())
    except Exception as e:
        logger.error(f"start_scheduled_refresh error {e}")

        return Result.failed(err_code="E000X", msg=f"start scheduled refresh error! {str(e)}")


@router.delete("/spaces/refresh/records")
def delete_refresh_records(
    refresh_id: Optional[str] = None,
    refresh_time: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"delete_refresh_records params: {refresh_id}, {refresh_time}, {token}")
    try:
        return Result.succ(
            service.delete_refresh_records(
                refresh_id=refresh_id, refresh_time=refresh_time
            )
        )
    except Exception as e:
        logger.error(f"delete_refresh_records error {e}")

        return Result.failed(
            err_code="E000X", msg=f"delete refresh records error! {str(e)}"
        )


@router.put("/yuque/repos/{group_login}/{book_slug}/docs")
def update_yuque_docs(
    group_login: Optional[str] = None,
    book_slug: Optional[str] = None,
    request: Optional[CreateDocRequest] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"update_yuque_docs params: {group_login}, {book_slug}, {request}, {token}")
    try:
        return Result.succ(
            service.update_yuque_docs(group_login=group_login, book_slug=book_slug, request=request)
        )
    except Exception as e:
        logger.error(f"update_yuque_docs error {e}")

        return Result.failed(
            err_code="E000X", msg=f"update yuque docs error! {str(e)}"
        )

@router.post("/yuque/repos/{group_login}/{book_slug}/docs")
def create_yuque_doc(
    group_login: Optional[str] = None,
    book_slug: Optional[str] = None,
    request: Optional[CreateDocRequest] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"create_yuque_doc params: {group_login}, {book_slug}, {request}, {token}")
    try:
        return Result.succ(
            service.create_yuque_doc(group_login=group_login, book_slug=book_slug, request=request)
        )
    except Exception as e:
        logger.error(f"create_yuque_doc error {e}")

        return Result.failed(
            err_code="E000X", msg=f"create yuque doc error! {str(e)}"
        )

@router.put("/yuque/repos/{group_login}/{book_slug}/toc")
def update_yuque_toc(
    group_login: Optional[str] = None,
    book_slug: Optional[str] = None,
    request: Optional[UpdateTocRequest] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"update_yuque_toc params: {group_login}, {book_slug}, {request}, {token}")
    try:
        return Result.succ(
            service.update_yuque_toc(group_login=group_login, book_slug=book_slug, request=request)
        )
    except Exception as e:
        logger.error(f"update_yuque_toc error {e}")

        return Result.failed(
            err_code="E000X", msg=f"update yuque toc error! {str(e)}"
        )


@router.get("/yuque/repos/{group_login}/{book_slug}/toc")
def get_yuque_toc(
    group_login: Optional[str] = None,
    book_slug: Optional[str] = None,
    yuque_token: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"get_yuque_toc params: {group_login}, {book_slug}, {yuque_token}, {token}")
    try:
        return Result.succ(
            service.get_yuque_toc(group_login=group_login, book_slug=book_slug, yuque_token=yuque_token)
        )
    except Exception as e:
        logger.error(f"get_yuque_toc error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get yuque toc error! {str(e)}"
        )


@router.get("/yuque/repos/{group_login}/{book_slug}/outline")
def get_yuque_outline(
    group_login: Optional[str] = None,
    book_slug: Optional[str] = None,
    yuque_token: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"get_yuque_outline params: {group_login}, {book_slug}, {yuque_token}, {token}")
    try:
        return Result.succ(
            service.get_beautify_yuque_book_outline(group_login=group_login, book_slug=book_slug, yuque_token=yuque_token)
        )
    except Exception as e:
        logger.error(f"get_yuque_outline error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get yuque outline error! {str(e)}"
        )

@router.get("/yuque/docs/{group_login}/{book_slug}/{doc_slug}")
def get_yuque_doc(
    group_login: Optional[str] = None,
    book_slug: Optional[str] = None,
    doc_slug: Optional[str] = None,
    yuque_token: Optional[str] = None,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"get_yuque_doc params: {group_login}, {book_slug}, {doc_slug}, {yuque_token}, {token}")
    try:
        return Result.succ(
            service.get_yuque_doc(group_login=group_login, book_slug=book_slug, doc_slug=doc_slug, yuque_token=yuque_token)
        )
    except Exception as e:
        logger.error(f"get_yuque_doc error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get yuque doc error! {str(e)}"
        )


@router.post("/spaces/public/knowledge/{knowledge_id}/backup")
async def backup_public_knowledge(
    knowledge_id: str,
    request: CreateBookRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"backup_knowledge params: {knowledge_id}, {request}, {token}")
    try:
        return Result.succ(await service.backup_knowledge(knowledge_id=knowledge_id, request=request))
    except Exception as e:
        logger.error(f"backup_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"backup knowledge error! {str(e)}")


@router.post("/spaces/public/knowledge/backup")
async def backup_all_public_knowledge(
    request: CreateBookRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"backup_all_public_knowledge params:  {request}, {token}")
    try:
        asyncio.create_task(service.abackup_all_public_knowledge(request=request))

        return Result.succ(True)
    except Exception as e:
        logger.error(f"backup_all_public_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"backup all public knowledge error! {str(e)}")


@router.get("/graph/projects")
async def get_graph_projects(
    user_token: str,
    token: APIToken = Depends(check_api_key),
    graph_service: GraphService = Depends(get_graph_service),
) -> Result[Any]:
    logger.info(f"get_graph_projects params:  {user_token}, {token}")
    try:
        request = QueryGraphProjectRequest(user_token=user_token)
        return Result.succ(graph_service.get_graph_projects(request=request))
    except Exception as e:
        logger.error(f"get_graph_projects error {e}")

        return Result.failed(err_code="E000X", msg=f"get graph projects error! {str(e)}")

@router.post("/graph/{project_id}/node/init")
async def init_graph_nodes(
    project_id: str,
    request: CreateGraphRelationRequest,
    token: APIToken = Depends(check_api_key),
    graph_service: GraphService = Depends(get_graph_service),
) -> Result[Any]:
    logger.info(f"init_graph_nodes params:  {request}, {token}")
    try:
        request.project_id = project_id
        return Result.succ(graph_service.init_graph_nodes(request=request))
    except Exception as e:
        logger.error(f"init_graph_nodes error {e}")

        return Result.failed(err_code="E000X", msg=f"init graph nodes error! {str(e)}")

@router.post("/spaces/{knowledge_id}/graph/init")
async def init_graph_relation(
    knowledge_id: str,
    request: CreateGraphRelationRequest,
    token: APIToken = Depends(check_api_key),
    graph_service: GraphService = Depends(get_graph_service),
) -> Result[Any]:
    logger.info(f"init_graph_relation params:  {request}, {token}")
    try:
        request.knowledge_id = knowledge_id
        return Result.succ(graph_service.create_graph_relation(request=request))
    except Exception as e:
        logger.error(f"init_graph_relation error {e}")

        return Result.failed(err_code="E000X", msg=f"init graph relation error! {str(e)}")

@router.post("/spaces/{knowledge_id}/graph/relation")
async def create_graph_relation(
    knowledge_id: str,
    request: CreateGraphRelationRequest,
    token: APIToken = Depends(check_api_key),
    graph_service: GraphService = Depends(get_graph_service),
) -> Result[Any]:
    logger.info(f"create_graph_relation params:  {request}, {token}")
    try:
        request.knowledge_id = knowledge_id
        return Result.succ(graph_service.create_graph_relation(request=request))
    except Exception as e:
        logger.error(f"create_graph_relation error {e}")

        return Result.failed(err_code="E000X", msg=f"create graph relation error! {str(e)}")


@router.get("/spaces/{knowledge_id}/graph/relation")
async def get_graph_relation(
    knowledge_id: str,
    token: APIToken = Depends(check_api_key),
    graph_service: GraphService = Depends(get_graph_service),
) -> Result[Any]:
    logger.info(f"get_graph_relation params:  {knowledge_id}, {token}")
    try:
        return Result.succ(graph_service.get_graph_relation(knowledge_id=knowledge_id))
    except Exception as e:
        logger.error(f"get_graph_relation error {e}")

        return Result.failed(err_code="E000X", msg=f"get graph relation error! {str(e)}")


@router.post("/spaces/{knowledge_id}/graph/full")
async def get_full_graph(
    knowledge_id: str,
    request: CreateGraphRelationRequest,
    token: APIToken = Depends(check_api_key),
    graph_service: GraphService = Depends(get_graph_service),
) -> Result[Any]:
    logger.info(f"get_full_graph params:  {request}, {token}")
    try:
        request.knowledge_id = knowledge_id
        return Result.succ(graph_service.get_full_graph(request=request))
    except Exception as e:
        logger.error(f"get_full_graph error {e}")

        return Result.failed(err_code="E000X", msg=f"get full graph error! {str(e)}")


@router.post("/settings")
def create_settings(
    request: SettingsRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"create_settings params: {request}, {token}")
    try:
        return Result.succ(service.create_settings(request=request))
    except Exception as e:
        logger.error(f"create_settings error {e}")

        return Result.failed(err_code="E000X", msg=f"create settings error! {str(e)}")

@router.put("/settings/{setting_key}")
def update_settings(
    setting_key: str,
    request: SettingsRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result[Any]:
    logger.info(f"create_settings params: {setting_key}, {request}, {token}")
    try:
        request.setting_key = setting_key
        return Result.succ(service.update_settings(request=request))
    except Exception as e:
        logger.error(f"update_settings error {e}")

        return Result.failed(err_code="E000X", msg=f"update settings error! {str(e)}")


@router.get(
    "/spaces/{knowledge_id}/settings",
    response_model=Result[List[dict]],
)
async def knowledge_setting(
    knowledge_id: str,
    service: Service = Depends(get_service),
) -> Result[List[dict]]:
    """Query Space entities

    Args:
        knowledge_id (str): knowledge id
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    try:
        return Result.succ(service.get_knowledge_settings(knowledge_id=knowledge_id))
    except Exception as e:
        logger.error(f"get knowledge setting error {e}")
        return Result.failed(err_code="E000X", msg=f"knowledge settings error! {str(e)}")


@router.put(
    "/spaces/{knowledge_id}/settings",
)
async def knowledge_setting(
    knowledge_id: str,
    request: KnowledgeSetting,
    service: Service = Depends(get_service),
):
    """Query Space entities

    Args:
        knowledge_id (str): knowledge id
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    try:
        return Result.succ(service.update_knowledge_settings(knowledge_id=knowledge_id, request=request))
    except Exception as e:
        logger.error(f"update knowledge setting error {e}")
        return Result.failed(err_code="E000X", msg=f"update knowledge settings error! {str(e)}")



@router.get(
    "/trace/flows",
    response_model=Result[List],
)
async def query_flows(
    message_id: Optional[str] = Query(default=None, description="message_id"),
    conv_id: Optional[str] = Query(default=None, description="conv_id"),
    app_code: Optional[str] = Query(default=None, description="app_code"),
    service: Service = Depends(get_service),
) -> Result[List]:
    """Query Space entities

    Args:
        message_id (int): The page number
        conv_id (int): The page size
        app_code (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    try:
        request = {
            "message_id": message_id,
            "conv_id": conv_id,
            "app_code": app_code,
        }
        return Result.succ(service.get_rag_flow_stages(request))
    except Exception as e:
        logger.error(f"get rag flow error {e}")


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    system_app.register(GraphService, config=config)
    system_app.register(YuqueService, config=config)
    global_system_app = system_app


def init_documents_auto_run():
    logger.info("init_documents_auto_run start")

    service = get_service()
    service.run_periodic_in_thread()
