import logging
from typing import Optional, Dict
from typing_extensions import Unpack,Self
import httpx

from .base import SandboxBase, SandboxOpts
from .client.shell.client import ShellClient

logger = logging.getLogger(__name__)


class AutoSandbox(SandboxBase):
    """
    Use this class to access the different functions within the SDK. You can instantiate any number of clients with different configuration that will propagate to these functions.

    Parameters
    ----------
    base_url : str
        The base url to use for requests from the client.

    headers : Optional[typing.Dict[str, str]]
        Additional headers to send with every request.

    timeout : Optional[float]
        The timeout to be used, in seconds, for requests. By default the timeout is 60 seconds, unless a custom httpx client is used, in which case this default is not enforced.

    follow_redirects : Optional[bool]
        Whether the default httpx client follows redirects or not, this is irrelevant if a custom httpx client is passed in.

    httpx_client : Optional[httpx.AsyncClient]
        The httpx client to use for making requests, a preconfigured client is used by default, however this is useful should you want to pass in any custom httpx configuration.

    Examples
    --------
    from agent_sandbox import AsyncSandbox

    client = Sandbox(
        base_url="https://yourhost.com/path/to/api",
    )
    """

    def __init__(
        self,
        shell: Optional[ShellClient] = None,
        **opts: Unpack[SandboxOpts],

    ):
        super().__init__(**opts)
        self._shell = shell

    @classmethod
    async def create(cls,
                     user_id: str,
                     agent: str,
                     type: Optional[str] = 'local',
                     template: Optional[str] = None,
                     timeout: Optional[int] = None,
                     metadata: Optional[Dict[str, str]] = None,
                     allow_internet_access: bool = True,
                     **kwargs
                     ) -> Self:
        logger.info(f"create sandbox instance:{type},{template},{timeout}")
        # 先给句type 找到对应的sandbox实现
        try:
            from derisk.sandbox.providers.manager import get_sandbox_manager
            sandbox_manager = get_sandbox_manager()
            sandbox_cls = sandbox_manager.get(type)
            sandbox: SandboxBase = await sandbox_cls.create(user_id=user_id,agent=agent, template=template, timeout=timeout, metadata=metadata,
                                                            allow_internet_access=allow_internet_access, **kwargs)

            return sandbox

        except Exception as e:
            logger.exception(f"create sandbox failed!{str(e)}")
            raise
