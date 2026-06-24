"""Knowledge Serve module — three-view knowledge space HTTP API."""

from .config import (
    APP_NAME,
    SERVE_APP_NAME,
    SERVE_APP_NAME_HUMP,
    SERVE_CONFIG_KEY_PREFIX,
    ServeConfig,
)
from .serve import Serve

__all__ = [
    "APP_NAME",
    "SERVE_APP_NAME",
    "SERVE_APP_NAME_HUMP",
    "SERVE_CONFIG_KEY_PREFIX",
    "ServeConfig",
    "Serve",
]
