from datetime import datetime
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class TaskRequest(BaseModel):
    id: Optional[int] = None
    workspace_id: int
    parent_task_id: Optional[int] = None
    type: str = Field("adhoc", description="routine/pipeline/incident/adhoc")
    title: str
    description: Optional[str] = None
    status: str = Field("draft", description="draft/pending_trigger/running/awaiting_human/blocked/delivered/closed/archived/failed")
    priority: Optional[str] = "normal"
    triggered_by: str = Field("manual", description="timer/webhook/alert/manual")
    trigger_ref: Optional[str] = None
    playbook_id: Optional[int] = None
    playbook_version_id: Optional[int] = None
    conv_session_id: Optional[str] = Field(None, description="conversation session id bound to this task")
    created_by_user_id: Optional[int] = None
    assigned_agents: Optional[List[str]] = Field(default_factory=list)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    due_at: Optional[datetime] = None

    model_config = ConfigDict(title=f"TaskRequest for {SERVE_APP_NAME_HUMP}")


class TaskResponse(BaseModel):
    id: int
    workspace_id: int
    parent_task_id: Optional[int] = None
    type: str
    title: str
    description: Optional[str] = None
    status: str
    priority: Optional[str] = None
    triggered_by: str
    trigger_ref: Optional[str] = None
    playbook_id: Optional[int] = None
    playbook_version_id: Optional[int] = None
    conv_session_id: Optional[str] = None
    created_by_user_id: Optional[int] = None
    assigned_agents: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    due_at: Optional[str] = None
    started_at: Optional[str] = None
    closed_at: Optional[str] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class TaskListFilter(BaseModel):
    workspace_id: int
    status: Optional[str] = None
    type: Optional[str] = None
    user_id: Optional[int] = None
    include_archived: bool = False
    limit: int = 100


class TaskRelationRequest(BaseModel):
    parent_task_id: int
    child_task_id: int
    relation_type: str = Field("spawned_by", description="spawned_by/escalated_to/blocked_by")


class TaskCloseRequest(BaseModel):
    task_id: int
    distill_completed: bool = Field(
        False, description="must be true — server enforces distill before close"
    )
