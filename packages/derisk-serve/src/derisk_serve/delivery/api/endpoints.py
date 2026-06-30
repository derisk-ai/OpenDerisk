"""Delivery API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import DeliveryListFilter, DeliveryRequest, DeliveryResponse
from ..config import ServeConfig
from ..service.service import DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> DeliveryService:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: DeliveryService = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return token
    return None


@router.post("/deliveries/create", response_model=Result[DeliveryResponse],
             dependencies=[Depends(check_api_key)])
async def create_delivery(
    request: DeliveryRequest, service: DeliveryService = Depends(get_service),
) -> Result[DeliveryResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("delivery create exception!")
        return Result.failed(str(e))


@router.post("/deliveries/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_deliveries(
    f: DeliveryListFilter, service: DeliveryService = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_deliveries(f))
    except Exception as e:
        logger.exception("delivery list exception!")
        return Result.failed(str(e))


@router.get("/deliveries/info", response_model=Result[DeliveryResponse],
            dependencies=[Depends(check_api_key)])
async def get_delivery(
    delivery_id: int = Query(...),
    service: DeliveryService = Depends(get_service),
) -> Result[DeliveryResponse]:
    try:
        result = service.get_by_id(delivery_id)
        if not result:
            return Result.failed(f"delivery {delivery_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("delivery info exception!")
        return Result.failed(str(e))


@router.post("/deliveries/{delivery_id}/send", response_model=Result[DeliveryResponse],
             dependencies=[Depends(check_api_key)])
async def send_delivery(
    delivery_id: int, service: DeliveryService = Depends(get_service),
) -> Result[DeliveryResponse]:
    try:
        return Result.succ(service.send(delivery_id))
    except Exception as e:
        logger.exception("delivery send exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(DeliveryService, config=config)
    global_system_app = system_app
