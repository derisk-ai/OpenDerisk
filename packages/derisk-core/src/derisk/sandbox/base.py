import asyncio
import datetime
import json
import logging
import os
import posixpath
from dataclasses import dataclass

from typing_extensions import Unpack, Self

from typing import TypedDict, Optional, Dict, List
from httpx import Limits
from httpcore import AsyncConnectionPool

from .client.browser.client import BrowserClient
from .client.file.client import FileClient
from .client.sandbox.types import SandboxDetail
from .client.shell.client import ShellClient
from .connection_config import ConnectionConfig, ApiParams
from .type.sandbox_api import SandboxInfo, SandboxMetrics


ENVD_API_FILES_ROUTE = "/files"
ENVD_API_HEALTH_ROUTE = "/health"
DEFAULT_WORK_DIR = "/home/ubuntu"
DEFAULT_SKILL_DIR = None

logger = logging.getLogger(__name__)


class SandboxOpts(TypedDict):
    sandbox_id: str
    pool: Optional[AsyncConnectionPool]
    sandbox_domain: Optional[str]
    connection_config: Optional[ConnectionConfig]


class SandboxSession:
    pass


@dataclass
class MachineInfo:
    os: Optional[str] = None
    python: Optional[str] = None
    node: Optional[str] = None


class SandboxBase:
    _limits = Limits(
        max_keepalive_connections=40,
        max_connections=40,
        keepalive_expiry=300,
    )

    envd_port = 49983

    default_sandbox_timeout = 300

    def __init__(
        self,
        sandbox_id: str,
        user_id: str,
        agent: str,
        conversation_id: Optional[str] = None,
        sandbox_domain: Optional[str] = None,
        sandbox_detail: Optional[SandboxDetail] = None,
        work_dir: Optional[str] = DEFAULT_WORK_DIR,
        enable_skill: Optional[bool] = True,
        skill_dir: Optional[str] = DEFAULT_SKILL_DIR,
        connection_config: Optional[ConnectionConfig] = None,
        **kwargs,
    ):
        self.__connection_config = connection_config
        self.__sandbox_id = sandbox_id
        self.__user_id = user_id
        self.__agent = agent
        self.__detail = sandbox_detail
        self.__sandbox_domain = sandbox_domain or (
            connection_config.domain if connection_config else None
        )
        self.__work_dir = work_dir or DEFAULT_WORK_DIR
        self.__enable_skill = enable_skill

        if skill_dir is None:
            try:
                from derisk.configs.model_config import DATA_DIR

                skill_dir = os.path.join(DATA_DIR, "skill")
            except ImportError:
                logger.warning(
                    "Failed to import DATA_DIR, skill_dir will need to be set explicitly"
                )
                skill_dir = None

        self.__skill_dir = skill_dir
        self.__conversation_id = conversation_id
        self._shell: Optional[ShellClient] = None
        self._file: Optional[FileClient] = None
        self._browser: Optional[BrowserClient] = None

    @classmethod
    def provider(cls):
        raise NotImplementedError

    @property
    def user_id(self):
        return self.__user_id

    @property
    def agent(self) -> str:
        return self.__agent

    @property
    def detail(self) -> Optional[SandboxDetail]:
        return self.__detail

    @property
    def work_dir(self) -> str:
        return self.__work_dir

    @property
    def skill_dir(self) -> str:
        if self.__skill_dir:
            return self.__skill_dir
        # Dynamic fallback: try to get from DATA_DIR
        try:
            from derisk.configs.model_config import DATA_DIR

            return os.path.join(DATA_DIR, "skill")
        except ImportError:
            logger.warning("DATA_DIR not available, returning empty skill_dir")
            return ""

    @property
    def enable_skill(self) -> Optional[bool]:
        return self.__enable_skill

    @property
    def sandbox_id(self) -> str:
        """
        Unique identifier of the sandbox.
        """
        return self.__sandbox_id

    @property
    def sandbox_domain(self) -> Optional[str]:
        return self.__sandbox_domain

    @property
    def connection_config(self) -> Optional[ConnectionConfig]:
        return self.__connection_config

    @property
    def conversation_id(self) -> Optional[str]:
        return self.__conversation_id

    @property
    def shell(self) -> Optional[ShellClient]:
        return self._shell

    @property
    def file(self) -> Optional[FileClient]:
        return self._file

    @property
    def browser(self) -> Optional[BrowserClient]:
        return self._browser

    def set_work_dir(self, work_dir: str) -> None:
        self.__work_dir = work_dir

    def set_conversation_id(self, conversation_id: Optional[str]) -> None:
        self.__conversation_id = conversation_id

    @classmethod
    async def create(
        cls,
        user_id: str,
        agent: str,
        template: Optional[str] = None,
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
        allow_internet_access: bool = True,
        **kwargs,
    ) -> Self:
        """
        Create a new sandbox.

        By default, the sandbox is created from the default `base` sandbox template.

        :param template: Sandbox template name or ID
        :param timeout: Timeout for the sandbox in **seconds**, default to 300 seconds. The maximum time a sandbox can be kept alive is 24 hours (86_400 seconds) for Pro users and 1 hour (3_600 seconds) for Hobby users.
        :param metadata: Custom metadata for the sandbox
        :param envs: Custom environment variables for the sandbox
        :param secure: Envd is secured with access token and cannot be used without it, defaults to `True`.
        :param allow_internet_access: Allow sandbox to access the internet, defaults to `True`.
        :param mcp: MCP server to enable in the sandbox

        :return: A Sandbox instance for the new sandbox

        Use this method instead of using the constructor to create a new sandbox.
        """
        raise NotImplementedError

    @classmethod
    async def recovery(
        cls,
        user_id: str,
        agent: str,
        conversation_id: str,
        template: Optional[str] = None,
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
        allow_internet_access: bool = True,
        workspace_path: Optional[str] = None,
        **kwargs,
    ) -> Self:
        """
        恢复当前对话的沙箱环境
        """
        sandbox: Self = await cls.create(
            user_id=user_id,
            agent=agent,
            template=template,
            timeout=timeout,
            metadata=metadata,
            allow_internet_access=allow_internet_access,
            **kwargs,
        )
        sandbox.set_conversation_id(conversation_id)

        raw_path = (workspace_path or "").strip()
        if raw_path:
            base_dir = (
                raw_path
                if raw_path.startswith("/")
                else posixpath.join(DEFAULT_WORK_DIR, raw_path)
            )
        else:
            base_dir = DEFAULT_WORK_DIR
        workspace_root = posixpath.normpath(base_dir.rstrip("/") or "/") or "/"

        sandbox.set_work_dir(workspace_root)

        if sandbox.file is None:
            logger.warning("File client not initialized, skipping OSS recovery")
            return sandbox

        conv_id = str(conversation_id)
        storage_prefix = sandbox.file.build_oss_path(f"conversations/{conv_id}").rstrip(
            "/"
        )

        result = sandbox.file.oss.generate_directory_download_urls(
            oss_prefix=storage_prefix
        )
        file_entries = result.get("file_urls") or []
        if not file_entries:
            logger.info(
                "未在 OSS 中找到需要恢复的文件, conversation_id=%s, prefix=%s",
                conversation_id,
                storage_prefix,
            )
            return sandbox

        tasks = []
        for item in file_entries:
            relative_path = (item.get("relative_path") or "").strip()
            if not relative_path:
                continue
            target_path = posixpath.normpath(
                posixpath.join(workspace_root, relative_path)
            )
            target_dir = posixpath.dirname(target_path)
            tasks.append(
                sandbox.file.download_to_local(
                    item.get("url"),
                    filename=posixpath.basename(target_path),
                    path=target_dir,
                )
            )

        if tasks:
            await asyncio.gather(*tasks)
        logger.info(
            "已从 OSS 恢复 conversation_id=%s 的工作目录，prefix=%s",
            conversation_id,
            storage_prefix,
        )

        logger.info(f"recovery result:{json.dumps(result, ensure_ascii=False)} ")
        return sandbox

    async def is_running(self, request_timeout: Optional[float] = None) -> bool:
        """
        Check if the sandbox is running.

        :param request_timeout: Timeout for the request in **seconds**

        :return: `True` if the sandbox is running, `False` otherwise

        Example
        ```python
        sandbox = await AsyncSandbox.create()
        await sandbox.is_running()  # Returns True

        await sandbox.kill()
        await sandbox.is_running()  # Returns False
        ```
        """
        ...

    async def connect(
        self,
        timeout: Optional[int] = None,
        **opts: Unpack[ApiParams],
    ) -> Self:
        """
        Connect to a sandbox. If the sandbox is paused, it will be automatically resumed.
        Sandbox must be either running or be paused.

        With sandbox ID you can connect to the same sandbox from different places or environments (serverless functions, etc).

        :param timeout: Timeout for the sandbox in **seconds**
        :return: A running sandbox instance

        @example
        ```python
        sandbox = await AsyncSandbox.create()
        await sandbox.beta_pause()

        # Another code block
        same_sandbox = await sandbox.connect()
        ```
        """
        ...

    async def kill(
        self,
        template: Optional[str] = None,
    ) -> bool:
        """
        Kill the sandbox.

        :return: `True` if the sandbox was killed, `False` if the sandbox was not found
        """
        ...

    async def set_timeout(self, instance_id: str, timeout: int, **kwargs) -> None:
        """
        Set the timeout of the sandbox.
        After the timeout expires, the sandbox will be automatically killed.
        This method can extend or reduce the sandbox timeout set when creating the sandbox or from the last call to `.set_timeout`.

        The maximum time a sandbox can be kept alive is 24 hours (86_400 seconds) for Pro users and 1 hour (3_600 seconds) for Hobby users.

        :param timeout: Timeout for the sandbox in **seconds**
        """
        ...

    async def get_info(
        self,
        **opts: Unpack[ApiParams],
    ) -> SandboxInfo:
        """
        Get sandbox information like sandbox ID, template, metadata, started at/end at date.

        :return: Sandbox info
        """
        ...

    async def get_metrics(
        self,
        start: Optional[datetime.datetime] = None,
        end: Optional[datetime.datetime] = None,
        **opts: Unpack[ApiParams],
    ) -> List[SandboxMetrics]:
        """
        Get the metrics of the current sandbox.

        :param start: Start time for the metrics, defaults to the start of the sandbox
        :param end: End time for the metrics, defaults to the current time

        :return: List of sandbox metrics containing CPU, memory and disk usage information
        """
        ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.kill(self.sandbox_id)
