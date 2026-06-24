"""Knowledge Serve module — wires the knowledge HTTP API into SystemApp."""

from __future__ import annotations

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
    SERVE_SERVICE_COMPONENT_NAME,
    ServeConfig,
)
from .service.service import Service

logger = logging.getLogger(__name__)


class Serve(BaseServe):
    """Serve component for the new knowledge module."""

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
        self._serve_config: Optional[ServeConfig] = config
        self._service: Optional[Service] = None

    def init_app(self, system_app: SystemApp) -> None:
        if self._app_has_initiated:
            return
        self._system_app = system_app
        self._system_app.app.include_router(
            router, prefix=self._api_prefix, tags=self._api_tags
        )
        self._serve_config = self._serve_config or ServeConfig.from_app_config(
            system_app.config, SERVE_CONFIG_KEY_PREFIX
        )
        init_endpoints(self._system_app, self._serve_config)
        self._app_has_initiated = True

    def on_init(self) -> None:
        """Register the Service component."""
        if self._serve_config is None:
            self._serve_config = ServeConfig.from_app_config(
                self._system_app.config, SERVE_CONFIG_KEY_PREFIX
            )
        self._service = Service(self._system_app, self._serve_config)
        self._system_app.register_instance(self._service)
        # Wire the vault factory so built-in knowledge tools can resolve slugs.
        self._service.init_app(self._system_app)

    def after_init(self) -> None:
        """Called before the app starts — nothing to do here for now."""
        pass

    @property
    def service(self) -> Optional[Service]:
        return self._service


__all__ = ["Serve", "APP_NAME", "SERVE_APP_NAME", "SERVE_CONFIG_KEY_PREFIX"]
