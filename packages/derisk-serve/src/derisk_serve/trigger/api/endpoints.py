"""Trigger API endpoints."""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    TriggerFireRequest, TriggerListFilter, TriggerSourceRequest,
    TriggerSourceResponse,
)
from ..config import ServeConfig
from ..service.service import TRIGGER_SERVICE_COMPONENT_NAME, TriggerService

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> TriggerService:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(TRIGGER_SERVICE_COMPONENT_NAME, TriggerService)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: TriggerService = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return token
    return None


@router.post("/triggers/create", response_model=Result[TriggerSourceResponse],
             dependencies=[Depends(check_api_key)])
async def create_trigger(
    request: TriggerSourceRequest, service: TriggerService = Depends(get_service),
) -> Result[TriggerSourceResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("trigger create exception!")
        return Result.failed(str(e))


@router.post("/triggers/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_triggers(
    f: TriggerListFilter, service: TriggerService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_triggers(f))
    except Exception as e:
        logger.exception("trigger list exception!")
        return Result.failed(str(e))


@router.get("/triggers/info", response_model=Result[TriggerSourceResponse],
            dependencies=[Depends(check_api_key)])
async def get_trigger(
    trigger_id: int = Query(...),
    service: TriggerService = Depends(get_service),
) -> Result[TriggerSourceResponse]:
    try:
        result = service.get_by_id(trigger_id)
        if not result:
            return Result.failed(f"trigger {trigger_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("trigger info exception!")
        return Result.failed(str(e))


@router.post("/triggers/update", response_model=Result[TriggerSourceResponse],
             dependencies=[Depends(check_api_key)])
async def update_trigger(
    request: TriggerSourceRequest, service: TriggerService = Depends(get_service),
) -> Result[TriggerSourceResponse]:
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("trigger update exception!")
        return Result.failed(str(e))


@router.post("/triggers/{trigger_id}/delete", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def delete_trigger(
    trigger_id: int, service: TriggerService = Depends(get_service),
) -> Result:
    try:
        ok = service.delete(trigger_id)
        return Result.succ({"deleted": ok})
    except Exception as e:
        logger.exception("trigger delete exception!")
        return Result.failed(str(e))


@router.post("/triggers/fire", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def fire_trigger(
    request: TriggerFireRequest, service: TriggerService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.fire(request))
    except Exception as e:
        logger.exception("trigger fire exception!")
        return Result.failed(str(e))


@router.post("/triggers/{trigger_id}/webhook", response_model=Result)
async def receive_webhook(
    trigger_id: int,
    payload: Optional[Dict[str, Any]] = None,
    service: TriggerService = Depends(get_service),
) -> Result:
    """Public webhook endpoint for external systems.

    Security: the trigger id acts as an opaque capability URL. The caller
    must also know the workspace_id, which is verified by the service.
    """
    try:
        entity = service.get_by_id(trigger_id)
        if not entity:
            raise HTTPException(status_code=404, detail="trigger not found")
        result = service.fire(TriggerFireRequest(
            workspace_id=entity.workspace_id,
            trigger_id=trigger_id,
            payload=payload or {},
        ))
        return Result.succ(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("webhook receive exception!")
        return Result.failed(str(e))


@router.post("/triggers/{trigger_id}/alert", response_model=Result)
async def receive_alert(
    trigger_id: int,
    payload: Optional[Dict[str, Any]] = None,
    service: TriggerService = Depends(get_service),
) -> Result:
    """Public alert endpoint for monitoring systems."""
    try:
        entity = service.get_by_id(trigger_id)
        if not entity:
            raise HTTPException(status_code=404, detail="trigger not found")
        result = service.fire(TriggerFireRequest(
            workspace_id=entity.workspace_id,
            trigger_id=trigger_id,
            payload=payload or {},
        ))
        return Result.succ(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("alert receive exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(TriggerService, config=config)
    global_system_app = system_app
