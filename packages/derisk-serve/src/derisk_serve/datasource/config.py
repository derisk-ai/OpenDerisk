from dataclasses import dataclass

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "datasource"
SERVE_APP_NAME = "derisk_datasource"
SERVE_APP_NAME_HUMP = "derisk_datasource"
SERVE_CONFIG_KEY_PREFIX = "derisk_datasource"
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"


@auto_register_resource(
    label=_("Datasource Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("This configuration is for the datasource serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME
