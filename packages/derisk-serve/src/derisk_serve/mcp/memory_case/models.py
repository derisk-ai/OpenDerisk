from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class CandidateCaseLifecycle(str, Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STALE = "stale"


class CandidateCase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: str = Field(..., description="Unique candidate case id")
    tenant_id: Optional[str] = Field(None, description="Tenant scope")
    team_id: Optional[str] = Field(None, description="Team scope")
    app_code: str = Field("default", description="Application scope")
    environment: str = Field("default", description="Environment scope")
    fingerprint: str = Field(..., description="Incident fingerprint")
    symptom_summary: str = Field("", description="Symptom summary")
    hypotheses: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    resolution: str = Field("", description="Resolution summary")
    effectiveness: str = Field("", description="Effectiveness summary")
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    lifecycle: CandidateCaseLifecycle = Field(default=CandidateCaseLifecycle.DRAFT)
    source_conv_id: Optional[str] = None
    source_session_id: Optional[str] = None
    markdown_summary: str = Field("", description="Shared markdown summary")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryRequestContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tenant_id: Optional[str] = None
    team_id: Optional[str] = None
    app_code: str = "default"
    environment: str = "default"
    conv_id: Optional[str] = None
    service: Optional[str] = None
    metric: Optional[str] = None
    labels: Dict[str, Any] = Field(default_factory=dict)
    alert_text: Optional[str] = None

    def scope_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "team_id": self.team_id,
            "app_code": self.app_code,
            "environment": self.environment,
        }

