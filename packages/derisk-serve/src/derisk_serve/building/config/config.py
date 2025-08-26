from dataclasses import dataclass

from derisk_serve.core import BaseServeConfig

APP_NAME = "building/config"
SERVE_APP_NAME = "derisk_serve_building/config"
SERVE_APP_NAME_HUMP = "derisk_serve_Building/config"
SERVE_CONFIG_KEY_PREFIX = "derisk_serve.building/config."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_building/config"


@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME

    # TODO: add your own parameters here
