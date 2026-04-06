"""DB Model for database spec documents."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class DbSpecEntity(Model):
    """Database-level spec document entity.

    Stores the per-database spec document which is an index of all tables
    with names, summaries, row counts, and grouping information.
    """

    __tablename__ = "db_spec"

    id = Column(
        Integer, primary_key=True, autoincrement=True, comment="autoincrement id"
    )
    datasource_id = Column(
        Integer, nullable=False, comment="FK to connect_config.id"
    )
    db_name = Column(String(255), nullable=False, comment="Database name")
    db_type = Column(String(64), nullable=False, comment="Database type")
    spec_content = Column(
        Text, nullable=False, comment="JSON: table list index with summaries"
    )
    table_count = Column(Integer, nullable=True, comment="Total number of tables")
    group_config = Column(
        Text, nullable=True, comment="JSON: table grouping configuration"
    )
    relations = Column(
        Text, nullable=True, comment="JSON: detected table relationships"
    )
    status = Column(
        String(32),
        nullable=False,
        default="generating",
        comment="Status: ready, generating, failed",
    )
    gmt_created = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(
        DateTime, default=datetime.now, onupdate=datetime.now,
        comment="Record update time",
    )

    __table_args__ = (
        UniqueConstraint("datasource_id", name="uk_db_spec_datasource"),
    )


class DbSpecDao(BaseDao):
    """DAO for database spec documents."""

    def from_request(
        self, request: Union[Dict[str, Any], Any]
    ) -> DbSpecEntity:
        if isinstance(request, dict):
            return DbSpecEntity(**request)
        return DbSpecEntity(**request)

    def to_request(self, entity: DbSpecEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
            "db_name": entity.db_name,
            "db_type": entity.db_type,
        }

    def to_response(self, entity: DbSpecEntity) -> Dict[str, Any]:
        spec_content = entity.spec_content
        if spec_content and isinstance(spec_content, str):
            try:
                spec_content = json.loads(spec_content)
            except (json.JSONDecodeError, TypeError):
                spec_content = []

        group_config = entity.group_config
        if group_config and isinstance(group_config, str):
            try:
                group_config = json.loads(group_config)
            except (json.JSONDecodeError, TypeError):
                group_config = None

        relations = entity.relations
        if relations and isinstance(relations, str):
            try:
                relations = json.loads(relations)
            except (json.JSONDecodeError, TypeError):
                relations = []

        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
            "db_name": entity.db_name,
            "db_type": entity.db_type,
            "spec_content": spec_content,
            "table_count": entity.table_count,
            "group_config": group_config,
            "relations": relations or [],
            "status": entity.status,
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

    def get_by_datasource_id(
        self, datasource_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get db spec by datasource id."""
        return self.get_one({"datasource_id": datasource_id})

    def upsert(self, datasource_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a db spec."""
        existing = self.get_by_datasource_id(datasource_id)
        if existing:
            return self.update(
                {"datasource_id": datasource_id}, data
            )
        data["datasource_id"] = datasource_id
        return self.create(data)

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete db spec by datasource id."""
        existing = self.get_by_datasource_id(datasource_id)
        if existing:
            self.delete({"datasource_id": datasource_id})
