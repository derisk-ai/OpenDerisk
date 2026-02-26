"""Channel serve component.

This module provides the main serve component for the channel service,
integrating with the FastAPI application and managing the service lifecycle.
"""

import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager
from derisk_serve.core import BaseServe

from .api.endpoints import init_endpoints, router
from .config import (
    APP_NAME,
    SERVE_APP_NAME,
    SERVE_APP_NAME_HUMP,
    SERVE_CONFIG_KEY_PREFIX,
    ServeConfig,
)

logger = logging.getLogger(__name__)


class Serve(BaseServe):
    """Channel serve component for Derisk.

    This component provides message channel management capabilities:
    - REST API for channel management
    - Support for DingTalk, Feishu, WeChat, QQ
    - Webhook endpoints for receiving messages
    """

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = f"/api/v1/serve/{APP_NAME}",
        api_tags: Optional[List[str]] = None,
        db_url_or_db: Union[str, URL, DatabaseManager] = None,
        try_create_tables: Optional[bool] = False,
    ):
        """Initialize the channel serve component.

        Args:
            system_app: The system application instance.
            config: Optional service configuration.
            api_prefix: The API prefix for endpoints.
            api_tags: The API tags for OpenAPI documentation.
            db_url_or_db: Database URL or manager instance.
            try_create_tables: Whether to try creating tables on startup.
        """
        if api_tags is None:
            api_tags = [SERVE_APP_NAME_HUMP]
        super().__init__(
            system_app, api_prefix, api_tags, db_url_or_db, try_create_tables
        )
        self._config = config
        self._db_manager: Optional[DatabaseManager] = None

    def init_app(self, system_app: SystemApp):
        """Initialize the serve component.

        Args:
            system_app: The system application instance.
        """
        if self._app_has_initiated:
            return
        self._system_app = system_app
        self._system_app.app.include_router(
            router, prefix=self._api_prefix, tags=self._api_tags
        )
        self._config = self._config or ServeConfig.from_app_config(
            system_app.config, SERVE_CONFIG_KEY_PREFIX
        )
        init_endpoints(self._system_app, self._config)
        self._app_has_initiated = True

    def on_init(self):
        """Called when initializing the application.

        Load the database model to ensure table creation.
        """
        from .models.models import ChannelEntity  # noqa: F401

    def before_start(self):
        """Called before the application starts.

        Initialize the service.
        """
        logger.info("Starting channel serve component")

    def before_stop(self):
        """Called before the application stops.

        Cleanup resources.
        """
        logger.info("Stopping channel serve component")