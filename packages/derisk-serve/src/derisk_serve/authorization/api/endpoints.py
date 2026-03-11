"""Authorization Audit Log API endpoints.

This module provides REST API endpoints for authorization audit log management.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from functools import cache

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..models.authorization_audit_db import (
    AuthorizationAuditLog,
    AuthorizationAuditLogDao,
    AuthorizationAuditStats,
)

router = APIRouter()

global_system_app: Optional[SystemApp] = None
_audit_log_dao: Optional[AuthorizationAuditLogDao] = None


def get_audit_log_dao() -> AuthorizationAuditLogDao:
    """Get the audit log DAO instance."""
    global _audit_log_dao
    if _audit_log_dao is None:
        _audit_log_dao = AuthorizationAuditLogDao()
    return _audit_log_dao


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list."""
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    request: Request = None,
    api_keys: str = "",
) -> Optional[str]:
    """Check the api key."""
    if request and request.url.path.startswith("/api/v1"):
        return None

    if api_keys:
        keys = _parse_api_keys(api_keys)
        if auth is None or (token := auth.credentials) not in keys:
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
    return None


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get(
    "/logs",
    response_model=Result[dict],
)
async def list_audit_logs(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    decision: Optional[str] = Query(None, description="Filter by decision type"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    start_time: Optional[datetime] = Query(None, description="Start time filter"),
    end_time: Optional[datetime] = Query(None, description="End time filter"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    dao: AuthorizationAuditLogDao = Depends(get_audit_log_dao),
) -> Result[dict]:
    """List authorization audit logs with filters and pagination.

    Args:
        session_id: Filter by session ID
        user_id: Filter by user ID
        agent_name: Filter by agent name
        tool_name: Filter by tool name
        decision: Filter by decision type (granted/denied/cached/need_confirmation)
        risk_level: Filter by risk level (safe/low/medium/high/critical)
        start_time: Start time for date range filter
        end_time: End time for date range filter
        page: Page number (1-indexed)
        page_size: Number of records per page

    Returns:
        Paginated list of audit logs
    """
    logs = await dao.list_async(
        session_id=session_id,
        user_id=user_id,
        agent_name=agent_name,
        tool_name=tool_name,
        decision=decision,
        risk_level=risk_level,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    total = await dao.count_async(
        session_id=session_id,
        user_id=user_id,
        agent_name=agent_name,
        tool_name=tool_name,
        decision=decision,
        risk_level=risk_level,
        start_time=start_time,
        end_time=end_time,
    )

    return Result.succ(
        {
            "items": [log.to_dict() for log in logs],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }
    )


@router.get(
    "/logs/{log_id}",
    response_model=Result[dict],
)
async def get_audit_log(
    log_id: int,
    dao: AuthorizationAuditLogDao = Depends(get_audit_log_dao),
) -> Result[dict]:
    """Get a specific audit log by ID.

    Args:
        log_id: The audit log ID

    Returns:
        The audit log details
    """
    log = await dao.get_by_id_async(log_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Audit log not found: {log_id}")
    return Result.succ(log.to_dict())


@router.get(
    "/stats",
    response_model=Result[dict],
)
async def get_audit_stats(
    start_time: Optional[datetime] = Query(
        None, description="Start time for statistics"
    ),
    end_time: Optional[datetime] = Query(None, description="End time for statistics"),
    dao: AuthorizationAuditLogDao = Depends(get_audit_log_dao),
) -> Result[dict]:
    """Get authorization audit statistics.

    Args:
        start_time: Start time for statistics period
        end_time: End time for statistics period

    Returns:
        Statistics summary
    """
    stats = await dao.get_stats_async(start_time=start_time, end_time=end_time)
    return Result.succ(stats.to_dict())


@router.get(
    "/tools/usage",
    response_model=Result[List[dict]],
)
async def get_tool_usage_stats(
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time"),
    dao: AuthorizationAuditLogDao = Depends(get_audit_log_dao),
) -> Result[List[dict]]:
    """Get tool usage statistics.

    Args:
        start_time: Start time for statistics period
        end_time: End time for statistics period

    Returns:
        Per-tool usage statistics
    """
    stats = dao.get_tool_usage_stats(start_time=start_time, end_time=end_time)
    return Result.succ(stats)


@router.delete(
    "/logs/cleanup",
    response_model=Result[dict],
)
async def cleanup_old_logs(
    days: int = Query(30, ge=1, le=365, description="Keep logs from last N days"),
    dao: AuthorizationAuditLogDao = Depends(get_audit_log_dao),
) -> Result[dict]:
    """Delete audit logs older than specified days.

    Args:
        days: Number of days to keep (default 30)

    Returns:
        Number of deleted records
    """
    deleted_count = dao.delete_old_logs(days=days)
    return Result.succ(
        {
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} audit logs older than {days} days",
        }
    )


def init_endpoints(system_app: SystemApp) -> None:
    """Initialize the endpoints.

    Args:
        system_app: The system application instance
    """
    global global_system_app
    global_system_app = system_app
