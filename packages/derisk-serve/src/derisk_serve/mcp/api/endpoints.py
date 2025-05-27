import logging
from functools import cache
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.util import PaginationResult
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import ServeRequest, ServerResponse, McpRunRequest, McpTool, QueryFilter

router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


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


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


@router.get("/test_auth", dependencies=[Depends(check_api_key)])
async def test_auth():
    """Test auth endpoint"""
    return {"status": "ok"}


@router.post(
    "/", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
)
async def create(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Create a new Mcp entity

    Args:
        request (ServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    logger.info(f"mcp add:{request}")
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("mcp add exception!")
        return Result.failed(str(e))


@router.put(
    "/", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
)
async def update(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Update a Mcp entity

    Args:
        request (ServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.update(request))


@router.delete(
    "/", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
)
async def update(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Update a Mcp entity

    Args:
        request (ServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.delete(request))



@router.post(
    "/start", response_model=Result[bool], dependencies=[Depends(check_api_key)]
)
async def start(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[bool]:
    try:
        return Result.succ(True)
    except Exception as e:
        return Result.failed(str(e))


@router.post(
    "/offline", response_model=Result[bool], dependencies=[Depends(check_api_key)]
)
async def offline(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[bool]:
    try:
        return Result.succ(True)
    except Exception as e:
        return Result.failed(str(e))


@router.post(
    "/connect", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
)
async def connect(
        request: McpRunRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    try:
        return Result.succ(None)
    except Exception as e:
        return Result.failed(str(e))


@router.post(
    "/tool/list", response_model=Result[List[McpTool]], dependencies=[Depends(check_api_key)]
)
async def tool_list(
        request: McpRunRequest, service: Service = Depends(get_service)
) -> Result[List[McpTool]]:
    try:
        return Result.succ(
            await service.list_tools(request.name, request.sse_url, request.sse_headers))
    except Exception as e:
        logger.exception("mcp list tool exception!")
        return Result.failed(str(e))


@router.post(
    "/tool/run", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
)
async def run(
        request: McpRunRequest, service: Service = Depends(get_service)
) -> Result[Any]:
    try:
        return Result.succ(
            await service.call_tool(request.name, request.method, request.sse_url, request.params, request.sse_headers))
    except Exception as e:
        logger.exception("mcp tool run exception!")
        return Result.failed(str(e))


@router.post(
    "/query_fuzzy",
    response_model=Result[PaginationResult[ServerResponse]],
    dependencies=[Depends(check_api_key)],
)
async def fuzzy_query(
        query_filter: QueryFilter,
        page: Optional[int] = Query(default=1, description="current page"),
        page_size: Optional[int] = Query(default=20, description="page size"),
        service: Service = Depends(get_service),
) -> Result[PaginationResult[ServerResponse]]:
    try:

        return Result.succ(service.filter_list_page(query_filter, page, page_size))
    except Exception as e:
        logger.exception("fuzzy query exception!")
        return Result.failed(str(e))


@router.post(
    "/query",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def query(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Query Mcp entities

    Args:
        request (ServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.get(request))


@router.post(
    "/query_page",
    response_model=Result[PaginationResult[ServerResponse]],
    dependencies=[Depends(check_api_key)],
)
async def query_page(
        request: ServeRequest,
        page: Optional[int] = Query(default=1, description="current page"),
        page_size: Optional[int] = Query(default=20, description="page size"),
        service: Service = Depends(get_service),
) -> Result[PaginationResult[ServerResponse]]:
    """Query Mcp entities

    Args:
        request (ServeRequest): The request
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.get_list_by_page(request, page, page_size))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
