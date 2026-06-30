"""Intervention API schemas."""
from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class InterventionRequest(BaseModel):
    id: Optional[int] = None
    task_id: Optional[int] = None
    conv_uid: Optional[str] = None
    workspace_id: int
    type: str = Field(default="review", description="MVP only: review")
    requested_by: str = Field(default="system", description="system / agent / user")
    question: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class InterventionResponse(BaseModel):
    id: int
    task_id: Optional[int] = None
    conv_uid: Optional[str] = None
    workspace_id: int
    type: str
    status: str = "requested"
    requested_by: str
    requested_at: str
    question: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    resolved_by_user_id: Optional[int] = None
    resolved_at: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    distillation: Optional[Dict[str, Any]] = None
    linked_asset_id: Optional[int] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class InterventionResolveRequest(BaseModel):
    decision: Optional[Dict[str, Any]] = None
    distillation: Optional[Dict[str, Any]] = None
    linked_asset_id: Optional[int] = None
    resolved_by_user_id: Optional[int] = None


class InterventionListFilter(BaseModel):
    workspace_id: int
    task_id: Optional[int] = None
    status: Optional[str] = None
    limit: int = 100
