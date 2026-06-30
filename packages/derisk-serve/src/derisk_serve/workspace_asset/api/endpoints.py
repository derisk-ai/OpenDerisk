"""WorkspaceAsset API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    AssetListFilter, AssetRequest, AssetResponse, AssetSearchRequest,
    AssetVersionResponse, TaskAssetLinkRequest, TaskAssetLinkResponse,
)
from ..config import ServeConfig
from ..service.service import ASSET_SERVICE_COMPONENT_NAME, AssetService

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> AssetService:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(ASSET_SERVICE_COMPONENT_NAME, AssetService)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: AssetService = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return token
    return None


@router.post("/assets/create", response_model=Result[AssetResponse],
             dependencies=[Depends(check_api_key)])
async def create_asset(
    request: AssetRequest, service: AssetService = Depends(get_service),
) -> Result[AssetResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("asset create exception!")
        return Result.failed(str(e))


@router.post("/assets/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_assets(
    f: AssetListFilter, service: AssetService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_assets(f))
    except Exception as e:
        logger.exception("asset list exception!")
        return Result.failed(str(e))


@router.get("/assets/info", response_model=Result[AssetResponse],
            dependencies=[Depends(check_api_key)])
async def get_asset(
    asset_id: int = Query(...),
    service: AssetService = Depends(get_service),
) -> Result[AssetResponse]:
    try:
        result = service.get_by_id(asset_id)
        if not result:
            return Result.failed(f"asset {asset_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("asset info exception!")
        return Result.failed(str(e))


@router.post("/assets/update", response_model=Result[AssetResponse],
             dependencies=[Depends(check_api_key)])
async def update_asset(
    request: AssetRequest, service: AssetService = Depends(get_service),
) -> Result[AssetResponse]:
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("asset update exception!")
        return Result.failed(str(e))


@router.post("/assets/search", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def search_assets(
    req: AssetSearchRequest, service: AssetService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.search(req))
    except Exception as e:
        logger.exception("asset search exception!")
        return Result.failed(str(e))


@router.get("/assets/{asset_id}/versions", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def list_versions(
    asset_id: int, service: AssetService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_versions(asset_id))
    except Exception as e:
        logger.exception("asset versions exception!")
        return Result.failed(str(e))


@router.post("/assets/link_task", response_model=Result[TaskAssetLinkResponse],
             dependencies=[Depends(check_api_key)])
async def link_to_task(
    request: TaskAssetLinkRequest, service: AssetService = Depends(get_service),
) -> Result[TaskAssetLinkResponse]:
    try:
        return Result.succ(service.link_to_task(request))
    except Exception as e:
        logger.exception("asset link_task exception!")
        return Result.failed(str(e))


@router.get("/assets/task_links", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def list_task_links(
    task_id: int = Query(...),
    service: AssetService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_links_by_task(task_id))
    except Exception as e:
        logger.exception("asset task_links exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(AssetService, config=config)
    global_system_app = system_app
