import json
import logging
from functools import cache
from typing import List, Optional, Any
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.util import PaginationResult
from derisk_serve.core import Result
from derisk_ext.mcp.client import GatewayClient

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
    "/update", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
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
    "/delete", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
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
async def start(request: ServeRequest, service: Service = Depends(get_service)) -> Result[bool]:
    """Start MCP service with full lifecycle management"""
    try:
        # 1. Check if service already exists and is online
        mcp = service.get(request)
        if mcp and mcp.available:
            return Result.succ(True, message=f"MCP '{request.name}' is already online")

        # 2. Initialize GatewayClient with the correct MCP Gateway URL
        # Replace "ws://gateway-host:port/register" with the actual Gateway URL
        gateway_url = "ws://gateway-host:port/register"  # TODO: Replace with actual Gateway URL
        client = GatewayClient(
            gateway_url=gateway_url,  # Use Gateway URL, not request.sse_url
            server_name=request.name,
            headers=request.sse_headers
        )

        # 3. Connect and register with gateway
        try:
            # 3.1 Establish WebSocket connection
            if not await client.connect_and_listen():
                return Result.failed(f"Failed to connect to gateway: {gateway_url}")

            # 3.2 Send registration (retry 3 times)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    registration_result = await client.send({
                        "jsonrpc": "2.0",
                        "method": "register",
                        "params": {
                            "name": request.name,
                            "version": "1.0.0",
                            "capabilities": {}
                        }
                    })
                    if registration_result and registration_result.get("status") == "registered":
                        break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(1)
            else:
                return Result.failed("Registration attempts exhausted")

            # 3.3 Initialize service
            init_result = await client.send({
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "0.1.0",
                    "clientInfo": {"name": "MCPGateway", "version": "1.0.0"}
                }
            })
            if not init_result:
                return Result.failed("Initialization failed")

            # 3.4 Load tools
            tools_result = await client.send({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {}
            })
            if not tools_result or "tools" not in tools_result:
                return Result.failed("Failed to load tools")

        except Exception as e:
            logger.error(f"Gateway communication failed: {str(e)}")
            try:
                await client.close()
            except:
                pass
            return Result.failed(f"Startup aborted: {str(e)}")

        # 4. Update database (atomic operation)
        try:
            update_data = ServeRequest(
                id=request.id,
                name=request.name,
                available=True,
            )
            if mcp:
                service.update(update_data)
            else:
                service.create(update_data)
        except Exception as e:
            logger.error(f"Database update failed: {str(e)}")
            await client.close()
            return Result.failed(f"Service started but status update failed: {str(e)}")

        return Result.succ(True, message=f"MCP '{request.name}' started successfully")

    except Exception as e:
        logger.exception(f"Critical startup failure: {e}")
        return Result.failed(f"Startup failed: {str(e)}")

@router.post(
    "/offline", response_model=Result[bool], dependencies=[Depends(check_api_key)]
)
async def offline(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[bool]:
    """标记 MCP 服务为离线状态，并关闭相关连接"""
    try:
        # 1. 获取 MCP 实例
        mcp = service.get(request)
        if not mcp:
            return Result.failed(f"MCP '{request.name}' not found")

        # 2. 若已离线则直接返回
        if not mcp.available:
            return Result.succ(True, message=f"MCP '{request.name}' is already offline")

        # 3. Close WebSocket connection (if exists)
        ws_failed = False
        if mcp.sse_url:
            try:
                gateway_url = "ws://gateway-host:port/register"  # TODO: 替换为实际的网关 URL
                client = GatewayClient(
                    gateway_url=gateway_url,
                    server_name=mcp.name,
                    headers=mcp.sse_headers
                )

                # 发送 unregister 请求
                await client.send({
                    "jsonrpc": "2.0",
                    "method": "unregister",
                    "params": {"name": mcp.name}
                })
                await client.close()
            except Exception as e:
                logger.error(f"WebSocket close failed for {request.name}: {str(e)}")
                ws_failed = True

        # 4. Update database (must succeed even if WS failed)
        try:
            update_request = ServeRequest(id=request.id, name=request.name, available=False)
            service.update(update_request)
        except Exception as e:
            logger.error(f"Database update failed for {request.name}: {str(e)}")
            if ws_failed:
                return Result.failed(f"Both WebSocket close and DB update failed: {str(e)}")
            return Result.failed(f"Database update failed: {str(e)}")

        # 5. Return appropriate result
        if ws_failed:
            return Result.succ(True,
                               message=f"MCP '{request.name}' marked offline but WebSocket close failed")
        return Result.succ(True, message=f"MCP '{request.name}' offline success")

    except Exception as e:
        logger.exception(f"Critical offline failure for {request.name}: {e}")
        return Result.failed(f"Offline operation failed: {str(e)}")


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
