"""Artifact API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    ArtifactListFilter, ArtifactRequest, ArtifactResponse, ArtifactVersionResponse,
)
from ..config import ServeConfig
from ..service.service import ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService as Service

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> Service:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(ARTIFACT_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return token
    return None


@router.post("/artifacts/create", response_model=Result[ArtifactResponse],
             dependencies=[Depends(check_api_key)])
async def create_artifact(
    request: ArtifactRequest, service: Service = Depends(get_service),
) -> Result[ArtifactResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("artifact create exception!")
        return Result.failed(str(e))


@router.post("/artifacts/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_artifacts(
    f: ArtifactListFilter, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_artifacts(f))
    except Exception as e:
        logger.exception("artifact list exception!")
        return Result.failed(str(e))


@router.get("/artifacts/info", response_model=Result[ArtifactResponse],
            dependencies=[Depends(check_api_key)])
async def get_artifact(
    artifact_id: int = Query(...),
    service: Service = Depends(get_service),
) -> Result[ArtifactResponse]:
    try:
        result = service.get_by_id(artifact_id)
        if not result:
            return Result.failed(f"artifact {artifact_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("artifact info exception!")
        return Result.failed(str(e))


@router.post("/artifacts/update", response_model=Result[ArtifactResponse],
             dependencies=[Depends(check_api_key)])
async def update_artifact(
    request: ArtifactRequest, service: Service = Depends(get_service),
) -> Result[ArtifactResponse]:
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("artifact update exception!")
        return Result.failed(str(e))


@router.get("/artifacts/{artifact_id}/versions", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def list_versions(
    artifact_id: int, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_versions(artifact_id))
    except Exception as e:
        logger.exception("artifact versions exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
