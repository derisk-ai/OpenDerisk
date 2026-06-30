"""Workspace API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    RenameConversationRequest,
    SetCurrentConversationRequest,
    WorkspaceListFilter,
    WorkspaceMemberListRequest,
    WorkspaceMemberRequest,
    WorkspaceMemberResponse,
    WorkspaceRequest,
    WorkspaceResourceListRequest,
    WorkspaceResourceRequest,
    WorkspaceResourceResponse,
    WorkspaceResponse,
)
from ..config import ServeConfig
from ..service.service import WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService as Service

router = APIRouter()

global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> Service:
    if global_system_app is None:
        raise HTTPException(
            status_code=500,
            detail={"error": {"message": "System app not initialized", "type": "internal_error"}},
        )
    return global_system_app.get_component(WORKSPACE_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={"error": {"message": "", "type": "invalid_request_error",
                                   "param": None, "code": "invalid_api_key"}},
            )
        return token
    return None


# ----------------------- Workspace -----------------------
@router.post("/workspaces/create", response_model=Result[WorkspaceResponse],
             dependencies=[Depends(check_api_key)])
async def create_workspace(
    request: WorkspaceRequest, service: Service = Depends(get_service),
) -> Result[WorkspaceResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("workspace create exception!")
        return Result.failed(str(e))


@router.post("/workspaces/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_workspaces(
    filter_request: WorkspaceListFilter,
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_workspaces(
            user_id=filter_request.user_id,
            scenario_type=filter_request.scenario_type,
            include_archived=filter_request.include_archived,
        ))
    except Exception as e:
        logger.exception("workspace list exception!")
        return Result.failed(str(e))


@router.get("/workspaces/info", response_model=Result[WorkspaceResponse],
            dependencies=[Depends(check_api_key)])
async def get_workspace(
    workspace_code: str = Query(..., description="workspace code"),
    service: Service = Depends(get_service),
) -> Result[WorkspaceResponse]:
    try:
        result = service.get_by_code(workspace_code)
        if not result:
            return Result.failed(f"workspace '{workspace_code}' not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("workspace info exception!")
        return Result.failed(str(e))


@router.post("/workspaces/update", response_model=Result[WorkspaceResponse],
             dependencies=[Depends(check_api_key)])
async def update_workspace(
    request: WorkspaceRequest, service: Service = Depends(get_service),
) -> Result[WorkspaceResponse]:
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("workspace update exception!")
        return Result.failed(str(e))


@router.post("/workspaces/archive", response_model=Result[WorkspaceResponse],
             dependencies=[Depends(check_api_key)])
async def archive_workspace(
    request: dict, service: Service = Depends(get_service),
) -> Result[WorkspaceResponse]:
    try:
        workspace_code = request.get("workspace_code")
        if not workspace_code:
            return Result.failed("workspace_code is required")
        return Result.succ(service.archive(workspace_code))
    except Exception as e:
        logger.exception("workspace archive exception!")
        return Result.failed(str(e))


# ----------------------- Members -----------------------
@router.post("/members/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_members(
    request: WorkspaceMemberListRequest,
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_members(request.workspace_id))
    except Exception as e:
        logger.exception("member list exception!")
        return Result.failed(str(e))


@router.post("/members/add", response_model=Result[WorkspaceMemberResponse],
             dependencies=[Depends(check_api_key)])
async def add_member(
    request: WorkspaceMemberRequest, service: Service = Depends(get_service),
) -> Result[WorkspaceMemberResponse]:
    try:
        return Result.succ(service.add_member(request))
    except Exception as e:
        logger.exception("member add exception!")
        return Result.failed(str(e))


@router.post("/members/remove", response_model=Result[bool],
             dependencies=[Depends(check_api_key)])
async def remove_member(
    request: dict, service: Service = Depends(get_service),
) -> Result[bool]:
    try:
        workspace_id = request.get("workspace_id")
        user_id = request.get("user_id")
        return Result.succ(service.remove_member(workspace_id, user_id))
    except Exception as e:
        logger.exception("member remove exception!")
        return Result.failed(str(e))


@router.post("/members/update_role", response_model=Result[WorkspaceMemberResponse],
             dependencies=[Depends(check_api_key)])
async def update_member_role(
    request: dict, service: Service = Depends(get_service),
) -> Result[WorkspaceMemberResponse]:
    try:
        return Result.succ(service.update_member_role(
            workspace_id=request.get("workspace_id"),
            user_id=request.get("user_id"),
            role=request.get("role"),
        ))
    except Exception as e:
        logger.exception("member update role exception!")
        return Result.failed(str(e))


# ----------------------- Resources -----------------------
@router.post("/resources/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_resources(
    request: WorkspaceResourceListRequest,
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_resources(request.workspace_id, request.type))
    except Exception as e:
        logger.exception("resource list exception!")
        return Result.failed(str(e))


@router.post("/resources/add", response_model=Result[WorkspaceResourceResponse],
             dependencies=[Depends(check_api_key)])
async def add_resource(
    request: WorkspaceResourceRequest, service: Service = Depends(get_service),
) -> Result[WorkspaceResourceResponse]:
    try:
        return Result.succ(service.add_resource(request))
    except Exception as e:
        logger.exception("resource add exception!")
        return Result.failed(str(e))


@router.post("/resources/remove", response_model=Result[bool],
             dependencies=[Depends(check_api_key)])
async def remove_resource(
    request: dict, service: Service = Depends(get_service),
) -> Result[bool]:
    try:
        resource_id = request.get("resource_id")
        return Result.succ(service.remove_resource(resource_id))
    except Exception as e:
        logger.exception("resource remove exception!")
        return Result.failed(str(e))


@router.post("/resources/update", response_model=Result[WorkspaceResourceResponse],
             dependencies=[Depends(check_api_key)])
async def update_resource(
    request: dict, service: Service = Depends(get_service),
) -> Result[WorkspaceResourceResponse]:
    try:
        resource_id = request.get("resource_id")
        rr = WorkspaceResourceRequest(**request.get("resource", {}))
        return Result.succ(service.update_resource(resource_id, rr))
    except Exception as e:
        logger.exception("resource update exception!")
        return Result.failed(str(e))


# ----------------------- Growth -----------------------
@router.get("/workspaces/{workspace_id}/growth", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def get_workspace_growth(
    workspace_id: int,
    service: Service = Depends(get_service),
) -> Result:
    """获取空间本月成长数据。"""
    try:
        return Result.succ(service.get_growth(workspace_id))
    except Exception as e:
        logger.exception("workspace growth exception!")
        return Result.failed(str(e))


# ----------------------- Conversation Link -----------------------
@router.post("/conversations/link", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def link_conversation(
    request: dict, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.link_conversation(
            workspace_id=request.get("workspace_id"),
            conv_uid=request.get("conv_uid"),
            task_id=request.get("task_id"),
            user_id=request.get("user_id"),
        ))
    except Exception as e:
        logger.exception("conversation link exception!")
        return Result.failed(str(e))


@router.post("/conversations/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_conversations(
    request: dict, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_conversations(
            workspace_id=request.get("workspace_id"),
            user_id=request.get("user_id"),
            limit=request.get("limit", 100),
        ))
    except Exception as e:
        logger.exception("conversation list exception!")
        return Result.failed(str(e))


@router.get("/conversations/lookup", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def lookup_conversation(
    conv_uid: str = Query(..., description="conversation uid"),
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.get_conversation_workspace(conv_uid))
    except Exception as e:
        logger.exception("conversation lookup exception!")
        return Result.failed(str(e))


@router.get("/workspaces/{workspace_id}/conversations/current", response_model=Result,
            dependencies=[Depends(check_api_key)])
async def get_current_conversation(
    workspace_id: int,
    user_id: Optional[int] = Header(None, alias="X-User-ID"),
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.get_current_conversation(
            workspace_id=workspace_id, user_id=user_id
        ))
    except Exception as e:
        logger.exception("get current conversation exception!")
        return Result.failed(str(e))


@router.post("/workspaces/{workspace_id}/conversations/set-current", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def set_current_conversation(
    workspace_id: int,
    request: SetCurrentConversationRequest,
    user_id: Optional[int] = Header(None, alias="X-User-ID"),
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.set_current_conversation(
            workspace_id=workspace_id, user_id=user_id, conv_uid=request.conv_uid
        ))
    except Exception as e:
        logger.exception("set current conversation exception!")
        return Result.failed(str(e))


@router.patch("/conversations/{conv_uid}/rename", response_model=Result,
              dependencies=[Depends(check_api_key)])
async def rename_conversation(
    conv_uid: str,
    request: RenameConversationRequest,
    service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.rename_conversation(
            conv_uid=conv_uid, title=request.title
        ))
    except Exception as e:
        logger.exception("rename conversation exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
