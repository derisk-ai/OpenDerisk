import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager, Model, UnifiedDBManagerFactory, db
from derisk_serve.core import BaseServe

from .api.endpoints import init_endpoints, router
from .config import (  # noqa: F401
    APP_NAME,
    SERVE_APP_NAME,
    SERVE_APP_NAME_HUMP,
    SERVE_CONFIG_KEY_PREFIX,
    ServeConfig,
)

logger = logging.getLogger(__name__)


class Serve(BaseServe):
    """Serve component for MCP"""

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
        self._app_has_initiated = True

    def on_init(self):
        """Called when init the application.

        You can do some initialization here. You can't get other components here
        because they may be not initialized yet
        """
        # import models to ensure they are registered with SQLAlchemy
        from .models.models import ServeEntity  # noqa: F401
        _ = list(map(lambda x: None, [
            ServeEntity.__tablename__,
        ]))

    def before_start(self):
        """Called before the start of the application.

        You can do some initialization here.
        """
        # Import models to ensure they are registered
        from .models.models import ServeEntity  # noqa: F401

        self._db_manager = self.create_or_get_db_manager()

        # Force create tables for SQLite mode
        db_manager_factory: UnifiedDBManagerFactory = self._system_app.get_component(
            "unified_metadata_db_manager_factory",
            UnifiedDBManagerFactory,
            default_component=None,
        )
        if db_manager_factory is not None and db_manager_factory.create():
            init_db = db_manager_factory.create()
        else:
            init_db = self._db_url_or_db or db
            init_db = DatabaseManager.build_from(init_db, base=Model)

        try:
            init_db.create_all()
        except Exception as e:
            logger.warning(f"Failed to create MCP tables: {e}")