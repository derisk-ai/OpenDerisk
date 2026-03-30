"""Risk Dashboard API schemas.

This module defines the Pydantic schemas for the risk dashboard API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP


# ============ Entity Type Schemas ============

class EntityTypeRequest(BaseModel):
    """Request schema for creating/updating an entity type."""

    model_config = ConfigDict(title=f"EntityTypeRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the entity type",
    )
    name: str = Field(
        ...,
        description="Entity type name",
        examples=["应用", "数据库"],
    )
    description: Optional[str] = Field(
        default=None,
        description="Entity type description",
    )
    default_skill_code: Optional[str] = Field(
        default=None,
        description="Default check skill code",
        examples=["app-health-check"],
    )
    icon: Optional[str] = Field(
        default=None,
        description="Icon name or URL",
        examples=["AppstoreOutlined", "DatabaseOutlined"],
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class EntityTypeResponse(BaseModel):
    """Response schema for an entity type."""

    model_config = ConfigDict(
        title=f"EntityTypeResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the entity type",
    )
    name: str = Field(
        ...,
        description="Entity type name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Entity type description",
    )
    default_skill_code: Optional[str] = Field(
        default=None,
        description="Default check skill code",
    )
    icon: Optional[str] = Field(
        default=None,
        description="Icon name or URL",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    entity_count: Optional[int] = Field(
        default=None,
        description="Count of entities of this type",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Entity Schemas ============

class EntityRequest(BaseModel):
    """Request schema for creating/updating an entity."""

    model_config = ConfigDict(title=f"EntityRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the entity",
    )
    type_id: str = Field(
        ...,
        description="Entity type ID",
    )
    name: str = Field(
        ...,
        description="Entity name",
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Entity configuration as JSON",
    )
    extra_skills: Optional[List[str]] = Field(
        default=None,
        description="Extra skill list",
    )
    source: Optional[str] = Field(
        default="manual",
        description="Entity source (manual/auto)",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class EntityResponse(BaseModel):
    """Response schema for an entity."""

    model_config = ConfigDict(
        title=f"EntityResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the entity",
    )
    type_id: str = Field(
        ...,
        description="Entity type ID",
    )
    name: str = Field(
        ...,
        description="Entity name",
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Entity configuration",
    )
    extra_skills: Optional[List[str]] = Field(
        default=None,
        description="Extra skill list",
    )
    source: Optional[str] = Field(
        default="manual",
        description="Entity source",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="Record update time",
    )
    # Additional fields for display
    type_name: Optional[str] = Field(
        default=None,
        description="Entity type name",
    )
    risk_level: Optional[str] = Field(
        default=None,
        description="Current risk level",
    )
    risk_level_text: Optional[str] = Field(
        default=None,
        description="Risk level display text",
    )
    last_check_at: Optional[str] = Field(
        default=None,
        description="Last check time",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Latest check summary",
    )
    subscribed: Optional[bool] = Field(
        default=None,
        description="Whether current user subscribed",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Entity Relation Schemas ============

class EntityRelationRequest(BaseModel):
    """Request schema for creating an entity relation."""

    model_config = ConfigDict(title=f"EntityRelationRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the relation",
    )
    source_entity_id: str = Field(
        ...,
        description="Source entity ID",
    )
    target_entity_id: str = Field(
        ...,
        description="Target entity ID",
    )
    relation_type: str = Field(
        ...,
        description="Relation type (depends_on/contains/impacts)",
        examples=["depends_on", "contains", "impacts"],
    )
    strength: Optional[str] = Field(
        default="weak",
        description="Relation strength (strong/weak)",
        examples=["strong", "weak"],
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class EntityRelationResponse(BaseModel):
    """Response schema for an entity relation."""

    model_config = ConfigDict(
        title=f"EntityRelationResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the relation",
    )
    source_entity_id: str = Field(
        ...,
        description="Source entity ID",
    )
    target_entity_id: str = Field(
        ...,
        description="Target entity ID",
    )
    relation_type: str = Field(
        ...,
        description="Relation type",
    )
    strength: str = Field(
        ...,
        description="Relation strength",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    # Additional fields for display
    source_entity_name: Optional[str] = Field(
        default=None,
        description="Source entity name",
    )
    target_entity_name: Optional[str] = Field(
        default=None,
        description="Target entity name",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Risk Check Record Schemas ============

class RiskCheckRecordRequest(BaseModel):
    """Request schema for creating a risk check record."""

    model_config = ConfigDict(title=f"RiskCheckRecordRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the record",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    conv_id: Optional[str] = Field(
        default=None,
        description="Conversation session ID",
    )
    risk_level: str = Field(
        ...,
        description="Risk level (green/blue/yellow/red)",
        examples=["green", "blue", "yellow", "red"],
    )
    summary: Optional[str] = Field(
        default=None,
        description="Check summary",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Check details",
    )
    suggestions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Suggestions list",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class RiskCheckRecordResponse(BaseModel):
    """Response schema for a risk check record."""

    model_config = ConfigDict(
        title=f"RiskCheckRecordResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the record",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    conv_id: Optional[str] = Field(
        default=None,
        description="Conversation session ID",
    )
    risk_level: str = Field(
        ...,
        description="Risk level",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Check summary",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Check details",
    )
    suggestions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Suggestions list",
    )
    checked_at: Optional[str] = Field(
        default=None,
        description="Check time",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Entity Subscription Schemas ============

class EntitySubscriptionRequest(BaseModel):
    """Request schema for creating a subscription."""

    model_config = ConfigDict(title=f"EntitySubscriptionRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the subscription",
    )
    user_id: str = Field(
        ...,
        description="User ID",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    notify_level: Optional[str] = Field(
        default="all",
        description="Notify level (all/yellow_plus/red_only)",
        examples=["all", "yellow_plus", "red_only"],
    )
    notify_channels: Optional[List[str]] = Field(
        default=None,
        description="Notify channels",
        examples=[["dingtalk", "email"]],
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class EntitySubscriptionResponse(BaseModel):
    """Response schema for a subscription."""

    model_config = ConfigDict(
        title=f"EntitySubscriptionResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the subscription",
    )
    user_id: str = Field(
        ...,
        description="User ID",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    notify_level: str = Field(
        ...,
        description="Notify level",
    )
    notify_channels: Optional[List[str]] = Field(
        default=None,
        description="Notify channels",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    # Additional fields for display
    entity_name: Optional[str] = Field(
        default=None,
        description="Entity name",
    )
    entity_type_name: Optional[str] = Field(
        default=None,
        description="Entity type name",
    )
    risk_level: Optional[str] = Field(
        default=None,
        description="Current risk level",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Risk Daily Summary Schemas ============

class RiskDailySummaryResponse(BaseModel):
    """Response schema for a risk daily summary."""

    model_config = ConfigDict(
        title=f"RiskDailySummaryResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the summary",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    date: Optional[str] = Field(
        default=None,
        description="Summary date",
    )
    risk_level: str = Field(
        ...,
        description="Risk level",
    )
    check_count: int = Field(
        ...,
        description="Check count for the day",
    )
    issue_count: int = Field(
        ...,
        description="Issue count for the day",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Dashboard Summary Schemas ============

class RiskSummaryResponse(BaseModel):
    """Response schema for risk summary."""

    model_config = ConfigDict(
        title=f"RiskSummaryResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    green_count: int = Field(
        ...,
        description="Count of entities with green risk level",
    )
    blue_count: int = Field(
        ...,
        description="Count of entities with blue risk level",
    )
    yellow_count: int = Field(
        ...,
        description="Count of entities with yellow risk level",
    )
    red_count: int = Field(
        ...,
        description="Count of entities with red risk level",
    )
    total_count: int = Field(
        ...,
        description="Total entity count",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class HeatmapDataPoint(BaseModel):
    """Data point for heatmap."""

    model_config = ConfigDict(title=f"HeatmapDataPoint for {SERVE_APP_NAME_HUMP}")

    date: str = Field(
        ...,
        description="Date string (YYYY-MM-DD)",
    )
    green_count: int = Field(
        ...,
        description="Count of green entities",
    )
    blue_count: int = Field(
        ...,
        description="Count of blue entities",
    )
    yellow_count: int = Field(
        ...,
        description="Count of yellow entities",
    )
    red_count: int = Field(
        ...,
        description="Count of red entities",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class HeatmapResponse(BaseModel):
    """Response schema for heatmap data."""

    model_config = ConfigDict(
        title=f"HeatmapResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    data: List[HeatmapDataPoint] = Field(
        ...,
        description="Heatmap data points",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


# ============ Entity Skill Config Schemas ============

class EntitySkillConfigRequest(BaseModel):
    """Request schema for creating/updating an entity skill configuration."""

    model_config = ConfigDict(title=f"EntitySkillConfigRequest for {SERVE_APP_NAME_HUMP}")

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the skill config",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    skill_code: str = Field(
        ...,
        description="Skill code",
        examples=["app-health-check", "log-analysis"],
    )
    skill_name: Optional[str] = Field(
        default=None,
        description="Skill name (redundant storage for display)",
    )
    skill_type: str = Field(
        default="custom",
        description="Skill type (default/custom)",
        examples=["default", "custom"],
    )
    enabled: Optional[bool] = Field(
        default=True,
        description="Whether the skill is enabled",
    )
    check_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Check parameters",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class EntitySkillConfigResponse(BaseModel):
    """Response schema for an entity skill configuration."""

    model_config = ConfigDict(
        title=f"EntitySkillConfigResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    id: str = Field(
        ...,
        description="Unique identifier for the skill config",
    )
    entity_id: str = Field(
        ...,
        description="Entity ID",
    )
    skill_code: str = Field(
        ...,
        description="Skill code",
    )
    skill_name: Optional[str] = Field(
        default=None,
        description="Skill name",
    )
    skill_type: str = Field(
        ...,
        description="Skill type (default/custom)",
    )
    enabled: bool = Field(
        ...,
        description="Whether the skill is enabled",
    )
    check_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Check parameters",
    )
    last_check_at: Optional[str] = Field(
        default=None,
        description="Last check time",
    )
    last_risk_level: Optional[str] = Field(
        default=None,
        description="Last risk level",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Record creation time",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="Record update time",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)


class SkillResponse(BaseModel):
    """Response schema for a skill."""

    model_config = ConfigDict(
        title=f"SkillResponse for {SERVE_APP_NAME_HUMP}", protected_namespaces=()
    )

    skill_code: str = Field(
        ...,
        description="Skill code",
    )
    name: str = Field(
        ...,
        description="Skill name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Skill description",
    )
    type: str = Field(
        ...,
        description="Skill type (builtin/custom)",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary."""
        return model_to_dict(self, **kwargs)