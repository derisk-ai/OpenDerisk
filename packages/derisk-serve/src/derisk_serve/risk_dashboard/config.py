"""Risk Dashboard serve configuration.

This module defines the configuration for the risk dashboard service.
"""

from dataclasses import dataclass, field
from typing import Optional

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "risk_dashboard"
SERVE_APP_NAME = "derisk_serve_risk_dashboard"
SERVE_APP_NAME_HUMP = "derisk_serve_RiskDashboard"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.risk_dashboard."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"

# Database table names
ENTITY_TYPE_TABLE_NAME = "derisk_serve_entity_type"
ENTITY_TABLE_NAME = "derisk_serve_entity"
ENTITY_RELATION_TABLE_NAME = "derisk_serve_entity_relation"
RISK_CHECK_RECORD_TABLE_NAME = "derisk_serve_risk_check_record"
ENTITY_SUBSCRIPTION_TABLE_NAME = "derisk_serve_entity_subscription"
RISK_DAILY_SUMMARY_TABLE_NAME = "derisk_serve_risk_daily_summary"
ENTITY_SKILL_CONFIG_TABLE_NAME = "derisk_serve_entity_skill_config"


@auto_register_resource(
    label=_("Risk Dashboard Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("This configuration is for the risk dashboard serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    """Configuration for the risk dashboard service."""

    __type__ = APP_NAME

    enabled: bool = field(
        default=True,
        metadata={"help": _("Enable risk dashboard")},
    )
    default_check_interval_hours: int = field(
        default=24,
        metadata={"help": _("Default interval for risk checks in hours")},
    )
    max_check_history_days: int = field(
        default=30,
        metadata={"help": _("Maximum days to keep check history")},
    )