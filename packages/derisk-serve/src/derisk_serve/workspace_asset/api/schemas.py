"""WorkspaceAsset API schemas."""
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class AssetRequest(BaseModel):
    id: Optional[int] = None
    workspace_id: int
    type: str = Field(..., description="historical_artifact / case")
    name: str
    description: Optional[str] = None
    scope: str = Field(default="workspace", description="workspace / organization")
    content_ref: Optional[str] = None
    content_text: Optional[str] = None
    source_task_id: Optional[int] = None
    source_artifact_id: Optional[int] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    is_published: bool = False
    created_by: Optional[str] = None


class AssetResponse(BaseModel):
    id: int
    workspace_id: int
    type: str
    name: str
    description: Optional[str] = None
    scope: str = "workspace"
    content_ref: Optional[str] = None
    content_text: Optional[str] = None
    current_version: int = 1
    source_task_id: Optional[int] = None
    source_artifact_id: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    is_published: bool = False
    created_by: Optional[str] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class AssetListFilter(BaseModel):
    workspace_id: int
    type: Optional[str] = None
    source_task_id: Optional[int] = None
    is_published: Optional[bool] = None
    limit: int = 100


class AssetSearchRequest(BaseModel):
    workspace_id: int
    query: Optional[str] = None
    type: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: int = 10


class TaskAssetLinkRequest(BaseModel):
    task_id: int
    asset_id: int
    link_type: str = Field(..., description="consumed / produced")


class TaskAssetLinkResponse(BaseModel):
    id: int
    task_id: int
    asset_id: int
    link_type: str
    gmt_created: str

    model_config = ConfigDict(from_attributes=True)


class AssetVersionResponse(BaseModel):
    id: int
    asset_id: int
    version: int
    content_ref: Optional[str] = None
    diff_summary: Optional[str] = None
    created_by: Optional[str] = None
    gmt_created: str

    model_config = ConfigDict(from_attributes=True)
