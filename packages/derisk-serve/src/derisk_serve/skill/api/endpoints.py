import logging
import os
import zipfile
import uuid
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk.util import PaginationResult
from derisk_serve.core import Result
from .schemas import (
    SkillRequest,
    SkillResponse,
    SkillQueryFilter,
    SkillFileListResponse,
    SkillFileReadRequest,
    SkillFileReadResponse,
    SkillFileWriteRequest,
    SkillFileWriteResponse,
    SkillFileRenameRequest,
    SkillFileRenameResponse,
    SkillFileBatchUploadRequest,
    SkillFileBatchUploadResponse,
    SkillSyncTaskRequest,
    SkillSyncTaskResponse,
)
from ..config import ServeConfig
from ..service.service import Service, SKILL_SERVICE_COMPONENT_NAME

router = APIRouter()

global_system_app: Optional[SystemApp] = None

logger = logging.getLogger(__name__)


def get_service() -> Service:
    """Get the service instance"""
    if global_system_app is None:
        raise HTTPException(
            status_code=500,
            detail={"error": {"message": "System app not initialized", "type": "internal_error"}},
        )
    return global_system_app.get_component(SKILL_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key"""
    if service.config.api_keys:
        api_keys = [key.strip() for key in service.config.api_keys.split(",")]
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


@router.post(
    "/create", response_model=Result[SkillResponse], dependencies=[Depends(check_api_key)]
)
async def create(
    request: SkillRequest, service: Service = Depends(get_service)
) -> Result[SkillResponse]:
    """Create a new Skill entity"""
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("skill create exception!")
        return Result.failed(str(e))


@router.post(
    "/update", response_model=Result[SkillResponse], dependencies=[Depends(check_api_key)]
)
async def update(
    request: SkillRequest, service: Service = Depends(get_service)
) -> Result[SkillResponse]:
    """Update a Skill entity"""
    if request.skill_code is None:
        return Result.failed("skill_code is null")
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("skill update exception!")
        return Result.failed(str(e))


@router.post(
    "/delete", response_model=Result[bool], dependencies=[Depends(check_api_key)]
)
async def delete(
    request: SkillRequest, service: Service = Depends(get_service)
) -> Result[bool]:
    """Delete a Skill entity"""
    skill_code = request.skill_code
    try:
        deleted_entity = service.get(request)
        if not deleted_entity:
            return Result.failed(f"Skill '{skill_code}' not found")

        service.delete(request)
        return Result.succ(True)
    except Exception as e:
        logger.exception(f"Failed to delete Skill '{skill_code}': {e}")
        return Result.failed(str(e))


@router.post(
    "/query_fuzzy",
    response_model=Result[PaginationResult[SkillResponse]],
    dependencies=[Depends(check_api_key)],
)
async def fuzzy_query(
    query_filter: SkillQueryFilter,
    page: Optional[int] = Query(default=1, description="current page"),
    page_size: Optional[int] = Query(default=20, description="page size"),
    service: Service = Depends(get_service),
) -> Result[PaginationResult[SkillResponse]]:
    """Query Skill entities with fuzzy search"""
    try:
        return Result.succ(service.filter_list_page(query_filter, page, page_size))
    except Exception as e:
        logger.exception("skill fuzzy query exception!")
        return Result.failed(str(e))


@router.post(
    "/query",
    response_model=Result[SkillResponse],
    dependencies=[Depends(check_api_key)],
)
async def query(
    request: SkillRequest, service: Service = Depends(get_service)
) -> Result[SkillResponse]:
    """Query Skill entities"""
    try:
        result = service.get(request)
        if result is None:
            return Result.failed("Skill not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("skill query exception!")
        return Result.failed(str(e))


@router.post(
    "/sync_git",
    response_model=Result[List[SkillResponse]],
    dependencies=[Depends(check_api_key)],
)
async def sync_git(
    repo_url: str = Query(..., description="git repository url"),
    branch: str = Query("main", description="git branch"),
    force_update: bool = Query(False, description="force update existing skills"),
    service: Service = Depends(get_service),
) -> Result[List[SkillResponse]]:
    """Sync skills from git repository"""
    try:
        return Result.succ(await service.sync_from_git(repo_url, branch, force_update))
    except Exception as e:
        logger.exception("skill sync git exception!")
        return Result.failed(str(e))


@router.post(
    "/upload",
    response_model=Result[SkillResponse],
    dependencies=[Depends(check_api_key)],
)
async def upload_skill(
    file: UploadFile = File(..., description="skill zip file"),
    service: Service = Depends(get_service),
) -> Result[SkillResponse]:
    """Upload a skill from a zip file"""
    try:
        return Result.succ(await service.upload_from_zip(file))
    except Exception as e:
        logger.exception("skill upload exception!")
        return Result.failed(str(e))


@router.post(
    "/upload_folder",
    response_model=Result[SkillResponse],
    dependencies=[Depends(check_api_key)],
)
async def upload_skill_folder(
    skill_name: str = Query(..., description="skill name"),
    skill_path: str = Query(..., description="local skill folder path"),
    service: Service = Depends(get_service),
) -> Result[SkillResponse]:
    """Upload a skill from a local folder"""
    try:
        return Result.succ(await service.upload_from_folder(skill_name, skill_path))
    except Exception as e:
        logger.exception("skill upload folder exception!")
        return Result.failed(str(e))


# -------------------- File Operation Endpoints --------------------


@router.get(
    "/file/list/{skill_code}",
    response_model=Result[SkillFileListResponse],
    dependencies=[Depends(check_api_key)],
)
async def list_skill_files(
    skill_code: str,
    service: Service = Depends(get_service),
) -> Result[SkillFileListResponse]:
    """List all files in a skill directory"""
    try:
        files_data = service.list_skill_files(skill_code)
        return Result.succ(files_data)
    except Exception as e:
        logger.exception("skill file list exception!")
        return Result.failed(str(e))


@router.post(
    "/file/read",
    response_model=Result[SkillFileReadResponse],
    dependencies=[Depends(check_api_key)],
)
async def read_skill_file(
    request: SkillFileReadRequest,
    service: Service = Depends(get_service),
) -> Result[SkillFileReadResponse]:
    """Read a skill file's content"""
    try:
        file_data = service.read_skill_file(request.skill_code, request.file_path)
        return Result.succ(file_data)
    except Exception as e:
        logger.exception("skill file read exception!")
        return Result.failed(str(e))


@router.post(
    "/file/write",
    response_model=Result[SkillFileWriteResponse],
    dependencies=[Depends(check_api_key)],
)
async def write_skill_file(
    request: SkillFileWriteRequest,
    service: Service = Depends(get_service),
) -> Result[SkillFileWriteResponse]:
    """Write content to a skill file"""
    try:
        write_result = service.write_skill_file(request.skill_code, request.file_path, request.content)
        return Result.succ(write_result)
    except Exception as e:
        logger.exception("skill file write exception!")
        return Result.failed(str(e))


@router.post(
    "/file/create",
    response_model=Result[SkillFileWriteResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_skill_file(
    request: SkillFileWriteRequest,
    service: Service = Depends(get_service),
) -> Result[SkillFileWriteResponse]:
    """Create a new file in the skill directory"""
    try:
        create_result = service.create_skill_file(request.skill_code, request.file_path, request.content)
        return Result.succ(create_result)
    except Exception as e:
        logger.exception("skill file create exception!")
        return Result.failed(str(e))


@router.post(
    "/file/delete",
    response_model=Result[SkillFileWriteResponse],
    dependencies=[Depends(check_api_key)],
)
async def delete_skill_file(
    request: SkillFileReadRequest,
    service: Service = Depends(get_service),
) -> Result[SkillFileWriteResponse]:
    """Delete a file from the skill directory"""
    try:
        delete_result = service.delete_skill_file(request.skill_code, request.file_path)
        return Result.succ(delete_result)
    except Exception as e:
        logger.exception("skill file delete exception!")
        return Result.failed(str(e))


@router.post(
    "/file/rename",
    response_model=Result[SkillFileRenameResponse],
    dependencies=[Depends(check_api_key)],
)
async def rename_skill_file(
    request: SkillFileRenameRequest,
    service: Service = Depends(get_service),
) -> Result[SkillFileRenameResponse]:
    """Rename a file in the skill directory"""
    try:
        rename_result = service.rename_skill_file(request.skill_code, request.old_path, request.new_path)
        return Result.succ(rename_result)
    except Exception as e:
        logger.exception("skill file rename exception!")
        return Result.failed(str(e))


@router.post(
    "/file/upload_batch",
    response_model=Result[SkillFileBatchUploadResponse],
    dependencies=[Depends(check_api_key)],
)
async def batch_upload_files(
    request: SkillFileBatchUploadRequest,
    service: Service = Depends(get_service),
) -> Result[SkillFileBatchUploadResponse]:
    """Upload multiple files to a skill directory"""
    try:
        result = service.batch_upload_files(
            request.skill_code,
            [f.model_dump() for f in request.files],
            request.overwrite
        )
        return Result.succ(result)
    except Exception as e:
        logger.exception("skill file batch upload exception!")
        return Result.failed(str(e))


# -------------------- Async Sync Task Endpoints --------------------


@router.post(
    "/sync_git_async",
    response_model=Result[SkillSyncTaskResponse],
    dependencies=[Depends(check_api_key)],
)
async def sync_git_async(
    request: SkillSyncTaskRequest,
    service: Service = Depends(get_service),
) -> Result[SkillSyncTaskResponse]:
    """Create and start an async git sync task"""
    try:
        task = service.create_sync_task(
            repo_url=request.repo_url,
            branch=request.branch,
            force_update=request.force_update,
        )
        return Result.succ(task)
    except Exception as e:
        logger.exception("skill async sync git exception!")
        return Result.failed(str(e))


@router.get(
    "/sync_status/{task_id}",
    response_model=Result[SkillSyncTaskResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_sync_status(
    task_id: str,
    service: Service = Depends(get_service),
) -> Result[SkillSyncTaskResponse]:
    """Get the status of an async sync task"""
    try:
        task = service.get_sync_task_status(task_id)
        if task:
            return Result.succ(task)
        return Result.failed(f"Task {task_id} not found")
    except Exception as e:
        logger.exception("skill sync status exception!")
        return Result.failed(str(e))


@router.get(
    "/recent_sync_tasks",
    response_model=Result[List[SkillSyncTaskResponse]],
    dependencies=[Depends(check_api_key)],
)
async def get_recent_sync_tasks(
    limit: int = Query(10, description="number of recent tasks to return"),
    service: Service = Depends(get_service),
) -> Result[List[SkillSyncTaskResponse]]:
    """Get recent sync tasks"""
    try:
        dao = service._get_sync_task_dao()
        tasks = dao.get_recent_tasks(limit)
        task_responses = [SkillSyncTaskResponse.from_entity(t) for t in tasks]
        return Result.succ(task_responses)
    except Exception as e:
        logger.exception("skill recent tasks exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app