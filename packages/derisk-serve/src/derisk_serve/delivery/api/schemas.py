"""Delivery API schemas."""
from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class DeliveryRequest(BaseModel):
    id: Optional[int] = None
    artifact_id: Optional[int] = None
    task_id: int
    workspace_id: int
    category: str = Field(default="notify", description="notify (MVP only)")
    channel: str = Field(..., description="email / feishu / in_app")
    target: str = Field(..., description="recipient: email address / feishu chat_id / user_id")
    title: Optional[str] = None
    message: Optional[str] = None
    format: str = Field(default="message_card", description="pdf / message_card / json")
    require_intervention: str = Field(default="none", description="none / review")
    scheduled_at: Optional[str] = None


class DeliveryResponse(BaseModel):
    id: int
    artifact_id: Optional[int] = None
    task_id: int
    workspace_id: int
    category: str
    channel: str
    target: str
    title: Optional[str] = None
    message: Optional[str] = None
    format: str
    status: str = "pending"
    require_intervention: str = "none"
    intervention_id: Optional[int] = None
    scheduled_at: Optional[str] = None
    sent_at: Optional[str] = None
    result_json: Optional[Dict[str, Any]] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class DeliveryListFilter(BaseModel):
    workspace_id: int
    task_id: Optional[int] = None
    status: Optional[str] = None
    channel: Optional[str] = None
    limit: int = 100
