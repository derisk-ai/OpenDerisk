"""Risk Dashboard models and DAO.

This module defines the database entities and data access objects for the risk dashboard feature.
"""

import json
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import Column, DateTime, String, Text, Integer, JSON, Date, Boolean

from derisk.storage.metadata import BaseDao, Model

from ..api.schemas import (
    EntityResponse,
    EntityTypeResponse,
    EntityRelationResponse,
    RiskCheckRecordResponse,
    EntitySubscriptionResponse,
    RiskDailySummaryResponse,
    EntityTypeRequest,
    EntityRequest,
    EntityRelationRequest,
    RiskCheckRecordRequest,
    EntitySubscriptionRequest,
    EntitySkillConfigRequest,
    EntitySkillConfigResponse,
)
from ..config import (
    ENTITY_TYPE_TABLE_NAME,
    ENTITY_TABLE_NAME,
    ENTITY_RELATION_TABLE_NAME,
    RISK_CHECK_RECORD_TABLE_NAME,
    ENTITY_SUBSCRIPTION_TABLE_NAME,
    RISK_DAILY_SUMMARY_TABLE_NAME,
    ENTITY_SKILL_CONFIG_TABLE_NAME,
    ServeConfig,
)


class EntityTypeEntity(Model):
    """Database entity for entity types."""

    __tablename__ = ENTITY_TYPE_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Entity type unique identifier")
    name = Column(String(128), nullable=False, comment="Entity type name")
    description = Column(Text, nullable=True, comment="Entity type description")
    default_skill_code = Column(String(255), nullable=True, comment="Default check skill code")
    icon = Column(String(256), nullable=True, comment="Icon name or URL")
    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )

    def __repr__(self):
        return f"EntityTypeEntity(id={self.id}, name='{self.name}')"


class EntityEntity(Model):
    """Database entity for entities."""

    __tablename__ = ENTITY_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Entity unique identifier")
    type_id = Column(String(64), nullable=False, comment="Entity type ID")
    name = Column(String(256), nullable=False, comment="Entity name")
    config = Column(JSON, nullable=True, comment="Entity configuration as JSON")
    extra_skills = Column(JSON, nullable=True, comment="Extra skill list as JSON")
    source = Column(String(32), default="manual", comment="Entity source (manual/auto)")
    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="Record update time",
    )

    def __repr__(self):
        return f"EntityEntity(id={self.id}, name='{self.name}', type_id='{self.type_id}')"


class EntityRelationEntity(Model):
    """Database entity for entity relations."""

    __tablename__ = ENTITY_RELATION_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Relation unique identifier")
    source_entity_id = Column(String(64), nullable=False, comment="Source entity ID")
    target_entity_id = Column(String(64), nullable=False, comment="Target entity ID")
    relation_type = Column(String(64), nullable=False, comment="Relation type (depends_on/contains/impacts)")
    strength = Column(String(16), default="weak", comment="Relation strength (strong/weak)")
    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )

    def __repr__(self):
        return f"EntityRelationEntity(id={self.id}, source={self.source_entity_id}, target={self.target_entity_id})"


class RiskCheckRecordEntity(Model):
    """Database entity for risk check records."""

    __tablename__ = RISK_CHECK_RECORD_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Record unique identifier")
    entity_id = Column(String(64), nullable=False, comment="Entity ID")
    conv_id = Column(String(64), nullable=True, comment="Conversation session ID")
    risk_level = Column(String(16), nullable=False, comment="Risk level (green/blue/yellow/red)")
    summary = Column(Text, nullable=True, comment="Check summary")
    details = Column(JSON, nullable=True, comment="Check details as JSON")
    suggestions = Column(JSON, nullable=True, comment="Suggestions as JSON")
    checked_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Check time",
    )

    def __repr__(self):
        return f"RiskCheckRecordEntity(id={self.id}, entity_id={self.entity_id}, risk_level={self.risk_level})"


