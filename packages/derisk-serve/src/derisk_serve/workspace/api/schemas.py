from datetime import datetime
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP


# ------------------------ Workspace ------------------------
class WorkspaceRequest(BaseModel):
    """Workspace create/update request"""

    workspace_code: Optional[str] = Field(None, description="workspace code (unique)")
    name: str = Field(..., min_length=1, max_length=128, description="workspace name")
    description: Optional[str] = Field(None, description="workspace description")
    type: str = Field("scenario", description="scenario / team")
    scenario_type: Optional[str] = Field(None, description="sre / data_ops / ...")
    owner_user_id: Optional[int] = Field(None, description="owner user id")
    default_agent_app_code: Optional[str] = Field(
        None, description="default agent app code"
    )
    settings: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="notification channels / default llm / ..."
    )
    is_archived: Optional[bool] = Field(False, description="archived flag")

    model_config = ConfigDict(title=f"WorkspaceRequest for {SERVE_APP_NAME_HUMP}")


class WorkspaceResponse(BaseModel):
    """Workspace response"""

    id: int
    workspace_code: str
    name: str
    description: Optional[str] = None
    type: str
    scenario_type: Optional[str] = None
    owner_user_id: int
    default_agent_app_code: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    is_archived: bool = False
    member_count: int = 0
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(
        title=f"WorkspaceResponse for {SERVE_APP_NAME_HUMP}",
        from_attributes=True,
    )


class WorkspaceListFilter(BaseModel):
    """List filter — empty for MVP"""

    user_id: Optional[int] = Field(
        None, description="only workspaces the user is a member of"
    )
    scenario_type: Optional[str] = None
    include_archived: bool = False


# ------------------------ Workspace Member ------------------------
class WorkspaceMemberRequest(BaseModel):
    workspace_id: int
    user_id: int
    role: str = Field("contributor", description="owner/contributor/approver/viewer")


class WorkspaceMemberResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    user_name: Optional[str] = None
    role: str
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberListRequest(BaseModel):
    workspace_id: int


# ------------------------ Workspace Resource ------------------------
class WorkspaceResourceRequest(BaseModel):
    workspace_id: int
    type: str = Field(
        ..., description="data_source/knowledge_space/environment/mcp/skill/llm_model"
    )
    name: str = Field(..., max_length=128, description="display name in workspace")
    category: str = Field(
        "scenario_bound",
        description="generic / scenario_bound / scenario_specific",
    )
    physical_ref: Optional[str] = Field(
        None, description="connect_config.id / knowledge_space slug / app_code / ..."
    )
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    access_mode: str = Field("read", description="read/write/admin")
    is_active: bool = True


class WorkspaceResourceResponse(BaseModel):
    id: int
    workspace_id: int
    type: str
    name: str
    category: str
    physical_ref: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    access_mode: str
    is_active: bool
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class WorkspaceResourceListRequest(BaseModel):
    workspace_id: int
    type: Optional[str] = None
