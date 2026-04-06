import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager
from derisk_serve.core import BaseServe

from .api.endpoints import init_endpoints, router
from .config import (
    SERVE_APP_NAME,
    SERVE_APP_NAME_HUMP,
    SERVE_CONFIG_KEY_PREFIX,
    ServeConfig,
)

logger = logging.getLogger(__name__)


class Serve(BaseServe):
    """Serve component for DERISK"""

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = "/api/v2/serve",
        api_tags: Optional[List[str]] = None,
        db_url_or_db: Union[str, URL, DatabaseManager] = None,
        try_create_tables: Optional[bool] = False,
    ):
        if api_tags is None:
            api_tags = [SERVE_APP_NAME_HUMP]
        super().__init__(
            system_app, api_prefix, api_tags, db_url_or_db, try_create_tables
        )
        self._db_manager: Optional[DatabaseManager] = None
        self._config = config

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

        # Register SQL Guard routes (tightly coupled with datasource)
        try:
            from derisk_serve.sql_guard.api.endpoints import (
                router as sql_guard_router,
            )

            self._system_app.app.include_router(
                sql_guard_router,
                prefix=self._api_prefix,
                tags=["SQL Guard"],
            )
            logger.info("SQL Guard API routes registered")
        except ImportError:
            logger.debug("SQL Guard module not available, skipping route registration")

        self._app_has_initiated = True

    def on_init(self):
        """Called when init the application.

        You can do some initialization here. You can't get other components here
        because they may be not initialized yet
        """
        from .manages.connect_config_db import ConnectConfigEntity as _  # noqa: F401
        from .manages.db_spec_db import DbSpecEntity as _ds  # noqa: F401
        from .manages.table_spec_db import TableSpecEntity as _ts  # noqa: F401
        from .manages.learning_task_db import DbLearningTaskEntity as _lt  # noqa: F401

        # Ensure SQL Guard tables are created
        try:
            from derisk_serve.sql_guard.masking.config_db import (
                SensitiveColumnEntity as _sg,  # noqa: F401
            )
        except ImportError:
            pass

    def before_start(self):
        """Called before the start of the application."""
        # TODO: Your code here
        self._db_manager = self.create_or_get_db_manager()
