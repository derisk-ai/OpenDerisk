"""Channel serve configuration.

This module defines the configuration for the channel service.
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

APP_NAME = "channel"
SERVE_APP_NAME = "derisk_serve_channel"
SERVE_APP_NAME_HUMP = "derisk_serve_Channel"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.channel."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_channel_config"


@auto_register_resource(
    label=_("Channel Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("This configuration is for the channel serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    """Configuration for the channel service."""

    __type__ = APP_NAME

    enabled: bool = field(
        default=True,
        metadata={"help": _("Enable channel service")},
    )
    api_keys: Optional[str] = field(
        default=None,
        metadata={"help": _("API keys for channel management endpoints")},
    )