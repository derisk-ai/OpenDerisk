"""DB Model for distributed learning subtasks (one per table)."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class DbLearningSubtaskEntity(Model):
    """Per-table learning subtask entity.

    Each row represents a single table within a learning task.
    Multiple workers (across nodes) atomically claim pending subtasks
    via UPDATE ... WHERE to achieve distributed execution.
    """

    __tablename__ = "db_learning_subtask"

    id = Column(
        Integer, primary_key=True, autoincrement=True, comment="autoincrement id"
    )
    task_id = Column(
        Integer, nullable=False, comment="FK to db_learning_task.id"
    )
    datasource_id = Column(
        Integer, nullable=False, comment="FK to connect_config.id (denormalized)"
    )
    table_name = Column(
        String(255), nullable=False, comment="Table name to learn"
    )
    status = Column(
        String(32), nullable=False, default="pending",
        comment="Status: pending, claimed, completed, failed, cancelled",
    )
    worker_id = Column(
        String(128), nullable=True,
        comment="hostname:pid:thread that claimed this subtask",
    )
    attempt_count = Column(
        Integer, nullable=False, default=0, comment="Number of claim attempts"
    )
    max_attempts = Column(
        Integer, nullable=False, default=3, comment="Max retry attempts"
    )
    error_message = Column(
        Text, nullable=True, comment="Error details on failure"
    )
    claimed_at = Column(
        DateTime, nullable=True, comment="When a worker claimed this subtask"
    )
    completed_at = Column(
        DateTime, nullable=True, comment="When the subtask finished"
    )
    gmt_created = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(
        DateTime, default=datetime.now, onupdate=datetime.now,
        comment="Record update time",
    )

    __table_args__ = (
        UniqueConstraint("task_id", "table_name", name="uk_subtask_task_table"),
        Index("idx_subtask_task_status", "task_id", "status"),
        Index("idx_subtask_ds", "datasource_id"),
    )


class DbLearningSubtaskDao(BaseDao):
    """DAO for distributed learning subtasks."""

    def from_request(
        self, request: Union[Dict[str, Any], Any]
    ) -> DbLearningSubtaskEntity:
        if isinstance(request, dict):
            return DbLearningSubtaskEntity(**request)
        return DbLearningSubtaskEntity(**request)

    def to_request(self, entity: DbLearningSubtaskEntity) -> Dict[str, Any]:
        return {"id": entity.id, "task_id": entity.task_id}

    def to_response(self, entity: DbLearningSubtaskEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "task_id": entity.task_id,
            "datasource_id": entity.datasource_id,
            "table_name": entity.table_name,
            "status": entity.status,
            "worker_id": entity.worker_id,
            "attempt_count": entity.attempt_count,
            "error_message": entity.error_message,
            "claimed_at": (
                entity.claimed_at.strftime("%Y-%m-%d %H:%M:%S")
                if entity.claimed_at else None
            ),
            "completed_at": (
                entity.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                if entity.completed_at else None
            ),
        }

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def bulk_create(
        self, task_id: int, datasource_id: int, table_names: List[str]
    ) -> int:
        """Create subtask rows for all tables in one transaction.

        Returns the number of rows created.
        """
        with self.session() as session:
            for table_name in table_names:
                entity = DbLearningSubtaskEntity(
                    task_id=task_id,
                    datasource_id=datasource_id,
                    table_name=table_name,
                    status="pending",
                    attempt_count=0,
                    max_attempts=3,
                )
                session.add(entity)
        return len(table_names)

    def delete_by_task_id(self, task_id: int) -> None:
        """Delete all subtasks for a learning task."""
        with self.session() as session:
            session.query(DbLearningSubtaskEntity).filter(
                DbLearningSubtaskEntity.task_id == task_id
            ).delete()

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete all subtasks for a datasource."""
        with self.session() as session:
            session.query(DbLearningSubtaskEntity).filter(
                DbLearningSubtaskEntity.datasource_id == datasource_id
            ).delete()

    # ------------------------------------------------------------------
    # Atomic claim (distributed work-stealing)
    # ------------------------------------------------------------------

    def claim_one(
        self, task_id: int, worker_id: str
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim one pending subtask.

        Uses UPDATE ... WHERE id = (SELECT ... LIMIT 1) which is atomic
        on both SQLite (database-level write lock) and MySQL InnoDB
        (row-level lock on the subquery result).

        Returns {"id": ..., "table_name": ...} or None if no work left.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.session() as session:
            result = session.execute(text("""
                UPDATE db_learning_subtask
                SET status = 'claimed',
                    worker_id = :worker_id,
                    attempt_count = attempt_count + 1,
                    claimed_at = :now,
                    gmt_modified = :now
                WHERE id = (
                    SELECT id FROM db_learning_subtask
                    WHERE task_id = :task_id
                      AND status = 'pending'
                      AND attempt_count < max_attempts
                    ORDER BY id
                    LIMIT 1
                )
            """), {
                "worker_id": worker_id,
                "task_id": task_id,
                "now": now,
            })

            if result.rowcount == 0:
                return None

            # Fetch the row we just claimed
            row = session.execute(text("""
                SELECT id, table_name FROM db_learning_subtask
                WHERE task_id = :task_id
                  AND worker_id = :worker_id
                  AND status = 'claimed'
                ORDER BY gmt_modified DESC
                LIMIT 1
            """), {"task_id": task_id, "worker_id": worker_id}).fetchone()

            if row:
                return {"id": row[0], "table_name": row[1]}
            return None

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def mark_completed(self, subtask_id: int) -> None:
        """Mark a subtask as completed."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.session() as session:
            session.execute(text("""
                UPDATE db_learning_subtask
                SET status = 'completed',
                    completed_at = :now,
                    gmt_modified = :now
                WHERE id = :id
            """), {"id": subtask_id, "now": now})

    def mark_failed(self, subtask_id: int, error_message: str) -> None:
        """Mark a subtask as failed with an error message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.session() as session:
            session.execute(text("""
                UPDATE db_learning_subtask
                SET status = 'failed',
                    error_message = :error,
                    completed_at = :now,
                    gmt_modified = :now
                WHERE id = :id
            """), {"id": subtask_id, "error": error_message[:2000], "now": now})

    # ------------------------------------------------------------------
    # Timeout recovery
    # ------------------------------------------------------------------

    def reclaim_stale(
        self, task_id: int, timeout_seconds: int = 300
    ) -> int:
        """Reset subtasks claimed longer than timeout back to pending.

        Returns the number of subtasks reclaimed.
        """
        cutoff = (datetime.now() - timedelta(seconds=timeout_seconds)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.session() as session:
            result = session.execute(text("""
                UPDATE db_learning_subtask
                SET status = 'pending',
                    worker_id = NULL,
                    claimed_at = NULL,
                    gmt_modified = :now
                WHERE task_id = :task_id
                  AND status = 'claimed'
                  AND claimed_at < :cutoff
                  AND attempt_count < max_attempts
            """), {"task_id": task_id, "cutoff": cutoff, "now": now})
            reclaimed = result.rowcount
            if reclaimed > 0:
                logger.info(
                    f"Reclaimed {reclaimed} stale subtasks for task {task_id}"
                )
            return reclaimed

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_task_stats(self, task_id: int) -> Dict[str, int]:
        """Get counts of subtasks grouped by status.

        Returns {"pending": N, "claimed": N, "completed": N, "failed": N, "total": N}
        """
        with self.session(commit=False) as session:
            rows = session.execute(text("""
                SELECT status, COUNT(*) as cnt
                FROM db_learning_subtask
                WHERE task_id = :task_id
                GROUP BY status
            """), {"task_id": task_id}).fetchall()

            stats = {
                "pending": 0, "claimed": 0,
                "completed": 0, "failed": 0, "cancelled": 0, "total": 0,
            }
            for row in rows:
                status_val = row[0]
                count_val = row[1]
                if status_val in stats:
                    stats[status_val] = count_val
                stats["total"] += count_val
            return stats

    def cancel_pending(self, task_id: int) -> int:
        """Mark all pending subtasks as cancelled.

        Returns the number of subtasks cancelled.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.session() as session:
            result = session.execute(text("""
                UPDATE db_learning_subtask
                SET status = 'cancelled',
                    completed_at = :now,
                    gmt_modified = :now
                WHERE task_id = :task_id AND status = 'pending'
            """), {"task_id": task_id, "now": now})
            cancelled = result.rowcount
            if cancelled > 0:
                logger.info(
                    f"Cancelled {cancelled} pending subtasks for task {task_id}"
                )
            return cancelled

    def get_error_summary(self, task_id: int) -> Optional[str]:
        """Build a human-readable error summary from failed subtasks."""
        with self.session(commit=False) as session:
            rows = session.execute(text("""
                SELECT table_name, error_message
                FROM db_learning_subtask
                WHERE task_id = :task_id AND status = 'failed'
                ORDER BY id
            """), {"task_id": task_id}).fetchall()

            if not rows:
                return None

            parts = [f"Failed tables ({len(rows)}):"]
            for row in rows[:20]:
                table_name = row[0]
                error = row[1] or "unknown error"
                parts.append(f"  - {table_name}: {error[:100]}")
            if len(rows) > 20:
                parts.append(f"  ... and {len(rows) - 20} more")
            return "\n".join(parts)
