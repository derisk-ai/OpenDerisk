from dataclasses import dataclass

from derisk_serve.core import BaseServeConfig

APP_NAME = "agent/chat"
SERVE_APP_NAME = "derisk_serve_agent/chat"
SERVE_APP_NAME_HUMP = "derisk_serve_Agent/chat"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.agent/chat."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_agent/chat"


@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME
