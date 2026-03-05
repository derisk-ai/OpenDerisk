import logging
from typing import List, Optional

from derisk.component import SystemApp
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
    """Multimodal serve component."""

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = f"/api/v2/serve/{APP_NAME}",
        api_tags: Optional[List[str]] = None,
    ):
        if api_tags is None:
            api_tags = [SERVE_APP_NAME_HUMP]
        super().__init__(system_app, api_prefix, api_tags)
        self._serve_config: Optional[ServeConfig] = config

    def init_app(self, system_app: SystemApp):
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

    def on_init(self):
        pass

    def after_init(self):
        from .service.service import MultimodalService

        service = MultimodalService.get_instance(self._system_app)
        if not service:
            service = MultimodalService(self._system_app, self._serve_config)
            self._system_app.register_instance(service)

    @classmethod
    def get_instance(cls, system_app: SystemApp) -> Optional["Serve"]:
        return system_app.get_component(SERVE_APP_NAME, Serve)