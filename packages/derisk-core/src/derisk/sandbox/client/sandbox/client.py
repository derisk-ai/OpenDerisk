import json
import logging
from typing import Optional, Dict, Any

from .types import SandboxResponse

from ..base import BaseClient

logger = logging.getLogger(__name__)


class SandboxClient(BaseClient):

    def get_context(self, *, request_options: Optional[dict] = None) -> SandboxResponse:
        """
        Get sandbox environment information

        Parameters
        ----------
        request_options : typing.Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        HttpResponse[SandboxResponse]
            Successful Response
        """
        pass

    async def apply(self, *, template: Optional[str] = None, time_out: Optional[int] = None,
                    **kwargs) -> SandboxResponse:
        pass

    async def release(self, *, instance_id: str, platform: Optional[str] = None) -> bool:
        pass

    async def set_timeout(
        self,
        instance_id: str,
        timeout: int,
        **kwargs,
    ) -> None:
        pass

    async def connect(
        self,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> bool:
        pass
