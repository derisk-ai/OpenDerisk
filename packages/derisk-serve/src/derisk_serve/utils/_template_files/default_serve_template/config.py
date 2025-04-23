from dataclasses import dataclass

from derisk_serve.core import BaseServeConfig

APP_NAME = "{__template_app_name__all_lower__}"
SERVE_APP_NAME = "derisk_serve_{__template_app_name__all_lower__}"
SERVE_APP_NAME_HUMP = "derisk_serve_{__template_app_name__hump__}"
SERVE_CONFIG_KEY_PREFIX = "derisk_serve.{__template_app_name__all_lower__}."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_{__template_app_name__all_lower__}"


@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME

    # TODO: add your own parameters here
