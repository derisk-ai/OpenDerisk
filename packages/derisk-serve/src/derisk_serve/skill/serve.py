import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager, Model, UnifiedDBManagerFactory, db
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
    """Serve component for Skill management

    Examples:

        Register the serve component to the system app

        .. code-block:: python

            from fastapi import FastAPI
            from derisk import SystemApp
            from derisk_serve.skill.serve import Serve

            app = FastAPI()
            system_app = SystemApp(app)
            system_app.register(Serve, api_prefix="/api/v1/serve_skill_service")
            system_app.on_init()
            system_app.before_start()

            skill_service = system_app.get_component(Serve.name, Serve)
    """

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = f"/api/v1/serve_{APP_NAME}_service",
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
        """Called before the start of the application.

        You can do some initialization here.
        """
        # import models to ensure they are registered with SQLAlchemy
        from .models.models import SkillEntity  # noqa: F401
        from .models.skill_sync_task_db import SkillSyncTaskEntity  # noqa: F401
        _ = list(map(lambda x: None, [
            SkillEntity.__tablename__,
            SkillSyncTaskEntity.__tablename__,
        ]))

    def before_start(self):
        """Called before the start of the application.

        You can do some initialization here.
        """
        # Import models to ensure they are registered
        from .models.models import SkillEntity  # noqa: F401
        from .models.skill_sync_task_db import SkillSyncTaskEntity  # noqa: F401

        # Force create tables for SQLite mode
        db_manager_factory: UnifiedDBManagerFactory = self._system_app.get_component(
            "unified_metadata_db_manager_factory",
            UnifiedDBManagerFactory,
            default_component=None,
        )
        if db_manager_factory is not None and db_manager_factory.create():
            init_db = db_manager_factory.create()
        else:
            init_db = db if not self._db_url_or_db else self._db_url_or_db
            from derisk.storage.metadata import DatabaseManager
            init_db = DatabaseManager.build_from(init_db, base=Model)

        try:
            init_db.create_all()
        except Exception as e:
            logger.warning(f"Failed to create Skill tables: {e}")

    async def async_after_start(self):
        """Called after the application has started.
        
        Load default skills from the configured git repository.
        """
        await self._load_default_skills()

    async def _load_default_skills(self):
        """Load default skills from git repository on startup (non-blocking)."""
        from .service.service import Service

        # Check if auto-sync is enabled
        if not getattr(self._config, 'enable_default_skill_sync', True):
            logger.info("Default skill sync is disabled, skipping")
            return

        try:
            service: Service = self._system_app.get_component(
                Service.name, Service
            )
            if not service:
                logger.info("Skill service not available, skipping default skill loading")
                return

            default_repo_url = self._config.get_default_skill_repo_url()
            default_branch = self._config.get_default_skill_repo_branch()

            if not default_repo_url:
                logger.info("No default skill repository URL configured, skipping")
                return
            
            logger.info(f"Starting background sync from default repository: {default_repo_url} (branch: {default_branch})")
            
            task = service.create_sync_task(
                repo_url=default_repo_url,
                branch=default_branch,
                force_update=False
            )
            logger.info(f"Background sync task created: {task.task_id}")
            
        except Exception as e:
            logger.warning(f"Failed to start default skill sync: {e}", exc_info=True)