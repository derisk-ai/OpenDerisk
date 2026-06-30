"""Trigger API schemas."""
from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class TriggerSourceRequest(BaseModel):
    id: Optional[int] = None
    workspace_id: int
    type: str = Field(..., description="timer / webhook / alert / manual")
    name: str
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    target_playbook_id: int
    is_active: bool = True


class TriggerSourceResponse(BaseModel):
    id: int
    workspace_id: int
    type: str
    name: str
    config: Dict[str, Any] = Field(default_factory=dict)
    target_playbook_id: int
    is_active: bool = True
    last_fired_at: Optional[str] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class TriggerListFilter(BaseModel):
    workspace_id: int
    type: Optional[str] = None
    is_active: Optional[bool] = None
    limit: int = 100


class TriggerFireRequest(BaseModel):
    """Manual fire request — carries arbitrary payload to inject as task input."""
    workspace_id: int
    trigger_id: int
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
