"""Streaming Configuration Serve Component."""

import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager
from derisk_serve.core import BaseServe

from .service import StreamingConfigService, _service

logger = logging.getLogger(__name__)

SERVE_APP_NAME = "streaming_config"
SERVE_APP_NAME_HUMP = "StreamingConfig"
SERVE_CONFIG_KEY_PREFIX = "streaming_config"


class ServeConfig:
    """Configuration for Streaming Config Serve."""

    __type__ = SERVE_APP_NAME

    def __init__(
        self,
        api_keys: Optional[str] = None,
    ):
        self.api_keys = api_keys


class Serve(BaseServe):
    """Serve component for Streaming Configuration."""

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = None,
        api_tags: Optional[List[str]] = None,
        db_url_or_db: Union[str, URL, DatabaseManager] = None,
        try_create_tables: Optional[bool] = True,
    ):
        if api_tags is None:
            api_tags = [SERVE_APP_NAME_HUMP]
        super().__init__(
            system_app, api_prefix or "", api_tags, db_url_or_db, try_create_tables
        )
        self._db_manager: Optional[DatabaseManager] = None
        self._config = config
        self._service: Optional[StreamingConfigService] = None

    def init_app(self, system_app: SystemApp):
        if self._app_has_initiated:
            return
        self._system_app = system_app
        self._app_has_initiated = True

    def on_init(self):
        pass

    def after_init(self):
        """Initialize database manager and storage after app is ready."""
        from derisk.model.streaming.db_models import StreamingToolConfig
        from derisk.storage.metadata.db_storage import SQLAlchemyStorage
        from derisk.util.serialization.json_serialization import JsonSerializer

        self._db_manager = self.create_or_get_db_manager()

        class StreamingConfigAdapter:
            def to_storage_format(self, obj):
                return obj

            def from_storage_format(self, data):
                return data

        storage = SQLAlchemyStorage(
            self._db_manager,
            StreamingToolConfig,
            StreamingConfigAdapter(),
            JsonSerializer(),
        )

        self._service = StreamingConfigService(storage)

        global _service
        _service = self._service

        logger.info("[StreamingConfig] Serve initialized with storage")

    def get_service(self) -> StreamingConfigService:
        """Get the streaming config service."""
        return self._service
