"""Cron serve configuration.

This module defines the configuration for the cron scheduling service.
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

APP_NAME = "cron"
SERVE_APP_NAME = "derisk_serve_cron"
SERVE_APP_NAME_HUMP = "derisk_serve_Cron"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.cron."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_cron_job"


@auto_register_resource(
    label=_("Cron Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("This configuration is for the cron serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    """Configuration for the cron scheduling service."""

    __type__ = APP_NAME

    enabled: bool = field(
        default=True,
        metadata={"help": _("Enable cron scheduler")},
    )
    max_concurrent_jobs: int = field(
        default=10,
        metadata={"help": _("Maximum number of concurrent job executions")},
    )
    default_timeout_seconds: int = field(
        default=600,
        metadata={"help": _("Default timeout for job execution in seconds")},
    )
    lock_backend: Optional[str] = field(
        default=None,
        metadata={"help": _("Distributed lock backend (memory/redis)")},
    )
    misfire_grace_time: int = field(
        default=60,
        metadata={"help": _("Grace time in seconds for misfired jobs")},
    )
    coalesce: bool = field(
        default=True,
        metadata={"help": _("Coalesce missed job executions")},
    )
    max_instances: int = field(
        default=1,
        metadata={"help": _("Maximum instances of the same job running concurrently")},
    )