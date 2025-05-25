import asyncio
import logging
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
from derisk.util import PaginationResult
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
    ChunkServeResponse,
    KnowledgeDocumentRequest,
    ChunkEditRequest, KnowledgeTaskRequest,
)
from derisk_serve.rag.config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from derisk_serve.rag.service.service import Service


logger = logging.getLogger(__name__)


router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance"""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


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
    service: Service = Depends(get_service),
) -> Result[PaginationResult[SpaceServeResponse]]:
    """Query Space entities

    Args:
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.get_list_by_page({}, page, page_size))


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


@router.post("/spaces/{knowledge_id}/documents/create-file")
async def create_document_text(
    knowledge_id: str,
    doc_name: str = Form(...),
    doc_type: str = Form(...),
    doc_file: UploadFile = File(...),
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(
        f"create_document_text params: {knowledge_id}, {token}, {doc_type}, {doc_name}"
    )

    try:
        request = DocumentServeRequest(
            knowledge_id=knowledge_id,
            doc_name=doc_name,
            doc_type=doc_type,
            doc_file=doc_file,
        )
        return Result.succ(
            await service.create_single_file_knowledge(
                knowledge_id=knowledge_id, request=request
            )
        )
    except Exception as e:
        logger.error(f"create_document_text error {e}")

        return Result.failed(
            err_code="E000X", msg=f"create document text error {str(e)}"
        )


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


@router.post("/spaces/documents/tasks/update")
def update_knowledge_task(
    request: KnowledgeTaskRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
) -> Result:
    logger.info(f"auto_sync_document params: {token}")

    try:
        return Result.succ(
            service.update_knowledge_task(request=request)
        )
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
        return Result.succ(
            service.get_knowledge_task(knowledge_id=knowledge_id)
        )
    except Exception as e:
        logger.error(f"get_knowledge_task error {e}")

        return Result.failed(
            err_code="E000X", msg=f"get knowledge task error {str(e)}"
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
        request.knowledge_id=knowledge_id

        return Result.succ(
            service.delete_knowledge_task(request=request)
        )
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
        return Result.succ(
            await service.init_auto_sync()
        )
    except Exception as e:
        logger.error(f"auto_run error {e}")

        return Result.failed(
            err_code="E000X", msg=f"auto run error {str(e)}"
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


@router.post("/search")
async def search_knowledge(
    request: KnowledgeSearchRequest,
    token: APIToken = Depends(check_api_key),
    service: Service = Depends(get_service),
):
    logger.info(f"search_knowledge params: {request}, {token}")
    try:
        # return Result.succ(await service.asearch_knowledge(request=request))
        return Result.succ(await service.knowledge_search(request=request))
    except Exception as e:
        logger.error(f"search_knowledge error {e}")

        return Result.failed(err_code="E000X", msg=f"search knowledge error! {str(e)}")


@router.get(
    "/spaces/{knowledge_id}/documents/{doc_id}",
    response_model=Result[List],
)
async def query(
    knowledge_id: str,
    doc_id: str,
    service: Service = Depends(get_service),
) -> Result[List[DocumentServeResponse]]:
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


@router.get(
    "/spaces/{knowledge_id}/documents",
    response_model=Result[PaginationResult[DocumentServeResponse]],
)
async def query_page(
    knowledge_id: str,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[DocumentServeResponse]]:
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
    doc_id: str, service: Service = Depends(get_service)
) -> Result[bool]:
    """Delete a Space entity

    Args:
        doc_id (str): doc_id
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"delete_document params: {doc_id}")

    # TODO: Delete the files of the document
    res = await blocking_func_to_async(
        global_system_app, service.delete_document, doc_id
    )
    return Result.succ(res)


@router.get(
    "/spaces/{knowledge_id}/documents/{doc_id}/chunks"
)
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


@router.post("/knowledge/search")
async def knowledge_search(
    request: KnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result:
    """Knowledge Search

    Args:
        request (KnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(await service.knowledge_search(request))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app


def init_documents_auto_run():
    logger.info("init_documents_auto_run start")

    service = get_service()
    service.run_periodic_in_thread()



