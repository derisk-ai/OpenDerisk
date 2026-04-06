"""SQL Guard API Pydantic models."""

from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict


class SQLCheckRequest(BaseModel):
    """Request to manually check SQL."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    sql: str
    user_id: Optional[str] = None
    datasource_id: Optional[int] = None
    db_name: Optional[str] = None
    mode: Optional[str] = None


class SQLCheckResponse(BaseModel):
    """Response from SQL check."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    allowed: bool
    risk_level: str = "safe"
    risk_score: int = 0
    blocked_rules: List[str] = []
    warnings: List[str] = []
    rewritten_sql: Optional[str] = None
    sql_type: str = "UNKNOWN"


class GuardConfigResponse(BaseModel):
    """Current Guard configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: bool = True
    default_mode: str = "readonly"
    audit_enabled: bool = True
    default_select_limit: int = 1000
    max_select_limit: int = 10000
    disabled_rules: List[str] = []


class GuardConfigUpdateRequest(BaseModel):
    """Request to update Guard configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: Optional[bool] = None
    default_mode: Optional[str] = None
    audit_enabled: Optional[bool] = None
    default_select_limit: Optional[int] = None
    max_select_limit: Optional[int] = None
    disabled_rules: Optional[List[str]] = None


class RuleInfo(BaseModel):
    """Information about a guard rule."""

    name: str
    description: str
    enabled: bool


class RuleUpdateRequest(BaseModel):
    """Request to update a rule's state."""

    enabled: bool


class AuditLogResponse(BaseModel):
    """Single audit log entry."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    datasource_id: Optional[int] = None
    db_name: Optional[str] = None
    agent_name: Optional[str] = None
    sql_text: Optional[str] = None
    sql_type: Optional[str] = None
    guard_mode: Optional[str] = None
    check_result: Optional[str] = None
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None
    blocked_rules: Optional[str] = None
    execution_time_ms: Optional[float] = None
    row_count: Optional[int] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    created_at: Optional[str] = None


class AuditStatsResponse(BaseModel):
    """Audit statistics."""

    total: int = 0
    allowed: int = 0
    blocked: int = 0
    blocked_rate: float = 0.0


class TablePermissionRequest(BaseModel):
    """Request to set table-level permissions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    datasource_id: int
    user_id: str
    allowed_tables: List[str]


class TablePermissionResponse(BaseModel):
    """Table permission entry."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    datasource_id: int
    user_id: str
    allowed_tables: List[str]


# ============================================================
# Sensitive Column Masking Schemas
# ============================================================


class SensitiveColumnResponse(BaseModel):
    """Response for a sensitive column config."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    datasource_id: int
    table_name: str
    column_name: str
    sensitive_type: str
    masking_mode: str = "mask"
    confidence: Optional[float] = None
    source: str = "auto"
    enabled: bool = True


class SensitiveColumnCreateRequest(BaseModel):
    """Request to manually add a sensitive column config."""

    table_name: str
    column_name: str
    sensitive_type: str
    masking_mode: str = "mask"


class SensitiveColumnUpdateRequest(BaseModel):
    """Request to update a sensitive column config."""

    sensitive_type: Optional[str] = None
    masking_mode: Optional[str] = None
    enabled: Optional[bool] = None


class SensitiveColumnDetectRequest(BaseModel):
    """Request to trigger auto-detection of sensitive columns."""

    table_names: Optional[List[str]] = None