class EntitySubscriptionEntity(Model):
    """Database entity for user subscriptions."""

    __tablename__ = ENTITY_SUBSCRIPTION_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Subscription unique identifier")
    user_id = Column(String(64), nullable=False, comment="User ID")
    entity_id = Column(String(64), nullable=False, comment="Entity ID")
    notify_level = Column(String(32), default="all", comment="Notify level (all/yellow_plus/red_only)")
    notify_channels = Column(JSON, nullable=True, comment="Notify channels as JSON")
    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )

    def __repr__(self):
        return f"EntitySubscriptionEntity(id={self.id}, user_id={self.user_id}, entity_id={self.entity_id})"


class RiskDailySummaryEntity(Model):
    """Database entity for risk daily summary."""

    __tablename__ = RISK_DAILY_SUMMARY_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Summary unique identifier")
    entity_id = Column(String(64), nullable=False, comment="Entity ID")
    date = Column(Date, nullable=False, comment="Summary date")
    risk_level = Column(String(16), nullable=False, comment="Risk level (green/blue/yellow/red)")
    check_count = Column(Integer, default=0, comment="Check count for the day")
    issue_count = Column(Integer, default=0, comment="Issue count for the day")
    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )

    def __repr__(self):
        return f"RiskDailySummaryEntity(id={self.id}, entity_id={self.entity_id}, date={self.date})"


class EntitySkillConfigEntity(Model):
    """Database entity for entity skill configuration."""

    __tablename__ = ENTITY_SKILL_CONFIG_TABLE_NAME

    id = Column(String(64), primary_key=True, comment="Skill config unique identifier")
    entity_id = Column(String(64), nullable=False, comment="Entity ID")
    skill_code = Column(String(255), nullable=False, comment="Skill code")
    skill_name = Column(String(255), nullable=True, comment="Skill name (redundant storage for display)")
    skill_type = Column(String(32), nullable=False, default="custom", comment="Skill type (default/custom)")
    enabled = Column(Boolean, default=True, nullable=False, comment="Whether the skill is enabled")
    check_params = Column(JSON, nullable=True, comment="Check parameters as JSON")
    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="Record creation time",
    )
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="Record update time",
    )

    def __repr__(self):
        return f"EntitySkillConfigEntity(id={self.id}, entity_id={self.entity_id}, skill_code={self.skill_code})"


class EntityTypeDao(BaseDao[EntityTypeEntity, EntityTypeRequest, EntityTypeResponse]):
    """Data Access Object for entity types."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[EntityTypeRequest, Dict[str, Any]]) -> EntityTypeEntity:
        """Convert a request to an entity.

        Args:
            request: The request object or dictionary.

        Returns:
            An EntityTypeEntity instance.
        """
        if isinstance(request, dict):
            request = EntityTypeRequest(**request)

        entity = EntityTypeEntity()
        entity.id = request.id or uuid.uuid4().hex[:16]
        entity.name = request.name
        entity.description = request.description
        entity.default_skill_code = request.default_skill_code
        entity.icon = request.icon
        entity.created_at = datetime.now()

        return entity

    def to_request(self, entity: EntityTypeEntity) -> EntityTypeRequest:
        """Convert an entity to a request.

        Args:
            entity: The entity to convert.

        Returns:
            An EntityTypeRequest instance.
        """
        return EntityTypeRequest(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            default_skill_code=entity.default_skill_code,
            icon=entity.icon,
        )

    def to_response(self, entity: EntityTypeEntity) -> EntityTypeResponse:
        """Convert an entity to a response.

        Args:
            entity: The entity to convert.

        Returns:
            An EntityTypeResponse instance.
        """
        return EntityTypeResponse(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            default_skill_code=entity.default_skill_code,
            icon=entity.icon,
            created_at=entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else None,
        )


class EntityDao(BaseDao[EntityEntity, EntityRequest, EntityResponse]):
    """Data Access Object for entities."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[EntityRequest, Dict[str, Any]]) -> EntityEntity:
        """Convert a request to an entity.

        Args:
            request: The request object or dictionary.

        Returns:
            An EntityEntity instance.
        """
        if isinstance(request, dict):
            request = EntityRequest(**request)

        entity = EntityEntity()
        entity.id = request.id or uuid.uuid4().hex[:16]
        entity.type_id = request.type_id
        entity.name = request.name
        entity.config = request.config
        entity.extra_skills = request.extra_skills
        entity.source = request.source or "manual"
        entity.created_at = datetime.now()
        entity.updated_at = datetime.now()

        return entity

    def to_request(self, entity: EntityEntity) -> EntityRequest:
        """Convert an entity to a request.

        Args:
            entity: The entity to convert.

        Returns:
            An EntityRequest instance.
        """
        return EntityRequest(
            id=entity.id,
            type_id=entity.type_id,
            name=entity.name,
            config=entity.config,
            extra_skills=entity.extra_skills,
            source=entity.source,
        )

    def to_response(self, entity: EntityEntity) -> EntityResponse:
        """Convert an entity to a response.

        Args:
            entity: The entity to convert.

        Returns:
            An EntityResponse instance.
        """
        return EntityResponse(
            id=entity.id,
            type_id=entity.type_id,
            name=entity.name,
            config=entity.config,
            extra_skills=entity.extra_skills,
            source=entity.source,
            created_at=entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else None,
            updated_at=entity.updated_at.strftime("%Y-%m-%d %H:%M:%S") if entity.updated_at else None,
        )

    def get_entities_by_type(self, type_id: str) -> List[EntityEntity]:
        """Get all entities of a specific type.

        Args:
            type_id: The entity type ID.

        Returns:
            List of entity entities.
        """
        with self.session(commit=False) as session:
            entities = session.query(EntityEntity).filter(EntityEntity.type_id == type_id).all()
            for entity in entities:
                session.expunge(entity)
            return entities


