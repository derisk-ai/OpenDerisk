from derisk_serve.core import BaseServeConfig

APP_NAME = "version"
SERVE_APP_NAME = "derisk_serve_version"
SERVE_APP_NAME_HUMP = "derisk_serve_Version"
SERVE_CONFIG_KEY_PREFIX = "derisk_serve.version."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"


class ServeConfig(BaseServeConfig):
    """Configuration for version serve."""

    __type__ = APP_NAME