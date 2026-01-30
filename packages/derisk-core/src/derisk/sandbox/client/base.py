import json
import httpx
from abc import ABC
from typing import Dict, Optional, Any

from httpcore import AsyncConnectionPool

from ..connect.client import AsyncClient
from ..connection_config import ConnectionConfig


class BaseClient(ABC):

    def __init__(
        self,
        connection_config: ConnectionConfig,
        pool: Optional[AsyncConnectionPool] = None,
        envd_api: Optional[httpx.AsyncClient] = None,
        **kwargs
    ) -> None:
        self._connection_config = connection_config

        if pool:
            self.connect = AsyncClient(
                pool=pool,
                base_url=f"{connection_config.api_url}",
                default_headers=connection_config.headers,
                timeout={
                    "read": connection_config.request_timeout
                }
            )
        self._envd_api = envd_api

    @property
    def envd_api(self):
        return self._envd_api

    async def gen_header(self):
        return {}
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        request_timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Helper method to make API requests"""
        if not headers:
            headers = {}
        headers.update(await self.gen_header())

        response = await self.connect.request(
            method,
            endpoint,
            headers=headers,
            data=data,
        )
        return json.loads(response.decode('utf-8'))



