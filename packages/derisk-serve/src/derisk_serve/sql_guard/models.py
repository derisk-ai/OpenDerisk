"""SQL Guard models and enumerations."""

from enum import Enum
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict


class SQLGuardMode(str, Enum):
    """SQL execution permission mode."""

    READONLY = "readonly"
    READWRITE = "readwrite"
    ADMIN = "admin"


class RiskLevel(str, Enum):
    """Risk level classification."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SQLType(str, Enum):
    """Parsed SQL statement type."""

    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    DDL = "DDL"
    DCL = "DCL"
    SHOW = "SHOW"
    DESCRIBE = "DESCRIBE"
    EXPLAIN = "EXPLAIN"
    WITH = "WITH"
    UNKNOWN = "UNKNOWN"


class RuleResult(BaseModel):
    """Result from a single rule check."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    passed: bool
    rule_name: str
    message: str = ""
    risk_score: int = 0
    risk_level: str = RiskLevel.SAFE.value


class SQLCheckResult(BaseModel):
    """Result of SQL Guard check."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    allowed: bool
    risk_level: str = RiskLevel.SAFE.value
    risk_score: int = 0
    blocked_rules: List[str] = []
    warnings: List[str] = []
    rewritten_sql: Optional[str] = None
    sql_type: str = SQLType.UNKNOWN.value
    details: List[RuleResult] = []


class ParsedSQL(BaseModel):
    """Parsed SQL information for rule evaluation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    raw_sql: str
    normalized_sql: str = ""
    sql_type: str = SQLType.UNKNOWN.value
    tables: List[str] = []
    columns: List[str] = []
    has_where: bool = False
    has_limit: bool = False
    limit_value: Optional[int] = None


class SQLCheckContext(BaseModel):
    """Context passed to rules during check."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: Optional[str] = None
    datasource_id: Optional[int] = None
    db_name: Optional[str] = None
    mode: str = SQLGuardMode.READONLY.value
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    extra: Dict[str, Any] = {}
