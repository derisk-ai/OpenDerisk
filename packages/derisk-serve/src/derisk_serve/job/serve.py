"""Job engine serve component — boots the worker loop on app start."""

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
    """Persistent job engine serve component.

    Boots a worker loop (asyncio background task in the web process) that
    claims pending `derisk_serve_job` rows via SKIP LOCKED (PG/MySQL) or an
    atomic conditional UPDATE (SQLite), dispatches to registered handlers by
    `job_type`, and ack/nacks on completion.
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
        if api_tags is None:
            api_tags = [SERVE_APP_NAME_HUMP]
        super().__init__(
            system_app, api_prefix, api_tags, db_url_or_db, try_create_tables
        )
        self._config = config
        self._db_manager: Optional[DatabaseManager] = None

    def init_app(self, system_app: SystemApp):
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
        """Load the DB model so table creation picks it up."""
        from .models.models import JobEntity  # noqa: F401

    def before_start(self):
        """Start the worker loop."""
        from .service.service import Service

        logger.info("Starting job engine serve component")
        service = self._system_app.get_component(
            SERVE_APP_NAME + "_service", Service
        )
        if self._config and self._config.enabled:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(service.start())
            else:
                loop.run_until_complete(service.start())
            logger.info("Job engine worker started")

    def before_stop(self):
        from .service.service import Service

        logger.info("Stopping job engine serve component")
        try:
            service = self._system_app.get_component(
                SERVE_APP_NAME + "_service", Service
            )
            if service:
                service.stop()
        except Exception as e:
            logger.warning(f"Error stopping job engine: {e}")