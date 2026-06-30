"""Playbook API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    PlaybookListFilter, PlaybookRequest, PlaybookResponse,
    PlaybookValidateRequest, PlaybookVersionResponse,
)
from ..config import ServeConfig
from ..service.service import PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService as Service

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> Service:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(PLAYBOOK_SERVICE_COMPONENT_NAME, Service)


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


@router.post("/playbooks/create", response_model=Result[PlaybookResponse],
             dependencies=[Depends(check_api_key)])
async def create_playbook(
    request: PlaybookRequest, service: Service = Depends(get_service),
) -> Result[PlaybookResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("playbook create exception!")
        return Result.failed(str(e))


@router.post("/playbooks/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_playbooks(
    f: PlaybookListFilter, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_playbooks(f))
    except Exception as e:
        logger.exception("playbook list exception!")
        return Result.failed(str(e))


@router.get("/playbooks/info", response_model=Result[PlaybookResponse],
            dependencies=[Depends(check_api_key)])
async def get_playbook(
    playbook_id: int = Query(...),
    service: Service = Depends(get_service),
) -> Result[PlaybookResponse]:
    try:
        result = service.get_by_id(playbook_id)
        if not result:
            return Result.failed(f"playbook {playbook_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("playbook info exception!")
        return Result.failed(str(e))


@router.post("/playbooks/update", response_model=Result[PlaybookResponse],
             dependencies=[Depends(check_api_key)])
async def update_playbook(
    request: PlaybookRequest, service: Service = Depends(get_service),
) -> Result[PlaybookResponse]:
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("playbook update exception!")
        return Result.failed(str(e))


@router.post("/playbooks/{playbook_id}/delete", response_model=Result[bool],
             dependencies=[Depends(check_api_key)])
async def delete_playbook(
    playbook_id: int, service: Service = Depends(get_service),
) -> Result[bool]:
    try:
        return Result.succ(service.delete(playbook_id))
    except Exception as e:
        logger.exception("playbook delete exception!")
        return Result.failed(str(e))


@router.post("/playbooks/validate", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def validate_playbook(
    request: PlaybookValidateRequest,
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.validate_declaration(request.declaration))
    except Exception as e:
        logger.exception("playbook validate exception!")
        return Result.failed(str(e))


@router.get("/playbooks/{playbook_id}/versions", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def list_versions(
    playbook_id: int, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_versions(playbook_id))
    except Exception as e:
        logger.exception("playbook versions exception!")
        return Result.failed(str(e))


@router.post("/playbooks/seed_builtin", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def seed_builtin(
    workspace_id: int = Query(...),
    service: Service = Depends(get_service),
) -> Result:
    """Seed the two built-in Playbook examples (data ops weekly + SRE capacity)
    into the given workspace. Idempotent: skips ones that already exist by name.
    """
    try:
        from ..builtin_examples import BUILTIN_PLAYBOOKS
        existing = service.list_playbooks(PlaybookListFilter(
            workspace_id=workspace_id, limit=200,
        ))
        existing_names = {p.name for p in existing}
        results = []
        for tmpl in BUILTIN_PLAYBOOKS:
            if tmpl["name"] in existing_names:
                results.append({"name": tmpl["name"], "status": "exists"})
                continue
            req = PlaybookRequest(
                workspace_id=workspace_id,
                name=tmpl["name"],
                scenario_type=tmpl["scenario_type"],
                task_type=tmpl["task_type"],
                trigger=tmpl["trigger"],
                declaration=tmpl["declaration"],
                is_active=True,
            )
            created = service.create(req)
            results.append({"name": tmpl["name"], "id": created.id, "status": "created"})
        return Result.succ(results)
    except Exception as e:
        logger.exception("playbook seed_builtin exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
