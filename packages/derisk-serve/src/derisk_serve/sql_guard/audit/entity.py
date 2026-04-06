"""SQL audit log database entity."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from derisk.storage.metadata import Model


class SqlAuditLogEntity(Model):
    """SQL execution audit log entity."""

    __tablename__ = "sql_audit_log"
    __table_args__ = (
        Index("idx_sql_audit_user", "user_id"),
        Index("idx_sql_audit_ds", "datasource_id"),
        Index("idx_sql_audit_time", "created_at"),
        Index("idx_sql_audit_session", "session_id"),
        Index("idx_sql_audit_result", "check_result"),
    )

    id = Column(Integer, primary_key=True, comment="Auto-increment ID")
    user_id = Column(String(255), nullable=True, comment="User identifier")
    session_id = Column(String(255), nullable=True, comment="Session identifier")
    datasource_id = Column(Integer, nullable=True, comment="Datasource ID")
    db_name = Column(String(255), nullable=True, comment="Database name")
    agent_name = Column(String(255), nullable=True, comment="Agent name")
    sql_text = Column(Text, nullable=True, comment="SQL statement (truncated)")
    sql_type = Column(String(32), nullable=True, comment="SQL type (SELECT/INSERT/...)")
    guard_mode = Column(
        String(32), nullable=True, comment="Guard mode (readonly/readwrite/admin)"
    )
    check_result = Column(
        String(16), nullable=True, comment="Check result (allowed/blocked/warning)"
    )
    risk_level = Column(String(16), nullable=True, comment="Risk level")
    risk_score = Column(Integer, nullable=True, comment="Risk score (0-100)")
    blocked_rules = Column(
        Text, nullable=True, comment="Blocked rule names (comma-separated)"
    )
    execution_time_ms = Column(
        Float, nullable=True, comment="SQL execution time in milliseconds"
    )
    row_count = Column(Integer, nullable=True, comment="Result row count")
    error_message = Column(Text, nullable=True, comment="Error message if failed")
    duration_ms = Column(
        Float, nullable=True, default=0.0, comment="Guard check duration in ms"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When the audit log was created",
    )
