"""Cron API endpoints.

This module provides REST API endpoints for cron job management.
"""

from functools import cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import (
    CronStatusResponse,
    ServeRequest,
    ServerResponse,
)

router = APIRouter()

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance."""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list.

    Args:
        api_keys: The string api keys.

    Returns:
        List of api keys.
    """
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    request: Request = None,
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key.

    If the api key is not set, allow all.
    """
    if request.url.path.startswith("/api/v1"):
        return None

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
        return None


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get(
    "/status",
    response_model=Result[CronStatusResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_status(
    service: Service = Depends(get_service),
) -> Result[CronStatusResponse]:
    """Get the scheduler status.

    Returns:
        The scheduler status summary.
    """
    status = await service.status()
    return Result.succ(
        CronStatusResponse(
            enabled=status.enabled,
            running=status.running,
            jobs=status.jobs,
            enabled_jobs=status.enabled_jobs,
            next_wake_at_ms=status.next_wake_at_ms,
        )
    )


@router.get(
    "/jobs",
    response_model=Result[List[ServerResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_jobs(
    include_disabled: bool = Query(
        default=False, description="Include disabled jobs"
    ),
    service: Service = Depends(get_service),
) -> Result[List[ServerResponse]]:
    """List all scheduled jobs.

    Args:
        include_disabled: Whether to include disabled jobs.

    Returns:
        List of cron jobs.
    """
    responses = service.list_job_responses(include_disabled)
    return Result.succ(responses)


@router.post(
    "/jobs",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_job(
    request: ServeRequest,
    service: Service = Depends(get_service),
) -> Result[ServerResponse]:
    """Create a new cron job.

    Args:
        request: The job creation request.

    Returns:
        The created cron job.
    """
    response = await service.add_job(request)
    return Result.succ(response)


@router.get(
    "/jobs/{job_id}",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_job(
    job_id: str,
    service: Service = Depends(get_service),
) -> Result[ServerResponse]:
    """Get a specific job by ID.

    Args:
        job_id: The job ID.

    Returns:
        The cron job details.
    """
    response = service.get_job_response(job_id)
    if not response:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return Result.succ(response)


@router.patch(
    "/jobs/{job_id}",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def update_job(
    job_id: str,
    request: ServeRequest,
    service: Service = Depends(get_service),
) -> Result[ServerResponse]:
    """Update a cron job.

    Args:
        job_id: The job ID.
        request: The update request.

    Returns:
        The updated cron job.
    """
    try:
        response = await service.update_job(job_id, request)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/jobs/{job_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_job(
    job_id: str,
    service: Service = Depends(get_service),
):
    """Delete a cron job.

    Args:
        job_id: The job ID.
    """
    removed = await service.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return Result.succ(None)


@router.post(
    "/jobs/{job_id}/run",
    dependencies=[Depends(check_api_key)],
)
async def run_job(
    job_id: str,
    force: bool = Query(default=False, description="Force run even if disabled"),
    service: Service = Depends(get_service),
):
    """Manually trigger a job execution.

    Args:
        job_id: The job ID.
        force: Force run even if job is disabled.

    Returns:
        Success status.
    """
    triggered = await service.run_job(job_id, force)
    if not triggered:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to trigger job: {job_id}. Job may not exist or is disabled.",
        )
    return Result.succ({"triggered": True, "job_id": job_id})


@router.put(
    "/jobs/{job_id}",
    response_model=Result[ServerResponse],
    dependencies=[Depends(check_api_key)],
)
async def replace_job(
    job_id: str,
    request: ServeRequest,
    service: Service = Depends(get_service),
) -> Result[ServerResponse]:
    """Replace a cron job completely.

    Args:
        job_id: The job ID.
        request: The replacement request.

    Returns:
        The replaced cron job.
    """
    # Ensure ID matches
    request.id = job_id
    try:
        response = await service.update_job(job_id, request)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/jobs/{job_id}/enable",
    dependencies=[Depends(check_api_key)],
)
async def enable_job(
    job_id: str,
    service: Service = Depends(get_service),
):
    """Enable a cron job.

    Args:
        job_id: The job ID.
    """
    enable_request = ServeRequest(id=job_id, name="", enabled=True)
    try:
        await service.update_job(job_id, enable_request)
        return Result.succ({"enabled": True, "job_id": job_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/jobs/{job_id}/disable",
    dependencies=[Depends(check_api_key)],
)
async def disable_job(
    job_id: str,
    service: Service = Depends(get_service),
):
    """Disable a cron job.

    Args:
        job_id: The job ID.
    """
    # Get current job to preserve fields
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    from .schemas import CronScheduleSchema, CronPayloadSchema
    disable_request = ServeRequest(
        id=job_id,
        name=job.name,
        description=job.description,
        enabled=False,
        schedule=CronScheduleSchema(
            kind=job.schedule.kind.value,
            at=job.schedule.at,
            every_ms=job.schedule.every_ms,
            anchor_ms=job.schedule.anchor_ms,
            expr=job.schedule.expr,
            tz=job.schedule.tz,
        ),
        payload=CronPayloadSchema(
            kind=job.payload.kind.value,
            message=job.payload.message,
            agent_id=job.payload.agent_id,
            timeout_seconds=job.payload.timeout_seconds,
            session_mode=job.payload.session_mode.value if job.payload.session_mode else "isolated",
            conv_session_id=job.payload.conv_session_id,
        ),
    )
    await service.update_job(job_id, disable_request)
    return Result.succ({"enabled": False, "job_id": job_id})


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints.

    Args:
        system_app: The system application instance.
        config: The service configuration.
    """
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app