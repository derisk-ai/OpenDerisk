import ipaddress
import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.core.interface.file import FileStorageClient, FileStorageURI
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
    """Serve component for DB-GPT"""

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = f"/api/v2/serve/{APP_NAME}",
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

        self._db_manager: Optional[DatabaseManager] = None
        self._file_storage_client: Optional[FileStorageClient] = None
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
        """Called when init the application.

        You can do some initialization here. You can't get other components here
        because they may be not initialized yet
        """
        # import your own module here to ensure the module is loaded before the
        # application starts
        from .models.models import ServeEntity as _  # noqa: F401

    def after_init(self):
        """Called before the start of the application."""
        from derisk.core.interface.file import (
            FileStorageSystem,
            SimpleDistributedStorage,
        )
        from derisk.storage.metadata.db_storage import SQLAlchemyStorage
        from derisk.util.serialization.json_serialization import JsonSerializer

        from .models.file_adapter import FileMetadataAdapter
        from .models.models import ServeEntity

        self._db_manager = self.create_or_get_db_manager()
        serializer = JsonSerializer()
        storage = SQLAlchemyStorage(
            self._db_manager,
            ServeEntity,
            FileMetadataAdapter(),
            serializer,
        )
        default_backend = self._serve_config.default_backend
        simple_distributed_storage = SimpleDistributedStorage(
            node_address=self._serve_config.get_node_address(),
            local_storage_path=self._serve_config.get_local_storage_path(),
            save_chunk_size=self._serve_config.save_chunk_size,
            transfer_chunk_size=self._serve_config.transfer_chunk_size,
            transfer_timeout=self._serve_config.transfer_timeout,
        )
        storage_backends = {
            simple_distributed_storage.storage_type: simple_distributed_storage,
        }
        for backend_config in self._serve_config.backends:
            storage_backend = backend_config.create_storage()
            storage_backends[storage_backend.storage_type] = storage_backend
            if not default_backend:
                # First backend is the default backend
                default_backend = storage_backend.storage_type
        if not default_backend:
            default_backend = simple_distributed_storage.storage_type

        fs = FileStorageSystem(
            storage_backends,
            metadata_storage=storage,
            check_hash=self._serve_config.check_hash,
        )
        self._file_storage_client = FileStorageClient(
            system_app=self._system_app,
            storage_system=fs,
            save_chunk_size=self._serve_config.save_chunk_size,
            default_storage_type=default_backend,
        )
        self._system_app.register_instance(self._file_storage_client)

        try:
            import fsspec

            from .service.fsspec_impl import DeriskFileSystem

            fsspec.register_implementation("derisk-fs", DeriskFileSystem)
        except ImportError:
            pass

    @property
    def file_storage_client(self) -> FileStorageClient:
        """Returns the file storage client."""
        if not self._file_storage_client:
            raise ValueError("File storage client is not initialized")
        return self._file_storage_client

    def replace_uri(self, uri: str) -> str:
        """Replace the uri with the new uri"""

        def _is_public_host(host: str) -> bool:
            """Return True if host looks like a public hostname/IP."""
            if not host:
                return False
            host = host.strip().lower()
            if host in ("localhost", "0.0.0.0"):
                return False
            try:
                addr = ipaddress.ip_address(host)
                # Any IP address (public or private) is usable as long as it is not
                # loopback/link-local. Private RFC1918 IPs may be valid in intranet
                # deployments, so we only reject clearly non-routable addresses.
                return not (addr.is_loopback or addr.is_link_local or addr.is_unspecified)
            except ValueError:
                # Not an IP address -> treat as a hostname/domain name (public enough)
                return True

        def _rewrite_file_api_url(url: str) -> str:
            """Rewrite absolute file-API URLs that point to a non-routable host.

            Storage backends such as SimpleDistributedStorage may return
            ``http://0.0.0.0:7777/api/v2/serve/file/files/...``. When the host is
            not public, convert to a relative URL so browsers use the host they
            are currently accessing.
            """
            try:
                from urllib.parse import urlparse

                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https"):
                    return url
                api_prefix = (
                    self._api_prefix[0]
                    if isinstance(self._api_prefix, list)
                    else self._api_prefix
                )
                if not parsed.path.startswith(f"{api_prefix}/"):
                    return url
                if _is_public_host(parsed.hostname or ""):
                    return url
                query = f"?{parsed.query}" if parsed.query else ""
                return f"{parsed.path}{query}"
            except Exception:
                return url

        try:
            new_uri = self.file_storage_client.get_public_url(uri)
            new_uri = _rewrite_file_api_url(new_uri)
            if new_uri != uri:
                return new_uri
            # If the uri is not changed, replace it with the new uri
            parsed_uri = FileStorageURI.parse(uri)
            bucket, file_id = parsed_uri.bucket, parsed_uri.file_id
            api_prefix = (
                self._api_prefix[0]
                if isinstance(self._api_prefix, list)
                else self._api_prefix
            )
            node_address = self._serve_config.get_node_address()
            host, _sep, _port = node_address.partition(":")
            if _is_public_host(host):
                return f"http://{node_address}{api_prefix}/files/{bucket}/{file_id}"
            # Use a relative URL so the browser uses whatever host it is currently
            # accessing. This avoids broken absolute URLs like http://0.0.0.0:7777
            # when the service is deployed behind a reverse proxy or on a remote host.
            # If an absolute public URL is required (e.g. for external LLM providers),
            # configure derisk.serve.file.host to the public hostname/IP.
            return f"{api_prefix}/files/{bucket}/{file_id}"
        except Exception as _e:
            return uri
