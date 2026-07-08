"""Admin endpoints for the job engine: create / list / get / retry / cancel / delete / stats / workers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..api.schemas import (
    JobListResponse,
    JobRetryResponse,
    JobStatsResponse,
    JobType,
    ServeRequest,
    ServeResponse,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import JobDao, JobEntity
from ..service.service import Service

router = APIRouter()

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    if global_system_app is None:
        raise HTTPException(status_code=503, detail="job service not initialized")
    svc = global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
    if svc is None:
        raise HTTPException(status_code=503, detail="job service not registered")
    return svc


def _to_resp(entity: JobEntity) -> ServeResponse:
    return get_service().dao.to_response(entity)


@router.get("/jobs", response_model=Result[JobListResponse])
async def list_jobs(
    job_type: Optional[str] = Query(None),
    space_slug: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: Service = Depends(get_service),
):
    """List jobs with optional filters."""
    rows = service.dao.list_jobs(
        job_type=job_type, space_slug=space_slug, status=status,
        limit=limit, offset=offset,
    )
    total = service.dao.count(
        job_type=job_type, space_slug=space_slug, status=status,
    )
    return Result.succ(
        JobListResponse(items=[service.dao.to_response(r) for r in rows], total=total)
    )


@router.post("/jobs", response_model=Result[ServeResponse])
async def create_job(req: ServeRequest, service: Service = Depends(get_service)):
    """Submit a new job (supports scheduling via not_before/run_after_seconds
    and worker affinity via required_worker)."""
    if req.job_type not in service.handler_types():
        raise HTTPException(
            status_code=400,
            detail=f"no handler registered for job_type '{req.job_type}'",
        )
    entity = await asyncio.to_thread(service.dao.submit, req)
    return Result.succ(service.dao.to_response(entity))


@router.get("/jobs/workers", response_model=Result[Dict[str, Any]])
async def list_workers(service: Service = Depends(get_service)):
    """Introspect this instance's worker (id, tags, subscribe_types, load)."""
    return Result.succ(service.worker_info())


@router.get("/jobs/types", response_model=Result[List[JobType]])
async def list_job_types(service: Service = Depends(get_service)):
    """List registered job types + their payload param schemas (for the admin
    UI to render a dynamic create form)."""
    return Result.succ([JobType(**m) for m in service.handler_meta()])


@router.get("/jobs/{job_id}", response_model=Result[ServeResponse])
async def get_job(job_id: str, service: Service = Depends(get_service)):
    row = service.dao.get(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Result.succ(service.dao.to_response(row))


@router.post("/jobs/{job_id}/retry", response_model=Result[JobRetryResponse])
async def retry_job(job_id: str, service: Service = Depends(get_service)):
    """Reset a failed/done job back to pending."""
    row = service.dao.retry(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Result.succ(JobRetryResponse(id=row.id, status=row.status))


@router.post("/jobs/{job_id}/cancel", response_model=Result[JobRetryResponse])
async def cancel_job(job_id: str, service: Service = Depends(get_service)):
    """Cancel a pending job (running jobs must let their lease expire)."""
    ok = service.dao.cancel(job_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="job not cancellable (not pending or not found)",
        )
    return Result.succ(JobRetryResponse(id=job_id, status="failed"))


@router.delete("/jobs/{job_id}", response_model=Result[bool])
async def delete_job(job_id: str, service: Service = Depends(get_service)):
    ok = service.dao.delete(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return Result.succ(True)


@router.get("/jobs/stats", response_model=Result[JobStatsResponse])
async def job_stats(service: Service = Depends(get_service)):
    s = service.dao.stats()
    return Result.succ(
        JobStatsResponse(
            total=s.get("total", 0),
            by_status=s.get("by_status", {}),
            by_type=s.get("by_type", {}),
            by_type_status=s.get("by_type_status", {}),
            by_executor=s.get("by_executor", {}),
        )
    )


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Register the Service component (mirrors cron's init_endpoints)."""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app