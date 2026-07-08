"""Pydantic schemas for the job engine.

`ServeRequest`/`ServerResponse` are the REQ/RES generics for BaseDao; the
Job*Out models back the admin endpoints (list/get/retry/stats).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ServeRequest(BaseModel):
    """Submit payload for a job (the DAO REQ type)."""

    job_type: str
    space_slug: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 5
    max_attempts: int = 3
    # v2: scheduling — exactly one of not_before / run_after_seconds.
    not_before: Optional[str] = None  # ISO datetime; not claimable before
    run_after_seconds: Optional[int] = None  # relative; resolved to not_before
    # v2: worker affinity — token list; a worker whose tags superset this may claim.
    required_worker: Optional[List[str]] = None


class ServeResponse(BaseModel):
    """The DAO RES type — a flat view of one job row."""

    id: str
    job_type: str
    space_slug: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str
    priority: int = 5
    attempts: int = 0
    max_attempts: int = 3
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    lease_until: Optional[str] = None
    last_error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    not_before: Optional[str] = None
    required_worker: Optional[List[str]] = None
    executed_by: Optional[str] = None
    executed_at: Optional[str] = None
    attempts_history: Optional[List[Dict[str, Any]]] = None
    gmt_created: Optional[str] = None
    gmt_modified: Optional[str] = None


class JobListResponse(BaseModel):
    """Admin: list jobs."""
    items: List[ServeResponse]
    total: int = 0


class JobStatsResponse(BaseModel):
    """Admin: aggregate stats."""
    by_status: Dict[str, int] = Field(default_factory=dict)
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_type_status: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    by_executor: Dict[str, int] = Field(default_factory=dict)
    total: int = 0


class JobType(BaseModel):
    """A registered job type + its payload param schema (JSON Schema)."""
    job_type: str
    description: str = ""
    params_schema: Optional[Dict[str, Any]] = None


class JobRetryResponse(BaseModel):
    """Admin: retry result."""
    id: str
    status: str