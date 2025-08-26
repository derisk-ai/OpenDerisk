import logging
from functools import cache
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.agent.core.schema import DynamicParam
from derisk.component import SystemApp
from derisk.util import PaginationResult
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import ServeRequest, ServerResponse, ChatInParamDefine, ChatInParam

router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None

logger = logging.getLogger(__name__)

get_bearer_token = HTTPBearer(auto_error=False)

def get_service() -> Service:
    """Get the service instance"""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


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


# @router.post(
#     "/edit", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)]
# )
# async def edit(
#     request: ServeRequest, service: Service = Depends(get_service)
# ) -> Result[ServerResponse]:
#     """Create a new Building/config entity
#
#     Args:
#         request (ServeRequest): The request
#         service (Service): The service
#     Returns:
#         ServerResponse: The response
#     """
#     return Result.succ(service.edit(request))



@router.get(
    "/list",
    response_model=Result[PaginationResult[ServerResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_app_configs(
    app_code:str,
    page: Optional[int] = Query(default=1, description="current page"),
    page_size: Optional[int] = Query(default=20, description="page size"),
    service: Service = Depends(get_service),
) -> Result[PaginationResult[ServerResponse]]:
    """Query Building/config entities

    Args:
        app_code (str): The app code
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.get_app_config(app_code, page, page_size))

@router.post(
    "/query",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def query(
    request: ServeRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Query Building/config entities

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
    """Query Building/config entities

    Args:
        request (ServeRequest): The request
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.get_list_by_page(request, page, page_size))



@router.get("/agent/variables", dependencies=[Depends(check_api_key)])
async def get_variables(agent_role: str, service: Service = Depends(get_service)) -> Result[List]:
    """get agent variables"""
    try:
        resp = await service.get_agent_variables(agent_role)
        return Result.succ(resp)
    except Exception as e:
        logger.exception(f"agent variables exception!{str(e)}")
        return Result.failed(str(e))


@router.post("/agent/variables/render", dependencies=[Depends(check_api_key)])
async def variables_render(params: List[DynamicParam], agent_role: str = Query(description="render param agent role"),
                           service: Service = Depends(get_service)) -> Result[Dict]:
    """chat agent variables render"""
    try:
        return Result.succ(await service.variables_render(agent_role, params))
    except Exception as e:
        logger.exception(f"agent variables render exception!{str(e)}")
        return Result.failed(str(e))


@router.get("/chat/out/modes", dependencies=[Depends(check_api_key)])
async def chat_out_modes(service: Service = Depends(get_service)) -> Result[List]:
    """chat out modes"""
    try:
        return Result.succ(service.get_vis_modes())
    except Exception as e:
        logger.info(f"vis modes exception!{str(e)}")
        return Result.failed(str(e))


@router.get("/chat/in/params/all", dependencies=[Depends(check_api_key)])
async def chat_in_params(service: Service = Depends(get_service)) -> Result[List[ChatInParamDefine]]:
    """chat in params"""
    try:
        return Result.succ(service.get_all_chat_in_params())
    except Exception as e:
        logger.info(f"all chat in params exception!{str(e)}")
        return Result.failed(str(e))


@router.post("/chat/in/params/render", dependencies=[Depends(check_api_key)])
async def render_chat_in_params(chat_in_params: List[ChatInParam], service: Service = Depends(get_service)) -> Result[List[ChatInParam]]:
    """chat in params render"""
    try:
        return Result.succ(await service.render_chat_in_params(chat_in_params))
    except Exception as e:
        logger.exception(f"render chat in params exception!{str(e)}")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
