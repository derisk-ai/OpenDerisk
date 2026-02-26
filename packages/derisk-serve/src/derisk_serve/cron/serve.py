"""Cron serve component.

This module provides the main serve component for the cron scheduling service,
integrating with the FastAPI application and managing the service lifecycle.
"""

import asyncio
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
    """Cron serve component for Derisk.

    This component provides cron job scheduling capabilities:
    - REST API for job management
    - APScheduler-based job execution
    - Support for Agent, Tool, and System Event execution
    - Distributed lock support for multi-instance deployment
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
        """Initialize the cron serve component.

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
        from .models.models import CronJobEntity  # noqa: F401
        # Import tools to register them with @system_tool decorator
        from .tools import create_cron_job  # noqa: F401

    def before_start(self):
        """Called before the application starts.

        Initialize the database manager and start the scheduler.
        """
        from .service.service import Service

        logger.info("Starting cron serve component")

        # Get the service instance
        service = self._system_app.get_component(
            SERVE_APP_NAME + "_service", Service
        )

        # Start the scheduler asynchronously
        if self._config and self._config.enabled:
            # Create a task to start the scheduler
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(service.start())
            else:
                loop.run_until_complete(service.start())
            logger.info("Cron scheduler started")

    def before_stop(self):
        """Called before the application stops.

        Stop the scheduler gracefully.
        """
        from .service.service import Service

        logger.info("Stopping cron serve component")

        try:
            service = self._system_app.get_component(
                SERVE_APP_NAME + "_service", Service
            )
            if service:
                service.stop()
                logger.info("Cron scheduler stopped")
        except Exception as e:
            logger.warning(f"Error stopping cron scheduler: {e}")