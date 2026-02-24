from abc import ABC
from typing import Optional, cast, Any, Dict

from .type.active_shell_sessions_result import ActiveShellSessionsResult
from .type.shell_command_result import ShellCommandResult
from .type.shell_create_session_response import ShellCreateSessionResponse
from .type.shell_kill_result import ShellKillResult
from .type.shell_wait_result import ShellWaitResult
from .type.shell_write_result import ShellWriteResult
from ..base import BaseClient
from ...core.response import Response

# this is used as the default value for optional parameters
OMIT = cast(Any, ...)


class ShellClient(BaseClient):

    def __init__(self, sandbox_id: str, work_dir: str, connection_config: Optional[Any] = None, **kwargs):
        super().__init__(connection_config=connection_config, **kwargs)
        self._sandbox_id = sandbox_id
        self._work_dir = work_dir
        self._connection_config = connection_config

    @property
    def work_dir(self) -> str:
        return self._work_dir

    @property
    def sandbox_id(self):
        return self._sandbox_id

    async def exec_command(
        self,
        *,
        command: str,
        work_dir: Optional[str] = OMIT,
        async_mode: Optional[bool] = OMIT,
        timeout: Optional[float] = OMIT,
        terminal_id: Optional[str] = None,
        request_options: Optional[dict] = None,
    ) -> ShellCommandResult:
        """
        Execute command in the specified shell session
        Supports SSE streaming if Accept header contains 'text/event-stream'

        Parameters
        ----------
        command : str
            Shell command to execute

        work_dir : Optional[str]
            Working directory for command execution (must use absolute path)

        async_mode : Optional[bool]
            Whether to execute command asynchronously (default: False for async, False for synchronous execution)

        timeout : Optional[float]
            Maximum time (seconds) to wait for command completion before returning running status

        terminal_id : Optional[str]
            terminal id.

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseShellCommandResult
            Successful Response
        """
        pass

    async def view(self, *, terminal_id: Optional[str] = None, **kwargs) -> ShellCommandResult:
        """
        View output of the specified shell session
        Supports SSE streaming if Accept header contains 'text/event-stream'

        Parameters
        ----------
        terminal_id: str
            Unique identifier of the terminal.

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseShellViewResult
            Successful Response
        """
        pass

    async def wait_for_process(
        self, *, seconds: Optional[int] = OMIT, request_options: Optional[dict] = None
    ) -> ShellWaitResult:
        """
        Wait for the process in the specified shell session to return

        Parameters
        ----------
        seconds : Optional[int]
            Wait time (seconds)

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseShellWaitResult
            Successful Response
        """
        pass

    async def write_to_process(
        self,
        *,
        input: str,
        press_enter: bool,
        request_options: Optional[dict] = None,
        terminal_id: Optional[str] = None,
    ) -> ShellWriteResult:
        """
        Write input to the process in the specified shell session

        Parameters
        ----------
        input : str
            Input content to write to the process

        press_enter : bool
            Whether to press enter key after input

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseShellWriteResult
            Successful Response
        """
        pass

    async def kill_process(
        self, *, request_options: Optional[dict] = None
    ) -> ShellKillResult:
        """
        Terminate the process in the specified shell session

        Parameters
        ----------

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseShellKillResult
            Successful Response
        """
        pass

    async def create_session(
        self,
        *,
        exec_dir: Optional[str] = OMIT,
        request_options: Optional[dict] = None,
    ) -> ShellCreateSessionResponse:
        """
        Create a new shell session and return its ID
        If id already exists, return the existing session

        Parameters
        ----------
        id : Optional[str]
            Unique identifier for the shell session, auto-generated if not provided

        exec_dir : Optional[str]
            Working directory for the new session (must use absolute path)

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseShellCreateSessionResponse
            Successful Response
        """
        pass

    async def get_terminal_url(self, *, request_options: Optional[dict] = None) -> str:
        """
        Create a new shell session and return the terminal URL

        Parameters
        ----------
        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseStr
            Successful Response
        """
        pass

    async def list_sessions(self, *, request_options: Optional[dict] = None) -> ActiveShellSessionsResult:
        """
        List all active shell sessions

        Parameters
        ----------
        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        ResponseActiveShellSessionsResult
            Successful Response
        """
        pass

    async def cleanup_all_sessions(self, *, request_options: Optional[dict] = None) -> Dict:
        """
        Cleanup all active shell sessions

        Parameters
        ----------
        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        Response
            Successful Response
        """
        pass

    async def cleanup_session(
        self, *, request_options: Optional[dict] = None
    ) -> Dict:
        """
        Manually cleanup a specific shell session

        Parameters
        ----------
        session_id : str

        request_options : Optional[RequestOptions]
            Request-specific configuration.

        Returns
        -------
        Response
            Successful Response
        """
        pass
