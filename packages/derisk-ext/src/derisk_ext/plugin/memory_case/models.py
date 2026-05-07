from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .case_context import CASE_CONTEXT_KEY


def default_case_fingerprint(data: dict) -> str:
    """Stable fingerprint when clients omit it (MCP / LLM payloads)."""
    case_id = str(data.get("case_id") or "")
    symptom = str(data.get("symptom_summary") or "").strip().lower()
    meta = data.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    ctx = meta.get(CASE_CONTEXT_KEY)
    ctx = ctx if isinstance(ctx, dict) else {}
    env = str(ctx.get("environment") or "default").strip().lower()
    app = str(ctx.get("app_code") or "default").strip().lower()
    tenant = str(ctx.get("tenant_id") or "").strip().lower()
    team = str(ctx.get("team_id") or "").strip().lower()
    blob = "|".join([tenant, team, app, env, case_id, symptom[:4000]])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CandidateCaseLifecycle(str, Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STALE = "stale"


class CandidateCase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="before")
    @classmethod
    def _normalize_metadata_scope_and_fingerprint(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        meta = dict(d.get("metadata") or {})
        raw_ctx = meta.get(CASE_CONTEXT_KEY)
        ctx = dict(raw_ctx) if isinstance(raw_ctx, dict) else {}
        for key in ("tenant_id", "team_id", "app_code", "environment"):
            if key in d and d[key] is not None:
                ctx.setdefault(key, d[key])
                del d[key]
        if ctx:
            meta[CASE_CONTEXT_KEY] = ctx
        d["metadata"] = meta
        fp = d.get("fingerprint")
        if fp is None or (isinstance(fp, str) and not str(fp).strip()):
            d["fingerprint"] = default_case_fingerprint(d)
        return d

    case_id: str = Field(..., description="Unique candidate case id")
    fingerprint: str = Field(..., description="Incident fingerprint")
    incident_title: str = Field(
        "",
        max_length=512,
        description="Short incident title for lists and UI",
    )
    symptom_summary: str = Field("", description="Symptom summary")
    hypotheses: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    resolution: str = Field("", description="Resolution summary")
    handling_path: str = Field(
        "",
        description=(
            "Free-form how this case was worked: branches considered, what was tried, "
            "dead ends, heuristics—reference only, not a strict step list for replay."
        ),
    )
    root_cause: str = Field(
        "",
        description="Confirmed root cause one-liner when known",
    )

    @field_validator("handling_path", mode="before")
    @classmethod
    def _coerce_handling_path(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return "\n".join(
                json.dumps(item, ensure_ascii=False)
                if isinstance(item, dict)
                else str(item)
                for item in v
            )
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    effectiveness: str = Field("", description="Effectiveness summary")
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    lifecycle: CandidateCaseLifecycle = Field(default=CandidateCaseLifecycle.DRAFT)
    source_conv_id: Optional[str] = None
    source_session_id: Optional[str] = None
    markdown_summary: str = Field("", description="Shared markdown summary")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Case meta: routing hints and context live under metadata['case_context'] "
            "(app_code, environment, tenant_id, team_id, application_name, data_sources, …)."
        ),
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryRequestContext(BaseModel):
    """Narrowing filters for ``memory_case_search`` — **not** table columns.

    Values are compared only against ``metadata.case_context`` inside ``metadata_json``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tenant_id: Optional[str] = Field(
        None, description="Optional; if set, rows must match case_context.tenant_id"
    )
    team_id: Optional[str] = Field(
        None, description="Optional; if set, rows must match case_context.team_id"
    )
    app_code: str = Field(
        "default",
        description=(
            "Routing hint: missing/empty/'default' → search does not filter by "
            "case_context.app_code; else equality on JSON case_context.app_code"
        ),
    )
    environment: str = Field(
        "default",
        description=(
            "Routing hint: missing/empty/'default' → search does not filter by "
            "case_context.environment; else equality on JSON case_context.environment"
        ),
    )
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
