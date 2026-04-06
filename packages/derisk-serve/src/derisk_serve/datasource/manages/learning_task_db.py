"""DB Model for database learning tasks."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class DbLearningTaskEntity(Model):
    """Database learning task entity.

    Tracks the progress of schema learning tasks for a datasource.
    """

    __tablename__ = "db_learning_task"

    id = Column(
        Integer, primary_key=True, autoincrement=True, comment="autoincrement id"
    )
    datasource_id = Column(
        Integer, nullable=False, comment="FK to connect_config.id"
    )
    task_type = Column(
        String(32), nullable=False, default="full_learn",
        comment="Task type: full_learn, single_table",
    )
    status = Column(
        String(32), nullable=False, default="pending",
        comment="Status: pending, running, completed, failed",
    )
    progress = Column(
        Integer, nullable=False, default=0, comment="Progress 0-100"
    )
    total_tables = Column(
        Integer, nullable=True, comment="Total number of tables to process"
    )
    processed_tables = Column(
        Integer, nullable=False, default=0, comment="Number of tables processed"
    )
    error_message = Column(
        Text, nullable=True, comment="Error message if task failed"
    )
    trigger_type = Column(
        String(32), nullable=False, default="manual",
        comment="Trigger type: manual, auto_on_create, scheduled",
    )
    gmt_created = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(
        DateTime, default=datetime.now, onupdate=datetime.now,
        comment="Record update time",
    )

    __table_args__ = (
        Index("idx_learning_task_ds", "datasource_id"),
        Index("idx_learning_task_status", "status"),
    )


class DbLearningTaskDao(BaseDao):
    """DAO for database learning tasks."""

    def from_request(
        self, request: Union[Dict[str, Any], Any]
    ) -> DbLearningTaskEntity:
        if isinstance(request, dict):
            return DbLearningTaskEntity(**request)
        return DbLearningTaskEntity(**request)

    def to_request(self, entity: DbLearningTaskEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
        }

    def to_response(self, entity: DbLearningTaskEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
            "task_type": entity.task_type,
            "status": entity.status,
            "progress": entity.progress,
            "total_tables": entity.total_tables,
            "processed_tables": entity.processed_tables,
            "error_message": entity.error_message,
            "trigger_type": entity.trigger_type,
            "gmt_created": (
                entity.gmt_created.strftime("%Y-%m-%d %H:%M:%S")
                if entity.gmt_created
                else None
            ),
            "gmt_modified": (
                entity.gmt_modified.strftime("%Y-%m-%d %H:%M:%S")
                if entity.gmt_modified
                else None
            ),
        }

    def get_latest_by_datasource(
        self, datasource_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the latest learning task for a datasource."""
        with self.session(commit=False) as session:
            result = (
                session.query(DbLearningTaskEntity)
                .filter(DbLearningTaskEntity.datasource_id == datasource_id)
                .order_by(DbLearningTaskEntity.id.desc())
                .first()
            )
            if result:
                return self.to_response(result)
            return None

    def get_running_by_datasource(
        self, datasource_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get a running learning task for a datasource if one exists."""
        return self.get_one({
            "datasource_id": datasource_id,
            "status": "running",
        })

    def update_progress(
        self,
        task_id: int,
        processed_tables: int,
        total_tables: int,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update learning task progress."""
        progress = (
            int(processed_tables / total_tables * 100) if total_tables > 0 else 0
        )
        update_data = {
            "processed_tables": processed_tables,
            "total_tables": total_tables,
            "progress": progress,
        }
        if status:
            update_data["status"] = status
        if error_message is not None:
            update_data["error_message"] = error_message
        self.update({"id": task_id}, update_data)

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete all learning tasks for a datasource."""
        tasks = self.get_list({"datasource_id": datasource_id})
        for task in tasks:
            self.delete({"id": task["id"]})
