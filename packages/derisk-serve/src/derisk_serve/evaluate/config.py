from dataclasses import dataclass, field
from typing import Optional 

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)

from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "evaluate"
SERVE_APP_NAME = "derisk_serve_evaluate"
SERVE_APP_NAME_HUMP = "derisk_serve_Evaluate"
SERVE_CONFIG_KEY_PREFIX = "derisk_serve.evaluate."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_evaluate"

@auto_register_resource(
    label=_("Evaluate Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("This configuration is for the evaluate serve module."),
    show_in_ui=False
)

@dataclass
class ServeConfig(BaseServeConfig):
    """Parameters for the serve command"""

    __type__ = APP_NAME

    # TODO: add your own parameters here
    embedding_model: Optional[str] = field() 
