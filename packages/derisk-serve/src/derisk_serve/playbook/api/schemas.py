from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class PlaybookRequest(BaseModel):
    id: Optional[int] = None
    workspace_id: int
    name: str
    scenario_type: Optional[str] = None
    task_type: str = Field("routine", description="routine/pipeline/incident/adhoc")
    trigger: Optional[Dict[str, Any]] = Field(default_factory=dict)
    declaration: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="strategy declaration DSL: skills/context/deliverables/distill",
    )
    is_active: bool = True

    model_config = ConfigDict(title=f"PlaybookRequest for {SERVE_APP_NAME_HUMP}")


class PlaybookResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    scenario_type: Optional[str] = None
    task_type: str
    trigger: Dict[str, Any] = Field(default_factory=dict)
    declaration: Dict[str, Any] = Field(default_factory=dict)
    current_version: int = 1
    is_active: bool = True
    created_by_user_id: Optional[int] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(from_attributes=True)


class PlaybookListFilter(BaseModel):
    workspace_id: int
    scenario_type: Optional[str] = None
    task_type: Optional[str] = None
    is_active: Optional[bool] = True


class PlaybookValidateRequest(BaseModel):
    declaration: Dict[str, Any]


class PlaybookVersionResponse(BaseModel):
    id: int
    playbook_id: int
    version: int
    declaration: Dict[str, Any]
    changelog: Optional[str] = None
    created_by_user_id: Optional[int] = None
    gmt_created: str

    model_config = ConfigDict(from_attributes=True)
