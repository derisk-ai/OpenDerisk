import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from derisk.model.cluster.apiserver.api import APISettings

router = APIRouter()
api_settings = APISettings()
get_bearer_token = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)


@router.post("/v2/derisk/reasoning_engine", dependencies=[])
async def derisk_plan():
    pass


@router.post("/v2/derisk/memory/write", dependencies=[])
async def derisk_memory_write():
    logger.info(f"derisk_memory_write:{1},{2}")


@router.post("/v2/derisk/memory/read", dependencies=[])
async def derisk_memory_read():
    logger.info(f"derisk_memory_write:{1},{2}")
