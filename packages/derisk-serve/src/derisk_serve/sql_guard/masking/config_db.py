"""Sensitive column configuration persistence.

Stores which columns are marked as sensitive (auto-detected or
manually configured) and their masking settings.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class SensitiveColumnEntity(Model):
    """Persistent storage for sensitive column configuration."""

    __tablename__ = "sensitive_column_config"
    __table_args__ = (
        UniqueConstraint(
            "datasource_id", "table_name", "column_name",
            name="uk_sensitive_col",
        ),
        Index("idx_sensitive_col_ds", "datasource_id"),
    )

    id = Column(Integer, primary_key=True, comment="Auto-increment ID")
    datasource_id = Column(Integer, nullable=False, comment="Datasource ID")
    table_name = Column(String(255), nullable=False, comment="Table name")
    column_name = Column(String(255), nullable=False, comment="Column name")
    sensitive_type = Column(
        String(32), nullable=False,
        comment="Sensitive type: phone/email/id_card/bank_card/address/name/password/token/custom",
    )
    masking_mode = Column(
        String(16), nullable=False, default="mask",
        comment="Masking mode: mask/token/none",
    )
    confidence = Column(
        Float, nullable=True,
        comment="Auto-detection confidence (0-1), null if manually configured",
    )
    source = Column(
        String(16), nullable=False, default="auto",
        comment="Config source: auto (detected) / manual (user-configured)",
    )
    enabled = Column(
        Integer, nullable=False, default=1,
        comment="Whether masking is active for this column",
    )
    gmt_created = Column(DateTime, default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SensitiveColumnDao(BaseDao):
    """DAO for sensitive column configuration."""

    def get_by_datasource(
        self, datasource_id: int
    ) -> List[Dict[str, Any]]:
        """Get all sensitive column configs for a datasource."""
        session = self.get_raw_session()
        try:
            entities = (
                session.query(SensitiveColumnEntity)
                .filter(SensitiveColumnEntity.datasource_id == datasource_id)
                .all()
            )
            return [self._to_dict(e) for e in entities]
        finally:
            session.close()

    def get_enabled_by_datasource(
        self, datasource_id: int
    ) -> List[Dict[str, Any]]:
        """Get only enabled sensitive column configs."""
        session = self.get_raw_session()
        try:
            entities = (
                session.query(SensitiveColumnEntity)
                .filter(
                    SensitiveColumnEntity.datasource_id == datasource_id,
                    SensitiveColumnEntity.enabled == 1,
                )
                .all()
            )
            return [self._to_dict(e) for e in entities]
        finally:
            session.close()

    def upsert(
        self,
        datasource_id: int,
        table_name: str,
        column_name: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Insert or update a sensitive column config."""
        session = self.get_raw_session()
        try:
            entity = (
                session.query(SensitiveColumnEntity)
                .filter(
                    SensitiveColumnEntity.datasource_id == datasource_id,
                    SensitiveColumnEntity.table_name == table_name,
                    SensitiveColumnEntity.column_name == column_name,
                )
                .first()
            )
            if entity:
                for key, value in data.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)
                session.commit()
                return self._to_dict(entity)
            else:
                entity = SensitiveColumnEntity(
                    datasource_id=datasource_id,
                    table_name=table_name,
                    column_name=column_name,
                    **data,
                )
                session.add(entity)
                session.commit()
                return self._to_dict(entity)
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_by_datasource(self, datasource_id: int):
        """Delete all configs for a datasource."""
        session = self.get_raw_session()
        try:
            session.query(SensitiveColumnEntity).filter(
                SensitiveColumnEntity.datasource_id == datasource_id
            ).delete()
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def set_enabled(
        self,
        datasource_id: int,
        table_name: str,
        column_name: str,
        enabled: bool,
    ):
        """Enable or disable masking for a column."""
        session = self.get_raw_session()
        try:
            entity = (
                session.query(SensitiveColumnEntity)
                .filter(
                    SensitiveColumnEntity.datasource_id == datasource_id,
                    SensitiveColumnEntity.table_name == table_name,
                    SensitiveColumnEntity.column_name == column_name,
                )
                .first()
            )
            if entity:
                entity.enabled = 1 if enabled else 0
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    @staticmethod
    def _to_dict(entity: SensitiveColumnEntity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "datasource_id": entity.datasource_id,
            "table_name": entity.table_name,
            "column_name": entity.column_name,
            "sensitive_type": entity.sensitive_type,
            "masking_mode": entity.masking_mode,
            "confidence": entity.confidence,
            "source": entity.source,
            "enabled": bool(entity.enabled),
        }
