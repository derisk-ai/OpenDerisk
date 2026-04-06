"""DB Model for table spec documents."""

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


class TableSpecEntity(Model):
    """Per-table spec document entity.

    Stores detailed information about a single database table including
    column definitions, indexes, sample data, and DDL.
    """

    __tablename__ = "table_spec"

    id = Column(
        Integer, primary_key=True, autoincrement=True, comment="autoincrement id"
    )
    datasource_id = Column(
        Integer, nullable=False, comment="FK to connect_config.id"
    )
    table_name = Column(String(255), nullable=False, comment="Table name")
    table_comment = Column(Text, nullable=True, comment="Table comment/description")
    row_count = Column(Integer, nullable=True, comment="Approximate row count")
    columns_json = Column(
        Text, nullable=False,
        comment="JSON: array of column definitions "
                "(name, type, nullable, default, comment, pk)",
    )
    indexes_json = Column(
        Text, nullable=True,
        comment="JSON: array of index definitions (name, columns, unique)",
    )
    sample_data_json = Column(
        Text, nullable=True,
        comment="JSON: sample rows from the table",
    )
    create_ddl = Column(
        Text, nullable=True, comment="CREATE TABLE DDL statement"
    )
    group_name = Column(
        String(128), nullable=True, comment="Table group name for categorization"
    )
    gmt_created = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(
        DateTime, default=datetime.now, onupdate=datetime.now,
        comment="Record update time",
    )

    __table_args__ = (
        UniqueConstraint(
            "datasource_id", "table_name",
            name="uk_table_spec_ds_table",
        ),
        Index("idx_table_spec_ds", "datasource_id"),
    )


class TableSpecDao(BaseDao):
    """DAO for table spec documents."""

    def from_request(
        self, request: Union[Dict[str, Any], Any]
    ) -> TableSpecEntity:
        if isinstance(request, dict):
            return TableSpecEntity(**request)
        return TableSpecEntity(**request)

    def to_request(self, entity: TableSpecEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
            "table_name": entity.table_name,
        }

    def to_response(self, entity: TableSpecEntity) -> Dict[str, Any]:
        def _parse_json(val):
            if val and isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return None
            return val

        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
            "table_name": entity.table_name,
            "table_comment": entity.table_comment,
            "row_count": entity.row_count,
            "columns": _parse_json(entity.columns_json),
            "indexes": _parse_json(entity.indexes_json),
            "sample_data": _parse_json(entity.sample_data_json),
            "create_ddl": entity.create_ddl,
            "group_name": entity.group_name,
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

    def get_by_datasource_and_table(
        self, datasource_id: int, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get table spec by datasource id and table name."""
        return self.get_one({
            "datasource_id": datasource_id,
            "table_name": table_name,
        })

    def get_all_by_datasource(
        self, datasource_id: int
    ) -> List[Dict[str, Any]]:
        """Get all table specs for a datasource."""
        return self.get_list({"datasource_id": datasource_id})

    def upsert(
        self, datasource_id: int, table_name: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Insert or update a table spec."""
        existing = self.get_by_datasource_and_table(datasource_id, table_name)
        if existing:
            return self.update(
                {"datasource_id": datasource_id, "table_name": table_name},
                data,
            )
        data["datasource_id"] = datasource_id
        data["table_name"] = table_name
        return self.create(data)

    def delete_by_table(self, datasource_id: int, table_name: str) -> None:
        """Delete a specific table spec."""
        self.delete({
            "datasource_id": datasource_id,
            "table_name": table_name,
        })

    def delete_by_datasource_id(self, datasource_id: int) -> None:
        """Delete all table specs for a datasource."""
        specs = self.get_all_by_datasource(datasource_id)
        for spec in specs:
            self.delete({
                "datasource_id": datasource_id,
                "table_name": spec["table_name"],
            })
