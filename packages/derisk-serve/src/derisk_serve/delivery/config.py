"""Delivery serve config."""
from dataclasses import dataclass, field
from typing import Optional

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "delivery"
SERVE_APP_NAME = "derisk_serve_delivery"
SERVE_APP_NAME_HUMP = "derisk_serve_delivery"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.delivery."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
SERVER_APP_TABLE_NAME = "server_app_delivery"


@auto_register_resource(
    label=_("Delivery Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("Configuration for the delivery serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    __type__ = APP_NAME

    api_keys: Optional[str] = field(
        default=None,
        metadata={"help": _("API keys for delivery serve, comma-separated")},
    )
    smtp_host: Optional[str] = field(default=None, metadata={"help": _("SMTP host")})
    smtp_port: Optional[int] = field(default=None, metadata={"help": _("SMTP port")})
    smtp_user: Optional[str] = field(default=None, metadata={"help": _("SMTP user")})
    smtp_password: Optional[str] = field(default=None, metadata={"help": _("SMTP password")})
    smtp_from: Optional[str] = field(default=None, metadata={"help": _("SMTP from address")})

    def get_type_value(self) -> str:
        return self.__type__
