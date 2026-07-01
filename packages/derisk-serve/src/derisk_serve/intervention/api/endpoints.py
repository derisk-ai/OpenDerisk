"""Intervention API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    InterventionListFilter, InterventionRequest, InterventionResolveRequest,
    InterventionResponse,
)
from ..config import ServeConfig
from ..service.service import INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> InterventionService:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: InterventionService = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return token
    return None


@router.post("/interventions/create", response_model=Result[InterventionResponse],
             dependencies=[Depends(check_api_key)])
async def create_intervention(
    request: InterventionRequest, service: InterventionService = Depends(get_service),
) -> Result[InterventionResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("intervention create exception!")
        return Result.failed(str(e))


@router.post("/interventions/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_interventions(
    f: InterventionListFilter, service: InterventionService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_interventions(f))
    except Exception as e:
        logger.exception("intervention list exception!")
        return Result.failed(str(e))


@router.get("/interventions/info", response_model=Result[InterventionResponse],
            dependencies=[Depends(check_api_key)])
async def get_intervention(
    intervention_id: int = Query(...),
    service: InterventionService = Depends(get_service),
) -> Result[InterventionResponse]:
    try:
        result = service.get_by_id(intervention_id)
        if not result:
            return Result.failed(f"intervention {intervention_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("intervention info exception!")
        return Result.failed(str(e))


@router.post("/interventions/{intervention_id}/resolve",
             response_model=Result[InterventionResponse],
             dependencies=[Depends(check_api_key)])
async def resolve_intervention(
    intervention_id: int, request: InterventionResolveRequest,
    service: InterventionService = Depends(get_service),
) -> Result[InterventionResponse]:
    try:
        return Result.succ(service.resolve(intervention_id, request))
    except Exception as e:
        logger.exception("intervention resolve exception!")
        return Result.failed(str(e))


@router.post("/interventions/{intervention_id}/abort",
             response_model=Result[InterventionResponse],
             dependencies=[Depends(check_api_key)])
async def abort_intervention(
    intervention_id: int, service: InterventionService = Depends(get_service),
) -> Result[InterventionResponse]:
    try:
        return Result.succ(service.abort(intervention_id))
    except Exception as e:
        logger.exception("intervention abort exception!")
        return Result.failed(str(e))


@router.post("/interventions/{intervention_id}/resolve-and-execute",
             response_model=Result[InterventionResponse],
             dependencies=[Depends(check_api_key)])
async def resolve_and_execute(
    intervention_id: int, request: InterventionResolveRequest,
    service: InterventionService = Depends(get_service),
) -> Result[InterventionResponse]:
    try:
        entity = await service.execute_resolved(
            intervention_id=intervention_id,
            decision=request.decision,
            distillation=request.distillation,
            resolved_by_user_id=request.resolved_by_user_id,
        )
        return Result.succ(service.dao.to_response(entity))
    except Exception as e:
        logger.exception("intervention resolve-and-execute exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(InterventionService, config=config)
    global_system_app = system_app
