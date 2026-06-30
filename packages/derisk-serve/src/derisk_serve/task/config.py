from dataclasses import dataclass, field
from typing import Optional

from derisk_serve.core import BaseServeConfig

APP_NAME = "task"
SERVE_APP_NAME = "derisk_serve_task"
SERVE_APP_NAME_HUMP = "Task"
SERVER_APP_TABLE_NAME = "server_app_task"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.task"


@dataclass
class ServeConfig(BaseServeConfig):
    __type__ = SERVE_APP_NAME
    api_keys: Optional[str] = field(default=None, metadata={"help": "API keys"})

    def get_type_value(self):
        return self.__type__
