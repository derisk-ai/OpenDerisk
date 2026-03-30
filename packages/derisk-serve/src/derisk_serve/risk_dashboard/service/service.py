"""Risk Dashboard service implementation.

This module provides the main service for risk dashboard management.
"""

import logging
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from derisk.component import SystemApp
from derisk.storage.metadata._base_dao import REQ, RES
from derisk_serve.core import BaseService

from ..api.schemas import (
    EntityTypeRequest,
    EntityTypeResponse,
    EntityRequest,
    EntityResponse,
    EntityRelationRequest,
    EntityRelationResponse,
    RiskCheckRecordResponse,
    EntitySubscriptionRequest,
    EntitySubscriptionResponse,
    RiskSummaryResponse,
    HeatmapDataPoint,
    EntitySkillConfigRequest,
    EntitySkillConfigResponse,
    SkillResponse,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import (
    EntityTypeEntity,
    EntityEntity,
    EntityRelationEntity,
    RiskCheckRecordEntity,
    EntitySubscriptionEntity,
    RiskDailySummaryEntity,
    EntitySkillConfigEntity,
    EntityTypeDao,
    EntityDao,
    EntityRelationDao,
    RiskCheckRecordDao,
    EntitySubscriptionDao,
    RiskDailySummaryDao,
    EntitySkillConfigDao,
)

logger = logging.getLogger(__name__)


class Service(BaseService[EntityTypeEntity, EntityTypeRequest, EntityTypeResponse]):
    """Risk dashboard service.

    This service manages entity types, entities, relations, check records,
    subscriptions, and provides risk summary and heatmap data.
    """

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
    ):
        """Initialize the risk dashboard service.

        Args:
            system_app: The system application instance.
            config: The service configuration.
        """
        self._config = config
        self._entity_type_dao: Optional[EntityTypeDao] = None
        self._entity_dao: Optional[EntityDao] = None
        self._relation_dao: Optional[EntityRelationDao] = None
        self._check_record_dao: Optional[RiskCheckRecordDao] = None
        self._subscription_dao: Optional[EntitySubscriptionDao] = None
        self._daily_summary_dao: Optional[RiskDailySummaryDao] = None
        self._skill_config_dao: Optional[EntitySkillConfigDao] = None

        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service.

        Args:
            system_app: The system application instance.
        """
        super().init_app(system_app)
        self._entity_type_dao = EntityTypeDao(self._config)
        self._entity_dao = EntityDao(self._config)
        self._relation_dao = EntityRelationDao(self._config)
        self._check_record_dao = RiskCheckRecordDao(self._config)
        self._subscription_dao = EntitySubscriptionDao(self._config)
        self._daily_summary_dao = RiskDailySummaryDao(self._config)
        self._skill_config_dao = EntitySkillConfigDao(self._config)

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._config

    @property
    def dao(self) -> "EntityDao":
        """Returns the primary DAO (EntityDao)."""
        return self._entity_dao

    def create(self, request: REQ) -> RES:
        """Create a new entity type (use create_entity_type instead)."""
        raise NotImplementedError("Use create_entity_type instead")

    # ============ Entity Type Methods ============

    def list_entity_types(self) -> List[EntityTypeResponse]:
        """List all entity types.

        Returns:
            List of entity type responses.
        """
        with self._entity_type_dao.session() as session:
            entities = session.query(EntityTypeEntity).all()
            responses = []
            for entity in entities:
                response = self._entity_type_dao.to_response(entity)
                # Get entity count
                count = session.query(EntityEntity).filter(
                    EntityEntity.type_id == entity.id
                ).count()
                response.entity_count = count
                responses.append(response)
            return responses

    def get_entity_type(self, type_id: str) -> Optional[EntityTypeResponse]:
        """Get an entity type by ID.

        Args:
            type_id: The entity type ID.

        Returns:
            The entity type response or None.
        """
        with self._entity_type_dao.session() as session:
            entity = session.query(EntityTypeEntity).filter(
                EntityTypeEntity.id == type_id
            ).first()
            if entity:
                response = self._entity_type_dao.to_response(entity)
                count = session.query(EntityEntity).filter(
                    EntityEntity.type_id == type_id
                ).count()
                response.entity_count = count
                return response
            return None

    def create_entity_type(self, request: EntityTypeRequest) -> EntityTypeResponse:
        """Create a new entity type.

        Args:
            request: The entity type creation request.

        Returns:
            The created entity type response.
        """
        entity = self._entity_type_dao.from_request(request)
        with self._entity_type_dao.session() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return self._entity_type_dao.to_response(entity)

    def delete_entity_type(self, type_id: str) -> bool:
        """Delete an entity type.

        Args:
            type_id: The entity type ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._entity_type_dao.session() as session:
            result = session.query(EntityTypeEntity).filter(
                EntityTypeEntity.id == type_id
            ).delete()
            session.commit()
            return result > 0

    # ============ Entity Methods ============

    def list_entities(
        self,
        type_id: Optional[str] = None,
        risk_level: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[EntityResponse]:
        """List entities with optional filters.

        Args:
            type_id: Filter by entity type.
            risk_level: Filter by risk level.
            user_id: Filter by subscribed user.

        Returns:
            List of entity responses.
        """
        with self._entity_dao.session() as session:
            query = session.query(EntityEntity)

            if type_id:
                query = query.filter(EntityEntity.type_id == type_id)

            # If user_id is provided, filter by subscribed entities
            if user_id:
                sub_query = session.query(EntitySubscriptionEntity.entity_id).filter(
                    EntitySubscriptionEntity.user_id == user_id
                )
                query = query.filter(EntityEntity.id.in_(sub_query))

            entities = query.all()
            responses = []

            for entity in entities:
                response = self._entity_dao.to_response(entity)

                # Get type name
                type_entity = session.query(EntityTypeEntity).filter(
                    EntityTypeEntity.id == entity.type_id
                ).first()
                if type_entity:
                    response.type_name = type_entity.name

                # Get latest check record
                latest_record = session.query(RiskCheckRecordEntity).filter(
                    RiskCheckRecordEntity.entity_id == entity.id
                ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()

                if latest_record:
                    response.risk_level = latest_record.risk_level
                    response.risk_level_text = self._get_risk_level_text(latest_record.risk_level)
                    response.last_check_at = latest_record.checked_at.strftime("%Y-%m-%d %H:%M:%S") if latest_record.checked_at else None
                    response.summary = latest_record.summary

                # Check if user subscribed
                if user_id:
                    subscription = session.query(EntitySubscriptionEntity).filter(
                        EntitySubscriptionEntity.user_id == user_id,
                        EntitySubscriptionEntity.entity_id == entity.id,
                    ).first()
                    response.subscribed = subscription is not None

                # Filter by risk level if specified
                if risk_level:
                    if response.risk_level != risk_level:
                        continue

                responses.append(response)

            return responses

    def get_entity(self, entity_id: str, user_id: Optional[str] = None) -> Optional[EntityResponse]:
        """Get an entity by ID.

        Args:
            entity_id: The entity ID.
            user_id: Optional user ID for subscription check.

        Returns:
            The entity response or None.
        """
        with self._entity_dao.session() as session:
            entity = session.query(EntityEntity).filter(
                EntityEntity.id == entity_id
            ).first()

            if not entity:
                return None

            response = self._entity_dao.to_response(entity)

            # Get type name
            type_entity = session.query(EntityTypeEntity).filter(
                EntityTypeEntity.id == entity.type_id
            ).first()
            if type_entity:
                response.type_name = type_entity.name

            # Get latest check record
            latest_record = session.query(RiskCheckRecordEntity).filter(
                RiskCheckRecordEntity.entity_id == entity.id
            ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()

            if latest_record:
                response.risk_level = latest_record.risk_level
                response.risk_level_text = self._get_risk_level_text(latest_record.risk_level)
                response.last_check_at = latest_record.checked_at.strftime("%Y-%m-%d %H:%M:%S") if latest_record.checked_at else None
                response.summary = latest_record.summary

            # Check if user subscribed
            if user_id:
                subscription = session.query(EntitySubscriptionEntity).filter(
                    EntitySubscriptionEntity.user_id == user_id,
                    EntitySubscriptionEntity.entity_id == entity.id,
                ).first()
                response.subscribed = subscription is not None

            return response

    def create_entity(self, request: EntityRequest) -> EntityResponse:
        """Create a new entity.

        Args:
            request: The entity creation request.

        Returns:
            The created entity response.
        """
        entity = self._entity_dao.from_request(request)
        with self._entity_dao.session() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return self._entity_dao.to_response(entity)

    def update_entity(self, entity_id: str, request: EntityRequest) -> EntityResponse:
        """Update an entity.

        Args:
            entity_id: The entity ID.
            request: The update request.

        Returns:
            The updated entity response.

        Raises:
            ValueError: If entity not found.
        """
        with self._entity_dao.session() as session:
            entity = session.query(EntityEntity).filter(
                EntityEntity.id == entity_id
            ).first()

            if not entity:
                raise ValueError(f"Entity not found: {entity_id}")

            if request.name is not None:
                entity.name = request.name
            if request.config is not None:
                entity.config = request.config
            if request.extra_skills is not None:
                entity.extra_skills = request.extra_skills
            if request.source is not None:
                entity.source = request.source

            entity.updated_at = datetime.now()
            session.commit()
            session.refresh(entity)
            return self._entity_dao.to_response(entity)

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._entity_dao.session() as session:
            # Delete related records first
            session.query(RiskCheckRecordEntity).filter(
                RiskCheckRecordEntity.entity_id == entity_id
            ).delete()
            session.query(EntitySubscriptionEntity).filter(
                EntitySubscriptionEntity.entity_id == entity_id
            ).delete()
            session.query(EntityRelationEntity).filter(
                (EntityRelationEntity.source_entity_id == entity_id) |
                (EntityRelationEntity.target_entity_id == entity_id)
            ).delete()
            session.query(RiskDailySummaryEntity).filter(
                RiskDailySummaryEntity.entity_id == entity_id
            ).delete()
            session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.entity_id == entity_id
            ).delete()

            # Delete entity
            result = session.query(EntityEntity).filter(
                EntityEntity.id == entity_id
            ).delete()
            session.commit()
            return result > 0

    # ============ Entity Relation Methods ============

    def get_entity_relations(self, entity_id: str) -> List[EntityRelationResponse]:
        """Get all relations for an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            List of relation responses.
        """
        with self._relation_dao.session() as session:
            relations = session.query(EntityRelationEntity).filter(
                (EntityRelationEntity.source_entity_id == entity_id) |
                (EntityRelationEntity.target_entity_id == entity_id)
            ).all()

            responses = []
            for relation in relations:
                response = self._relation_dao.to_response(relation)

                # Get entity names
                source = session.query(EntityEntity).filter(
                    EntityEntity.id == relation.source_entity_id
                ).first()
                target = session.query(EntityEntity).filter(
                    EntityEntity.id == relation.target_entity_id
                ).first()

                if source:
                    response.source_entity_name = source.name
                if target:
                    response.target_entity_name = target.name

                responses.append(response)

            return responses

    def create_relation(self, request: EntityRelationRequest) -> EntityRelationResponse:
        """Create an entity relation.

        Args:
            request: The relation creation request.

        Returns:
            The created relation response.
        """
        entity = self._relation_dao.from_request(request)
        with self._relation_dao.session() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return self._relation_dao.to_response(entity)

    def delete_relation(self, relation_id: str) -> bool:
        """Delete an entity relation.

        Args:
            relation_id: The relation ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._relation_dao.session() as session:
            result = session.query(EntityRelationEntity).filter(
                EntityRelationEntity.id == relation_id
            ).delete()
            session.commit()
            return result > 0

    # ============ Risk Check Methods ============

    async def trigger_check(self, entity_id: str) -> RiskCheckRecordResponse:
        """Trigger a risk check for an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            The check record response.

        Raises:
            ValueError: If entity not found.
        """
        # Get entity
        entity = self.get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        # Get entity type for default skill
        entity_type = self.get_entity_type(entity.type_id)
        if not entity_type:
            raise ValueError(f"Entity type not found: {entity.type_id}")

        # TODO: Execute the skill and get risk result
        # For now, create a mock check record
        record = RiskCheckRecordEntity()
        record.id = uuid.uuid4().hex[:16]
        record.entity_id = entity_id
        record.conv_id = uuid.uuid4().hex[:16]
        record.risk_level = "green"
        record.summary = "风险巡检完成，各项指标正常"
        record.details = {"check_type": "manual"}
        record.suggestions = []
        record.checked_at = datetime.now()

        with self._check_record_dao.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._check_record_dao.to_response(record)

    def get_check_history(self, entity_id: str, limit: int = 10) -> List[RiskCheckRecordResponse]:
        """Get check history for an entity.

        Args:
            entity_id: The entity ID.
            limit: Maximum number of records.

        Returns:
            List of check record responses.
        """
        with self._check_record_dao.session() as session:
            records = session.query(RiskCheckRecordEntity).filter(
                RiskCheckRecordEntity.entity_id == entity_id
            ).order_by(RiskCheckRecordEntity.checked_at.desc()).limit(limit).all()

            return [self._check_record_dao.to_response(record) for record in records]

    # ============ Subscription Methods ============

    def list_subscriptions(self, user_id: str) -> List[EntitySubscriptionResponse]:
        """List all subscriptions for a user.

        Args:
            user_id: The user ID.

        Returns:
            List of subscription responses.
        """
        with self._subscription_dao.session() as session:
            subscriptions = session.query(EntitySubscriptionEntity).filter(
                EntitySubscriptionEntity.user_id == user_id
            ).all()

            responses = []
            for sub in subscriptions:
                response = self._subscription_dao.to_response(sub)

                # Get entity info
                entity = session.query(EntityEntity).filter(
                    EntityEntity.id == sub.entity_id
                ).first()
                if entity:
                    response.entity_name = entity.name

                    # Get type name
                    type_entity = session.query(EntityTypeEntity).filter(
                        EntityTypeEntity.id == entity.type_id
                    ).first()
                    if type_entity:
                        response.entity_type_name = type_entity.name

                    # Get risk level
                    latest_record = session.query(RiskCheckRecordEntity).filter(
                        RiskCheckRecordEntity.entity_id == entity.id
                    ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()
                    if latest_record:
                        response.risk_level = latest_record.risk_level

                responses.append(response)

            return responses

    def create_subscription(self, request: EntitySubscriptionRequest) -> EntitySubscriptionResponse:
        """Create a subscription.

        Args:
            request: The subscription creation request.

        Returns:
            The created subscription response.
        """
        entity = self._subscription_dao.from_request(request)
        with self._subscription_dao.session() as session:
            # Check if already subscribed
            existing = session.query(EntitySubscriptionEntity).filter(
                EntitySubscriptionEntity.user_id == request.user_id,
                EntitySubscriptionEntity.entity_id == request.entity_id,
            ).first()

            if existing:
                return self._subscription_dao.to_response(existing)

            session.add(entity)
            session.commit()
            session.refresh(entity)
            return self._subscription_dao.to_response(entity)

    def delete_subscription(self, subscription_id: str) -> bool:
        """Delete a subscription.

        Args:
            subscription_id: The subscription ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._subscription_dao.session() as session:
            result = session.query(EntitySubscriptionEntity).filter(
                EntitySubscriptionEntity.id == subscription_id
            ).delete()
            session.commit()
            return result > 0

    # ============ Dashboard Methods ============

    def get_risk_summary(self) -> RiskSummaryResponse:
        """Get risk summary for all entities.

        Returns:
            Risk summary with counts for each risk level.
        """
        with self._entity_dao.session() as session:
            entities = session.query(EntityEntity).all()

            green_count = 0
            blue_count = 0
            yellow_count = 0
            red_count = 0

            for entity in entities:
                # Get latest check record
                latest_record = session.query(RiskCheckRecordEntity).filter(
                    RiskCheckRecordEntity.entity_id == entity.id
                ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()

                if latest_record:
                    if latest_record.risk_level == "green":
                        green_count += 1
                    elif latest_record.risk_level == "blue":
                        blue_count += 1
                    elif latest_record.risk_level == "yellow":
                        yellow_count += 1
                    elif latest_record.risk_level == "red":
                        red_count += 1
                else:
                    # No check record, assume green
                    green_count += 1

            return RiskSummaryResponse(
                green_count=green_count,
                blue_count=blue_count,
                yellow_count=yellow_count,
                red_count=red_count,
                total_count=len(entities),
            )

    def get_heatmap_data(self, days: int = 30) -> List[HeatmapDataPoint]:
        """Get heatmap data for the specified number of days.

        Args:
            days: Number of days to include.

        Returns:
            List of heatmap data points.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        with self._daily_summary_dao.session() as session:
            # Get all daily summaries in the date range
            summaries = session.query(RiskDailySummaryEntity).filter(
                RiskDailySummaryEntity.date >= start_date,
                RiskDailySummaryEntity.date <= end_date,
            ).all()

            # Group by date
            date_data: Dict[str, Dict[str, int]] = {}
            for summary in summaries:
                date_str = summary.date.isoformat() if summary.date else None
                if date_str:
                    if date_str not in date_data:
                        date_data[date_str] = {"green": 0, "blue": 0, "yellow": 0, "red": 0}

                    level = summary.risk_level
                    if level in date_data[date_str]:
                        date_data[date_str][level] += 1

            # Generate heatmap data points
            data_points = []
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.isoformat()
                day_data = date_data.get(date_str, {"green": 0, "blue": 0, "yellow": 0, "red": 0})

                data_points.append(HeatmapDataPoint(
                    date=date_str,
                    green_count=day_data["green"],
                    blue_count=day_data["blue"],
                    yellow_count=day_data["yellow"],
                    red_count=day_data["red"],
                ))

                current_date += timedelta(days=1)

            return data_points

    def _get_risk_level_text(self, risk_level: str) -> str:
        """Get display text for risk level.

        Args:
            risk_level: The risk level.

        Returns:
            Display text.
        """
        level_map = {
            "green": "正常",
            "blue": "关注",
            "yellow": "警告",
            "red": "危险",
        }
        return level_map.get(risk_level, "未知")

    # ============ Entity Skill Config Methods ============

    def list_entity_skills(self, entity_id: str) -> List[EntitySkillConfigResponse]:
        """List all skill configurations for an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            List of skill configuration responses.
        """
        with self._skill_config_dao.session() as session:
            skills = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.entity_id == entity_id
            ).order_by(EntitySkillConfigEntity.skill_type, EntitySkillConfigEntity.created_at).all()

            responses = []
            for skill in skills:
                response = self._skill_config_dao.to_response(skill)

                # Get latest check record for this skill
                latest_record = session.query(RiskCheckRecordEntity).filter(
                    RiskCheckRecordEntity.entity_id == entity_id
                ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()

                if latest_record:
                    response.last_check_at = latest_record.checked_at.strftime("%Y-%m-%d %H:%M:%S") if latest_record.checked_at else None
                    response.last_risk_level = latest_record.risk_level

                responses.append(response)

            return responses

    def get_entity_skill(self, entity_id: str, skill_id: str) -> Optional[EntitySkillConfigResponse]:
        """Get a skill configuration by ID.

        Args:
            entity_id: The entity ID.
            skill_id: The skill configuration ID.

        Returns:
            The skill configuration response or None.
        """
        with self._skill_config_dao.session() as session:
            skill = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.id == skill_id,
                EntitySkillConfigEntity.entity_id == entity_id,
            ).first()

            if skill:
                response = self._skill_config_dao.to_response(skill)

                # Get latest check record for this skill
                latest_record = session.query(RiskCheckRecordEntity).filter(
                    RiskCheckRecordEntity.entity_id == entity_id
                ).order_by(RiskCheckRecordEntity.checked_at.desc()).first()

                if latest_record:
                    response.last_check_at = latest_record.checked_at.strftime("%Y-%m-%d %H:%M:%S") if latest_record.checked_at else None
                    response.last_risk_level = latest_record.risk_level

                return response
            return None

    def create_entity_skill(self, request: EntitySkillConfigRequest) -> EntitySkillConfigResponse:
        """Create a skill configuration for an entity.

        Args:
            request: The skill configuration creation request.

        Returns:
            The created skill configuration response.

        Raises:
            ValueError: If skill already exists.
        """
        with self._skill_config_dao.session() as session:
            # Check if skill already exists
            existing = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.entity_id == request.entity_id,
                EntitySkillConfigEntity.skill_code == request.skill_code,
            ).first()

            if existing:
                raise ValueError(f"Skill {request.skill_code} already configured for entity {request.entity_id}")

            entity = self._skill_config_dao.from_request(request)
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return self._skill_config_dao.to_response(entity)

    def update_entity_skill(
        self,
        entity_id: str,
        skill_id: str,
        request: EntitySkillConfigRequest,
    ) -> EntitySkillConfigResponse:
        """Update a skill configuration.

        Args:
            entity_id: The entity ID.
            skill_id: The skill configuration ID.
            request: The update request.

        Returns:
            The updated skill configuration response.

        Raises:
            ValueError: If skill configuration not found or trying to delete default skill.
        """
        with self._skill_config_dao.session() as session:
            skill = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.id == skill_id,
                EntitySkillConfigEntity.entity_id == entity_id,
            ).first()

            if not skill:
                raise ValueError(f"Skill configuration not found: {skill_id}")

            if request.check_params is not None:
                skill.check_params = request.check_params

            skill.updated_at = datetime.now()
            session.commit()
            session.refresh(skill)
            return self._skill_config_dao.to_response(skill)

    def toggle_entity_skill(self, entity_id: str, skill_id: str) -> EntitySkillConfigResponse:
        """Toggle a skill configuration's enabled state.

        Args:
            entity_id: The entity ID.
            skill_id: The skill configuration ID.

        Returns:
            The updated skill configuration response.

        Raises:
            ValueError: If skill configuration not found.
        """
        with self._skill_config_dao.session() as session:
            skill = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.id == skill_id,
                EntitySkillConfigEntity.entity_id == entity_id,
            ).first()

            if not skill:
                raise ValueError(f"Skill configuration not found: {skill_id}")

            skill.enabled = not skill.enabled
            skill.updated_at = datetime.now()
            session.commit()
            session.refresh(skill)
            return self._skill_config_dao.to_response(skill)

    def delete_entity_skill(self, entity_id: str, skill_id: str) -> bool:
        """Delete a skill configuration.

        Args:
            entity_id: The entity ID.
            skill_id: The skill configuration ID.

        Returns:
            True if deleted.

        Raises:
            ValueError: If skill configuration not found or is a default skill.
        """
        with self._skill_config_dao.session() as session:
            skill = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.id == skill_id,
                EntitySkillConfigEntity.entity_id == entity_id,
            ).first()

            if not skill:
                raise ValueError(f"Skill configuration not found: {skill_id}")

            if skill.skill_type == "default":
                raise ValueError("Cannot delete default skill. Disable it instead.")

            result = session.query(EntitySkillConfigEntity).filter(
                EntitySkillConfigEntity.id == skill_id,
            ).delete()
            session.commit()
            return result > 0

    def create_default_skill_for_entity(self, entity_id: str, type_id: str) -> Optional[EntitySkillConfigResponse]:
        """Create the default skill configuration for a new entity.

        Args:
            entity_id: The entity ID.
            type_id: The entity type ID.

        Returns:
            The created skill configuration response or None if no default skill.
        """
        # Get entity type for default skill
        entity_type = self.get_entity_type(type_id)
        if not entity_type or not entity_type.default_skill_code:
            return None

        request = EntitySkillConfigRequest(
            entity_id=entity_id,
            skill_code=entity_type.default_skill_code,
            skill_name=f"Default {entity_type.name} Check",
            skill_type="default",
            enabled=True,
        )

        return self.create_entity_skill(request)