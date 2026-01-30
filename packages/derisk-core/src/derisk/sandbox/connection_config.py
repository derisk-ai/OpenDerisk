import os

from typing import Optional, Dict, TypedDict
from httpx._types import ProxyTypes
from httpx._config import Limits
from typing_extensions import Unpack

REQUEST_TIMEOUT: float = 60.0  # 60 seconds

KEEPALIVE_PING_INTERVAL_SEC = 50  # 50 seconds
KEEPALIVE_PING_HEADER = "Keepalive-Ping-Interval"


class ApiParams(TypedDict, total=False):
    """
    Parameters for a request.

    In the case of a sandbox, it applies to all **requests made to the returned sandbox**.
    """
    sandbox_id: str
    request_timeout: Optional[float]
    headers: Optional[Dict[str, str]]
    domain: Optional[str]
    api_url: Optional[str]
    debug: Optional[bool]


class ConnectionConfig:
    """
    Configuration for the connection to the API.
    """

    def __init__(
        self,
        api_url: str,
        domain: Optional[str] = None,
        debug: Optional[bool] = None,
        limits: Optional[Limits] = None,
        access_token: Optional[str] = None,
        request_timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        extra_sandbox_headers: Optional[Dict[str, str]] = None,
        proxy: Optional[ProxyTypes] = None,
    ):
        self.domain = domain
        self.debug = debug
        self.limits = limits if limits else Limits(max_connections=100, max_keepalive_connections=50)
        self.access_token = access_token
        self.headers = headers or {}
        self.__extra_sandbox_headers = extra_sandbox_headers or {}

        self.proxy = proxy

        self.request_timeout = ConnectionConfig._get_request_timeout(
            REQUEST_TIMEOUT,
            request_timeout,
        )

        if request_timeout == 0:
            self.request_timeout = None
        elif request_timeout is not None:
            self.request_timeout = request_timeout
        else:
            self.request_timeout = REQUEST_TIMEOUT

        self.api_url = (
            api_url
        )

    @staticmethod
    def _get_request_timeout(
        default_timeout: Optional[float],
        request_timeout: Optional[float],
    ):
        if request_timeout == 0:
            return None
        elif request_timeout is not None:
            return request_timeout
        else:
            return default_timeout

    def get_request_timeout(self, request_timeout: Optional[float] = None):
        return self._get_request_timeout(self.request_timeout, request_timeout)

    @property
    def sandbox_headers(self):
        """
        We need this separate as we use the same header for E2B access token to API and envd access token to sandbox.
        """
        return {
            **self.headers,
            **self.__extra_sandbox_headers,
        }


Username = str
"""
User used for the operation in the sandbox.
"""

default_username: Username = "user"
"""
Default user used for the operation in the sandbox.
"""
