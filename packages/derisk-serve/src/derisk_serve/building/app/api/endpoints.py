import logging
from functools import cache
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.util import PaginationResult
from derisk._private.config import Config
from derisk_serve.core import Result, blocking_func_to_async
from derisk_serve.utils.auth import UserRequest, get_user_from_headers
from .schema_app import GptsAppQuery

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import ServeRequest, ServerResponse, AppConfigPubilsh

router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None

logger = logging.getLogger(__name__)

CFG = Config()

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


@router.post("/create")
async def old_create(
        gpts_app: ServeRequest, user_info: UserRequest = Depends(get_user_from_headers),  service: Service = Depends(get_service),
):
    try:
        logger.info(f"old create:{gpts_app}")
        from derisk_serve.agent.db.gpts_app import GptsAppDao
        gpts_dao = GptsAppDao()
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        res = await blocking_func_to_async(CFG.SYSTEM_APP, gpts_dao.create, gpts_app)
        return Result.succ(res)
    except Exception as ex:
        logger.exception("old app create exception!")
        return Result.failed(err_code="E10011", msg=f"create old app error: {ex}")


@router.post("/building/create")
async def create(
        gpts_app: ServeRequest, user_info: UserRequest = Depends(get_user_from_headers),  service: Service = Depends(get_service),
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        return Result.succ( service.create(gpts_app))
    except Exception as ex:
        logger.exception("Create app error!")
        return Result.failed(err_code="E11001", msg=f"create app error: {ex}")

@router.post("/building/edit")
async def building_edit(
        gpts_app: ServeRequest, user_info: UserRequest = Depends(get_user_from_headers),  service: Service = Depends(get_service),
):
    try:
        logger.info(f"building_edit:{gpts_app}")

        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        resp = await service.edit(gpts_app)
        ## 编辑配置信息
        return Result.succ(resp)
    except Exception as ex:
        logger.exception(" app edit exception!")
        return Result.failed(err_code="E11002", msg=f"edit app error: {ex}")

@router.post("/edit")
async def old_edit(
        gpts_app: ServeRequest, user_info: UserRequest = Depends(get_user_from_headers),  service: Service = Depends(get_service),
):
    logger.info(f"old edit:{gpts_app}")
    try:
        from derisk_serve.agent.db.gpts_app import GptsAppDao
        gpts_dao = GptsAppDao()
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        return Result.succ(gpts_dao.edit(gpts_app))
    except Exception as ex:
        logger.exception(" app edit exception!")
        return Result.failed(err_code="E10002", msg=f"edit old app error: {ex}")




@router.post("/publish", response_model=Result[ServerResponse], dependencies=[Depends(check_api_key)])
async def update(
        request: AppConfigPubilsh, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Update a App entity

    Args:
        request (ServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    try:
        return Result.succ(await service.publish(app_code=request.app_code, new_config_code=request.config_code, operator=request.operator, description=request.description))
    except Exception as e:
        return Result.failed(err_code="E11003",msg=f"应用配置[{request.app_code}][{request.config_code}]发布异常!{str(e)}", )



@router.post(
    "/query",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def query(
        request: ServeRequest, service: Service = Depends(get_service)
) -> Result[ServerResponse]:
    """Query App entities

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
    """Query App entities

    Args:
        request (ServeRequest): The request
        page (int): The page number
        page_size (int): The page size
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.get_list_by_page(request, page, page_size))






@router.post("/list")
async def app_list(
        query: GptsAppQuery,
        page: Optional[int] = Query(default=None, description="current page"),
        page_size: Optional[int] = Query(default=None, description="page size"),
        user_info: UserRequest = Depends(get_user_from_headers),
        service: Service = Depends(get_service),
):
    try:

        query.user_code = (
            user_info.user_id if user_info.user_id is not None else query.user_code
        )
        query.ignore_user = "true"
        query.app_name = query.name_filter
        if page:
            query.page = page
        if page_size:
            query.page_size = page_size
        res = await service.app_list(query, True)
        return Result.succ(res)
    except Exception as ex:
        logger.exception("app_list exception!")
        return Result.failed(err_code="E000X", msg=f"query app list error: {ex}")


@router.get("/info")
async def app_detail(
        app_code: str,
        building_mode: bool = True,
        config_code: Optional[str] = None,
        service: Service = Depends(get_service),
):
    logger.info(f"app_detail:{app_code},{config_code},")
    try:

        res = await service.app_detail(app_code, config_code, building_mode=building_mode)

        return Result.succ(res)

    except Exception as ex:
        logger.exception("query app detail error!")
        return Result.failed( msg=f"query app detail error: {ex}")

@router.post("/add_hub_code")
async def add_hub_code(
        app_code: str, app_hub_code: str, user_info: UserRequest = Depends(get_user_from_headers),
        service: Service = Depends(get_service),
):
    try:
        return Result.succ(service.add_hub_code(app_code, app_hub_code))
    except Exception as ex:
        logger.exception("add app hub code exception!")
        return Result.failed(err_code="E10005", msg=f"add app hub code error: {ex}")


@router.post("/hot/list")
async def hot_app_list(
        query: GptsAppQuery, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        query.user_code = (
            user_info.user_id if user_info.user_id is not None else query.user_code
        )
        app_service = get_service()

        list_hot_apps = await app_service.list_hot_apps(query)
        return Result.succ(list_hot_apps)
    except Exception as ex:
        logger.exception("hot_app_list exception！")
        return Result.failed( msg=f"query hot app error: {ex}")


@router.post("/detail")
async def app_list(
        gpts_app: ServeRequest, user_info: UserRequest = Depends(get_user_from_headers),  service: Service = Depends(get_service),
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        return Result.succ(await service.app_detail(gpts_app.app_code))
    except Exception as ex:
        return Result.failed(err_code="E110005", msg=f"query app error: {ex}")



@router.post("/remove", response_model=Result)
async def delete(
        gpts_app: ServeRequest, user_info: UserRequest = Depends(get_user_from_headers),  service: Service = Depends(get_service),
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        return Result.succ(service.delete(gpts_app))
    except Exception as ex:
        logger.exception("app remove exception!")
        return Result.failed(err_code="E110006", msg=f"delete app error: {ex}")





def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
