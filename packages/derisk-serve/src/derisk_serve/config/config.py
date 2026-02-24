from dataclasses import dataclass, field
from typing import List

from derisk.util.i18n_utils import _
from derisk.util.module_utils import ScannerConfig
from derisk_serve.config.service.base_upload import UpdaterConfig
from derisk_serve.core import BaseServeConfig

APP_NAME = "config"
SERVE_APP_NAME = "derisk_serve_config"
SERVE_APP_NAME_HUMP = "derisk_serve_Config"
SERVE_CONFIG_KEY_PREFIX = "derisk_serve.config."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_config"


@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME

    __scan_config__ = ScannerConfig(
        module_path="derisk_serve.config.service.ext",
        base_class=UpdaterConfig,
        recursive=True,
        # specific_files=["config"],
    )


    config_update_interval: int = field(
        default=60,
        metadata={"help": _("Interval to update from config updater")},
    )
    updaters: List[UpdaterConfig] = field(
        default_factory=list,
        metadata={"help": _("The updaters configurations")},
    )