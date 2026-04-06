"""SQL audit log DAO."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func as sa_func

from derisk.storage.metadata import BaseDao

from .entity import SqlAuditLogEntity

logger = logging.getLogger(__name__)


class SqlAuditLogDao(BaseDao):
    """Data access object for SQL audit logs."""

    def create(self, data: Dict[str, Any]) -> int:
        """Create an audit log record.

        Args:
             Dict with entity field values.

        Returns:
            The created record ID.
        """
        entity = SqlAuditLogEntity(**data)
        session = self.get_raw_session()
        try:
            session.add(entity)
            session.commit()
            return entity.id
        except Exception as e:
            session.rollback()
            logger.warning(f"Failed to create SQL audit log: {e}")
            return -1
        finally:
            session.close()

    def update_execution(
        self,
        log_id: int,
        execution_time_ms: Optional[float] = None,
        row_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Update execution result after SQL runs."""
        session = self.get_raw_session()
        try:
            entity = (
                session.query(SqlAuditLogEntity)
                .filter(SqlAuditLogEntity.id == log_id)
                .first()
            )
            if entity:
                if execution_time_ms is not None:
                    entity.execution_time_ms = execution_time_ms
                if row_count is not None:
                    entity.row_count = row_count
                if error_message is not None:
                    entity.error_message = error_message[:2000]
                session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Failed to update SQL audit log: {e}")
        finally:
            session.close()

    def list(
        self,
        user_id: Optional[str] = None,
        datasource_id: Optional[int] = None,
        session_id: Optional[str] = None,
        check_result: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[Dict[str, Any]]:
        """Query audit logs with filters."""
        session = self.get_raw_session()
        try:
            query = session.query(SqlAuditLogEntity)

            if user_id:
                query = query.filter(SqlAuditLogEntity.user_id == user_id)
            if datasource_id:
                query = query.filter(
                    SqlAuditLogEntity.datasource_id == datasource_id
                )
            if session_id:
                query = query.filter(SqlAuditLogEntity.session_id == session_id)
            if check_result:
                query = query.filter(SqlAuditLogEntity.check_result == check_result)
            if risk_level:
                query = query.filter(SqlAuditLogEntity.risk_level == risk_level)
            if start_time:
                query = query.filter(SqlAuditLogEntity.created_at >= start_time)
            if end_time:
                query = query.filter(SqlAuditLogEntity.created_at <= end_time)

            entities = (
                query.order_by(desc(SqlAuditLogEntity.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._to_dict(e) for e in entities]
        finally:
            session.close()

    def get_stats(
        self,
        datasource_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get audit statistics."""
        session = self.get_raw_session()
        try:
            query = session.query(SqlAuditLogEntity)
            if datasource_id:
                query = query.filter(
                    SqlAuditLogEntity.datasource_id == datasource_id
                )
            if start_time:
                query = query.filter(SqlAuditLogEntity.created_at >= start_time)
            if end_time:
                query = query.filter(SqlAuditLogEntity.created_at <= end_time)

            total = query.count()
            blocked = query.filter(
                SqlAuditLogEntity.check_result == "blocked"
            ).count()
            allowed = query.filter(
                SqlAuditLogEntity.check_result == "allowed"
            ).count()

            return {
                "total": total,
                "allowed": allowed,
                "blocked": blocked,
                "blocked_rate": round(blocked / total * 100, 2) if total > 0 else 0,
            }
        finally:
            session.close()

    def delete_old_logs(self, days: int = 30) -> int:
        """Delete logs older than the specified number of days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        session = self.get_raw_session()
        try:
            deleted = (
                session.query(SqlAuditLogEntity)
                .filter(SqlAuditLogEntity.created_at < cutoff)
                .delete()
            )
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            return 0
        finally:
            session.close()

    @staticmethod
    def _to_dict(entity: SqlAuditLogEntity) -> Dict[str, Any]:
        """Convert entity to dict."""
        return {
            "id": entity.id,
            "user_id": entity.user_id,
            "session_id": entity.session_id,
            "datasource_id": entity.datasource_id,
            "db_name": entity.db_name,
            "agent_name": entity.agent_name,
            "sql_text": entity.sql_text,
            "sql_type": entity.sql_type,
            "guard_mode": entity.guard_mode,
            "check_result": entity.check_result,
            "risk_level": entity.risk_level,
            "risk_score": entity.risk_score,
            "blocked_rules": entity.blocked_rules,
            "execution_time_ms": entity.execution_time_ms,
            "row_count": entity.row_count,
            "error_message": entity.error_message,
            "duration_ms": entity.duration_ms,
            "created_at": (
                entity.created_at.isoformat() if entity.created_at else None
            ),
        }
