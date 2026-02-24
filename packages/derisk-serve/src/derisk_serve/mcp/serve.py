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

        # Sync default MCP server configurations from derisk-mcps config files
        self._sync_default_mcp_configs()

    def _sync_default_mcp_configs(self):
        """Clone MCP config repo from GitHub and sync default configs to DB.

        Follows the same pattern as the skill module:
        1. Clone (or pull) the remote repo to
           ``pilot/data/mcp/.git_cache/<md5-hash>/``
        2. Compare the HEAD commit hash to detect changes
        3. Copy JSON config files from ``servers/`` to ``pilot/data/mcp/``
        4. Load configs and insert new MCP servers into the database
           (idempotent)

        If git clone fails (e.g. no network), falls back to loading from
        any previously copied local files in ``pilot/data/mcp/``.
        """
        try:
            from .default_configs import sync_default_mcps_from_repo
            from .models.models import ServeDao

            dao = ServeDao(self._config)

            repo_url = (
                self._config.default_mcp_repo_url if self._config else None
            )
            if not repo_url:
                logger.info(
                    "Default MCP repo URL is not configured, skipping sync"
                )
                return

            branch = (
                self._config.default_mcp_repo_branch
                if self._config
                else "main"
            )
            mcp_dir = (
                self._config.get_mcp_dir()
                if self._config
                else None
            )
            git_cache_dir = (
                self._config.get_mcp_git_cache_dir()
                if self._config
                else None
            )
            servers_subdir = (
                self._config.default_mcp_servers_subdir
                if self._config
                else "servers"
            )
            overwrite = (
                self._config.default_mcp_overwrite
                if self._config
                else False
            )

            synced = sync_default_mcps_from_repo(
                dao=dao,
                repo_url=repo_url,
                branch=branch,
                mcp_dir=mcp_dir,
                git_cache_dir=git_cache_dir,
                servers_subdir=servers_subdir,
                overwrite=overwrite,
            )
            if synced > 0:
                logger.info(
                    "Synced %d default MCP server(s) from repo %s",
                    synced,
                    repo_url,
                )
        except Exception as e:
            logger.warning(
                "Failed to sync default MCP configs: %s", e, exc_info=True
            )