from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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
    blob = "|".join([app, env, case_id, symptom[:4000]])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CandidateCaseLifecycle(str, Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STALE = "stale"


class CaseRelationType(str, Enum):
    """Relation between two cases, determined by multi-signal analysis.

    Ordered from strongest (reusable) to weakest (informational only).
    """

    SAME_ROOT_CAUSE = "same_root_cause"       # root cause + struct match
    CAUSED_BY = "caused_by"                   # A's root cause triggered B
    RECURRENCE_OF = "recurrence_of"           # B is a later occurrence of A
    SIMILAR_DIAGNOSIS = "similar_diagnosis"   # diag path matches, root cause differs
    SURFACE_SIMILAR = "surface_similar"       # symptom text matches only — do NOT reuse
    CONTRADICTION = "contradiction"           # conflicting resolution / root cause


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
        for key in ("app_code", "environment"):
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
    symptom_summary: str = Field("", description="Symptom summary")
    diagnosis: str = Field(
        "",
        description=(
            "Free-form Markdown describing the diagnostic process: "
            "hypotheses considered, actions taken, dead ends, heuristics, "
            "and the reasoning chain from symptom to root cause."
        ),
    )
    resolution: str = Field("", description="Resolution summary")
    root_cause: str = Field("", description="Confirmed root cause one-liner when known")
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    lifecycle: CandidateCaseLifecycle = Field(default=CandidateCaseLifecycle.DRAFT)
    source_conv_id: Optional[str] = None
    markdown_summary: str = Field("", description="Shared markdown summary")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Case meta: routing hints and context live under metadata['case_context'] "
            "(app_code, environment, application_name, data_sources, …)."
        ),
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryRequestContext(BaseModel):
    """Narrowing filters for ``memory_case_search`` — **not** table columns.

    Values are compared only against ``metadata.case_context`` inside ``metadata_json``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

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
            "app_code": self.app_code,
            "environment": self.environment,
        }