class EntityRelationDao(BaseDao[EntityRelationEntity, EntityRelationRequest, EntityRelationResponse]):
    """Data Access Object for entity relations."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[EntityRelationRequest, Dict[str, Any]]) -> EntityRelationEntity:
        """Convert a request to an entity."""
        if isinstance(request, dict):
            request = EntityRelationRequest(**request)

        entity = EntityRelationEntity()
        entity.id = request.id or uuid.uuid4().hex[:16]
        entity.source_entity_id = request.source_entity_id
        entity.target_entity_id = request.target_entity_id
        entity.relation_type = request.relation_type
        entity.strength = request.strength or "weak"
        entity.created_at = datetime.now()

        return entity

    def to_request(self, entity: EntityRelationEntity) -> EntityRelationRequest:
        """Convert an entity to a request."""
        return EntityRelationRequest(
            id=entity.id,
            source_entity_id=entity.source_entity_id,
            target_entity_id=entity.target_entity_id,
            relation_type=entity.relation_type,
            strength=entity.strength,
        )

    def to_response(self, entity: EntityRelationEntity) -> EntityRelationResponse:
        """Convert an entity to a response."""
        return EntityRelationResponse(
            id=entity.id,
            source_entity_id=entity.source_entity_id,
            target_entity_id=entity.target_entity_id,
            relation_type=entity.relation_type,
            strength=entity.strength,
            created_at=entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else None,
        )


class RiskCheckRecordDao(BaseDao[RiskCheckRecordEntity, RiskCheckRecordRequest, RiskCheckRecordResponse]):
    """Data Access Object for risk check records."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[RiskCheckRecordRequest, Dict[str, Any]]) -> RiskCheckRecordEntity:
        """Convert a request to an entity."""
        if isinstance(request, dict):
            request = RiskCheckRecordRequest(**request)

        entity = RiskCheckRecordEntity()
        entity.id = request.id or uuid.uuid4().hex[:16]
        entity.entity_id = request.entity_id
        entity.conv_id = request.conv_id
        entity.risk_level = request.risk_level
        entity.summary = request.summary
        entity.details = request.details
        entity.suggestions = request.suggestions
        entity.checked_at = datetime.now()

        return entity

    def to_request(self, entity: RiskCheckRecordEntity) -> RiskCheckRecordRequest:
        """Convert an entity to a request."""
        return RiskCheckRecordRequest(
            id=entity.id,
            entity_id=entity.entity_id,
            conv_id=entity.conv_id,
            risk_level=entity.risk_level,
            summary=entity.summary,
            details=entity.details,
            suggestions=entity.suggestions,
        )

    def to_response(self, entity: RiskCheckRecordEntity) -> RiskCheckRecordResponse:
        """Convert an entity to a response."""
        return RiskCheckRecordResponse(
            id=entity.id,
            entity_id=entity.entity_id,
            conv_id=entity.conv_id,
            risk_level=entity.risk_level,
            summary=entity.summary,
            details=entity.details,
            suggestions=entity.suggestions,
            checked_at=entity.checked_at.strftime("%Y-%m-%d %H:%M:%S") if entity.checked_at else None,
        )

    def get_latest_record(self, entity_id: str) -> Optional[RiskCheckRecordEntity]:
        """Get the latest check record for an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            The latest check record or None.
        """
        with self.session(commit=False) as session:
            record = session.query(RiskCheckRecordEntity).filter(
                RiskCheckRecordEntity.entity_id == entity_id
            ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()
            if record:
                session.expunge(record)
            return record

    def get_records_by_entity(self, entity_id: str, limit: int = 10) -> List[RiskCheckRecordEntity]:
        """Get check records for an entity.

        Args:
            entity_id: The entity ID.
            limit: Maximum number of records to return.

        Returns:
            List of check records.
        """
        with self.session(commit=False) as session:
            records = session.query(RiskCheckRecordEntity).filter(
                RiskCheckRecordEntity.entity_id == entity_id
            ).order_by(RiskCheckRecordEntity.checked_at.desc()).limit(limit).all()
            for record in records:
                session.expunge(record)
            return records


class EntitySubscriptionDao(BaseDao[EntitySubscriptionEntity, EntitySubscriptionRequest, EntitySubscriptionResponse]):
    """Data Access Object for entity subscriptions."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[EntitySubscriptionRequest, Dict[str, Any]]) -> EntitySubscriptionEntity:
        """Convert a request to an entity."""
        if isinstance(request, dict):
            request = EntitySubscriptionRequest(**request)

        entity = EntitySubscriptionEntity()
        entity.id = request.id or uuid.uuid4().hex[:16]
        entity.user_id = request.user_id
        entity.entity_id = request.entity_id
        entity.notify_level = request.notify_level or "all"
        entity.notify_channels = request.notify_channels
        entity.created_at = datetime.now()

        return entity

    def to_request(self, entity: EntitySubscriptionEntity) -> EntitySubscriptionRequest:
        """Convert an entity to a request."""
        return EntitySubscriptionRequest(
            id=entity.id,
            user_id=entity.user_id,
            entity_id=entity.entity_id,
            notify_level=entity.notify_level,
            notify_channels=entity.notify_channels,
        )

    def to_response(self, entity: EntitySubscriptionEntity) -> EntitySubscriptionResponse:
        """Convert an entity to a response."""
        return EntitySubscriptionResponse(
            id=entity.id,
            user_id=entity.user_id,
            entity_id=entity.entity_id,
            notify_level=entity.notify_level,
            notify_channels=entity.notify_channels,
            created_at=entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else None,
        )

    def get_user_subscriptions(self, user_id: str) -> List[EntitySubscriptionEntity]:
        """Get all subscriptions for a user.

        Args:
            user_id: The user ID.

        Returns:
            List of subscriptions.
        """
        with self.session(commit=False) as session:
            subscriptions = session.query(EntitySubscriptionEntity).filter(
                EntitySubscriptionEntity.user_id == user_id
            ).all()
            for sub in subscriptions:
                session.expunge(sub)
            return subscriptions


class RiskDailySummaryDao(BaseDao[RiskDailySummaryEntity, Dict[str, Any], RiskDailySummaryResponse]):
    """Data Access Object for risk daily summary."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[Dict[str, Any], Dict[str, Any]]) -> RiskDailySummaryEntity:
        """Convert a request to an entity."""
        entity = RiskDailySummaryEntity()
        entity.id = request.get("id") or uuid.uuid4().hex[:16]
        entity.entity_id = request.get("entity_id")
        entity.date = request.get("date")
        entity.risk_level = request.get("risk_level")
        entity.check_count = request.get("check_count", 0)
        entity.issue_count = request.get("issue_count", 0)
        entity.created_at = datetime.now()

        return entity

    def to_request(self, entity: RiskDailySummaryEntity) -> Dict[str, Any]:
        """Convert an entity to a request."""
        return {
            "id": entity.id,
            "entity_id": entity.entity_id,
            "date": entity.date.isoformat() if entity.date else None,
            "risk_level": entity.risk_level,
            "check_count": entity.check_count,
            "issue_count": entity.issue_count,
        }

    def to_response(self, entity: RiskDailySummaryEntity) -> RiskDailySummaryResponse:
        """Convert an entity to a response."""
        return RiskDailySummaryResponse(
            id=entity.id,
            entity_id=entity.entity_id,
            date=entity.date.isoformat() if entity.date else None,
            risk_level=entity.risk_level,
            check_count=entity.check_count,
            issue_count=entity.issue_count,
            created_at=entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else None,
        )

    def get_summaries_by_date_range(self, entity_id: str, start_date: date, end_date: date) -> List[RiskDailySummaryEntity]:
        """Get daily summaries for an entity within a date range.

        Args:
            entity_id: The entity ID.
            start_date: Start date.
            end_date: End date.

        Returns:
            List of daily summaries.
        """
        with self.session(commit=False) as session:
            summaries = session.query(RiskDailySummaryEntity).filter(
                RiskDailySummaryEntity.entity_id == entity_id,
                RiskDailySummaryEntity.date >= start_date,
                RiskDailySummaryEntity.date <= end_date,
            ).order_by(RiskDailySummaryEntity.date).all()
            for summary in summaries:
                session.expunge(summary)
            return summaries


class EntitySkillConfigDao(BaseDao[EntitySkillConfigEntity, EntitySkillConfigRequest, EntitySkillConfigResponse]):
    """Data Access Object for entity skill configuration."""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[EntitySkillConfigRequest, Dict[str, Any]]) -> EntitySkillConfigEntity:
        """Convert a request to an entity."""
        if isinstance(request, dict):
            request = EntitySkillConfigRequest(**request)

        entity = EntitySkillConfigEntity()
        entity.id = request.id or uuid.uuid4().hex[:16]
        entity.entity_id = request.entity_id
        entity.skill_code = request.skill_code
        entity.skill_name = request.skill_name
        entity.skill_type = request.skill_type or "custom"
        entity.enabled = request.enabled if request.enabled is not None else True
        entity.check_params = request.check_params
        entity.created_at = datetime.now()
        entity.updated_at = datetime.now()

        return entity

    def to_request(self, entity: EntitySkillConfigEntity) -> EntitySkillConfigRequest:
        """Convert an entity to a request."""
        return EntitySkillConfigRequest(
            id=entity.id,
            entity_id=entity.entity_id,
            skill_code=entity.skill_code,
            skill_name=entity.skill_name,
            skill_type=entity.skill_type,
            enabled=entity.enabled,
            check_params=entity.check_params,
        )

    def to_response(self, entity: EntitySkillConfigEntity) -> EntitySkillConfigResponse:
        """Convert an entity to a response."""
        return EntitySkillConfigResponse(
            id=entity.id,
            entity_id=entity.entity_id,
            skill_code=entity.skill_code,
            skill_name=entity.skill_name,
            skill_type=entity.skill_type,
            enabled=entity.enabled,
            check_params=entity.check_params,
            created_at=entity.created_at.strftime("%Y-%m-%d %H:%M:%S") if entity.created_at else None,
            updated_at=entity.updated_at.strftime("%Y-%m-%d %H:%M:%S") if entity.updated_at else None,
        )

    def get_skills_by_entity(self, entity_id: str) -> List[EntitySkillConfigEntity]:
        """Get all skill configurations for an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            List of skill configurations.
        """
        with self.session(commit=False) as session:
            skills = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.entity_id == entity_id
            ).order_by(EntitySkillConfigEntity.skill_type, EntitySkillConfigEntity.created_at).all()
            for skill in skills:
                session.expunge(skill)
            return skills

    def get_skill_by_entity_and_code(self, entity_id: str, skill_code: str) -> Optional[EntitySkillConfigEntity]:
        """Get a skill configuration by entity and skill code.

        Args:
            entity_id: The entity ID.
            skill_code: The skill code.

        Returns:
            The skill configuration or None.
        """
        with self.session(commit=False) as session:
            skill = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.entity_id == entity_id,
                EntitySkillConfigEntity.skill_code == skill_code,
            ).first()
            if skill:
                session.expunge(skill)
            return skill