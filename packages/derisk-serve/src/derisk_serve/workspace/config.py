from dataclasses import dataclass, field
from typing import Optional

from derisk_serve.core import BaseServeConfig

APP_NAME = "workspace"
SERVE_APP_NAME = "derisk_serve_workspace"
SERVE_APP_NAME_HUMP = "Workspace"
SERVER_APP_TABLE_NAME = "server_app_workspace"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.workspace"


@dataclass
class ServeConfig(BaseServeConfig):
    """Serve configuration for Scenario Workspace"""

    __type__ = SERVE_APP_NAME

    api_keys: Optional[str] = field(
        default=None, metadata={"help": "API keys for the serve"}
    )

    def get_type_value(self):
        return self.__type__
