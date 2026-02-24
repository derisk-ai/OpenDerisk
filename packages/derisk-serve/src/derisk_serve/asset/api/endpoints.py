import logging
from functools import cache
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Request
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.util import PaginationResult
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import (
    AssetKnowledgeSearchRequest,
    AssetDocumentResponse, AssetKnowledgeResponse, AssetToolResponse,
    AssetAgentResponse, AssetKnowledgeCreateRequest, AssetDocumentRequest,
    AssetToolRequest, AssetAgentRequest,
)

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
    request: Request = None,
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
    if request.url.path.startswith("/api/v1"):
        return None


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


@router.get("/test_auth", dependencies=[Depends(check_api_key)])
async def test_auth():
    """Test auth endpoint"""
    return {"status": "ok"}


# TODO: Compatible with old API, will be modified in the future
@router.post(
    "/knowledge/add", response_model=Result[AssetDocumentResponse], dependencies=[Depends(check_api_key)]
)
async def create(
    request: AssetKnowledgeCreateRequest, service: Service = Depends(get_service)
) -> Result[AssetDocumentResponse]:
    """Create a new Prompt entity

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    return Result.succ(service.create(request))


@router.put(
    "/document/update",
    response_model=Result[AssetDocumentResponse],
    dependencies=[Depends(check_api_key)],
)
async def update_document(
    request: AssetDocumentRequest, service: Service = Depends(get_service)
) -> Result[AssetDocumentResponse]:
    """Update a Prompt entity

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    try:
        data = service.update_document(request)
        return Result.succ(data)
    except Exception as e:
        logger.exception("Update prompt failed!")
        return Result.failed(msg=str(e))

@router.post(
    "/tool/add",
    response_model=Result[AssetToolResponse],
    dependencies=[Depends(check_api_key)],
)
async def add_tool(
    request: AssetToolRequest, service: Service = Depends(get_service)
) -> Result[AssetToolResponse]:
    """Update a Prompt entity

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    try:
        data = service.add_tool(request)
        return Result.succ(data)
    except Exception as e:
        logger.exception("Update prompt failed!")
        return Result.failed(msg=str(e))


@router.put(
    "/tool/update",
    response_model=Result[int],
    dependencies=[Depends(check_api_key)],
)
async def update_tool(
    request: AssetToolRequest, service: Service = Depends(get_service)
) -> Result[int]:
    """Update a Prompt entity

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    try:
        data = service.update_tool(request)
        return Result.succ(data)
    except Exception as e:
        logger.exception("Update prompt failed!")
        return Result.failed(msg=str(e))

@router.post(
    "/tool/delete", response_model=Result[Dict[
        str, Any]], dependencies=[Depends(check_api_key)]
)
async def delete_tool(
    request: AssetToolRequest, service: Service = Depends(get_service)
) -> Result[Dict[str, Any]]:
    """Delete a Prompt entity

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    return Result.succ(service.delete_tool(request))


@router.post(
    "/agent/add",
    response_model=Result[AssetAgentResponse],
    dependencies=[Depends(check_api_key)],
)
async def add_agent(
    request: AssetAgentRequest, service: Service = Depends(get_service)
) -> Result[AssetAgentResponse]:
    """Update a Prompt entity

    Args:
        request (AssetAgentRequest): The request
        service (Service): The service
    Returns:
        AssetAgentResponse: The response
    """
    try:
        data = service.add_agent(request)
        return Result.succ(data)
    except Exception as e:
        logger.exception("add agent failed!")
        return Result.failed(msg=str(e))


@router.put(
    "/agent/update",
    response_model=Result[int],
    dependencies=[Depends(check_api_key)],
)
async def update_agent(
    request: AssetAgentRequest, service: Service = Depends(get_service)
) -> Result[int]:
    """Update a AssetAgentRequest entity

    Args:
        request (AssetAgentRequest): The request
        service (Service): The service
    Returns:
        int: The update count
    """
    try:
        data = service.update_agent(request)
        return Result.succ(data)
    except Exception as e:
        logger.exception("Update agent failed!")
        return Result.failed(msg=str(e))

@router.post(
    "/agent/delete", response_model=Result[Dict[
        str, Any]], dependencies=[Depends(check_api_key)]
)
async def delete_agent(
    request: AssetAgentRequest, service: Service = Depends(get_service)
) -> Result[Dict[str, Any]]:
    """Delete a Agent entity

    Args:
        request (AssetAgentRequest): The request
        service (Service): The service
    Returns:
        Dict[str, Any]: The delete count
    """
    return Result.succ(service.delete_agent(request))


@router.post(
    "/delete", response_model=Result[None], dependencies=[Depends(check_api_key)]
)
async def delete(
    request: AssetKnowledgeSearchRequest, service: Service = Depends(get_service)
) -> Result[None]:
    """Delete a Prompt entity

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    return Result.succ(service.delete(request))


@router.post(
    "/list",
    response_model=Result[List[AssetDocumentResponse]],
    dependencies=[Depends(check_api_key)],
)
async def query(
    request: AssetKnowledgeSearchRequest, service: Service = Depends(get_service)
) -> Result[List[AssetDocumentResponse]]:
    """Query Prompt entities

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        List[AssetDocumentResponse]: The response
    """
    return Result.succ(service.get_list(request))

@router.post(
    "/tool/search",
    response_model=Result[PaginationResult[AssetToolResponse]],
    dependencies=[Depends(check_api_key)],
)
async def tool_search(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetToolResponse]]:
    """Query Prompt entities

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetToolResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    return Result.succ(service.tool_search(request))

@router.post(
    "/agent/search",
    response_model=Result[PaginationResult[AssetAgentResponse]],
    dependencies=[Depends(check_api_key)],
)
async def agent_search(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetAgentResponse]]:
    """Asset Search

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetAgentResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    return Result.succ(service.agent_search(request))


@router.post(
    "/document/search",
    response_model=Result[PaginationResult[AssetDocumentResponse]],
    dependencies=[Depends(check_api_key)],
)
async def document_search(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetDocumentResponse]]:
    """Asset Search

    Args:
        request (AssetKnowledgeSearchRequest): The request
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    page_result: PaginationResult = service.document_search(request)
    documents = [
        document for document in page_result.items if document.document_content != ""
    ]
    page_result.items = documents
    # page_result.total_count = len(documents)
    return Result.succ(page_result)

@router.post(
    "/knowledge/search",
    response_model=Result[PaginationResult[AssetKnowledgeResponse]],
    dependencies=[Depends(check_api_key)],
)
async def knowledge_search(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetKnowledgeResponse]]:
    """Asset Search

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    return (Result.succ(service.knowledge_search(request)))

@router.post(
    "/knowledge/recommend",
    response_model=Result[PaginationResult[AssetDocumentResponse]],
    dependencies=[Depends(check_api_key)],
)
async def knowledge_recommend(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetDocumentResponse]]:
    """Asset Search

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    return Result.succ(service.knowledge_recommendation(request))


@router.post(
    "/tool/recommend",
    response_model=Result[PaginationResult[AssetToolResponse]],
    dependencies=[Depends(check_api_key)],
)
async def tool_recommend(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetToolResponse]]:
    """Asset Search

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    return (Result.succ(service.tool_recommendation(request)))

@router.post(
    "/agent/recommend",
    response_model=Result[PaginationResult[AssetAgentResponse]],
    dependencies=[Depends(check_api_key)],
)
async def tool_recommend(
    request: AssetKnowledgeSearchRequest,
    service: Service = Depends(get_service),
) -> Result[PaginationResult[AssetAgentResponse]]:
    """Asset Search

    Args:
        request (AssetKnowledgeSearchRequest): The request
        service (Service): The service
    Returns:
        AssetDocumentResponse: The response
    """
    request.offset = (request.page - 1) * request.limit
    return (Result.succ(service.agent_recommendation(request)))






def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
