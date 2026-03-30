"""
Improved Local Sandbox Provider with Full Feature Support

Replaces the original LocalSandbox with:
- Proper security isolation (macOS sandbox-exec, Linux resource limits)
- Real Playwright browser integration
- Complete SandboxBase interface implementation
- TOML configuration support
- Better session and process management
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from derisk.configs.model_config import DATA_DIR
from derisk.sandbox.base import SandboxBase, SandboxOpts
from derisk.sandbox.client.sandbox.types import SandboxDetail
from derisk.sandbox.providers.base import (
    SessionConfig,
    ExecutionResult,
    ExecutionStatus,
)
from derisk_ext.sandbox.local.improved_runtime import (
    ImprovedLocalSandboxRuntime,
    ImprovedLocalSandboxSession,
    get_platform,
)
from derisk_ext.sandbox.local.shell_client import LocalShellClient
from derisk_ext.sandbox.local.file_client import LocalFileClient
from derisk_ext.sandbox.local.playwright_browser_client import (
    PlaywrightBrowserClient,
    BrowserConfig,
)

logger = logging.getLogger(__name__)

# Default directories for local sandbox (under DATA_DIR)
DEFAULT_LOCAL_SANDBOX_SKILL_DIR = os.path.join(DATA_DIR, "skill")
DEFAULT_LOCAL_SANDBOX_WORK_DIR = os.path.join(DATA_DIR, "workspace")


@dataclass
class LocalSandboxConfig:
    """Configuration for local sandbox provider."""

    # Runtime settings
    work_dir: str = DEFAULT_LOCAL_SANDBOX_WORK_DIR
    skill_dir: str = DEFAULT_LOCAL_SANDBOX_SKILL_DIR
    runtime_id: str = "improved_local_runtime"

    # Execution settings
    default_timeout: int = 300  # seconds
    max_memory: int = 256 * 1024 * 1024  # 256MB
    max_cpus: int = 1

    # Security settings
    use_sandbox_exec: Optional[bool] = None  # None = auto-detect
    allow_network: bool = True
    network_disabled: bool = False

    # Browser settings
    browser_type: str = "chromium"
    browser_headless: bool = True
    browser_viewport: Dict[str, int] = None

    # Resource limits
    max_sessions: int = 10
    session_idle_timeout: int = 3600  # 1 hour

    # Git sync settings
    enable_git_sync: bool = False
    git_sync_timeout: int = 5  # seconds

    def __post_init__(self):
        if self.browser_viewport is None:
            self.browser_viewport = {"width": 1280, "height": 720}

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "LocalSandboxConfig":
        """Create config from dictionary (e.g., from TOML)."""
        return cls(
            work_dir=config_dict.get("work_dir", DEFAULT_LOCAL_SANDBOX_WORK_DIR),
            skill_dir=config_dict.get("skill_dir", DEFAULT_LOCAL_SANDBOX_SKILL_DIR),
            runtime_id=config_dict.get("runtime_id", "improved_local_runtime"),
            default_timeout=config_dict.get("default_timeout", 300),
            max_memory=config_dict.get("max_memory", 256 * 1024 * 1024),
            max_cpus=config_dict.get("max_cpus", 1),
            use_sandbox_exec=config_dict.get("use_sandbox_exec"),
            allow_network=config_dict.get("allow_network", True),
            network_disabled=config_dict.get("network_disabled", False),
            browser_type=config_dict.get("browser_type", "chromium"),
            browser_headless=config_dict.get("browser_headless", True),
            browser_viewport=config_dict.get(
                "browser_viewport", {"width": 1280, "height": 720}
            ),
            max_sessions=config_dict.get("max_sessions", 10),
            session_idle_timeout=config_dict.get("session_idle_timeout", 3600),
            enable_git_sync=config_dict.get("enable_git_sync", False),
            git_sync_timeout=config_dict.get("git_sync_timeout", 5),
        )

    def to_session_config(self) -> SessionConfig:
        """Convert to SessionConfig for the runtime."""
        return SessionConfig(
            language="python",
            timeout=self.default_timeout,
            max_memory=self.max_memory,
            max_cpus=self.max_cpus,
            working_dir=self.work_dir,
            network_disabled=self.network_disabled or not self.allow_network,
        )


class ImprovedLocalSandbox(SandboxBase):
    """
    Improved Local Sandbox Provider with complete implementation.

    Features:
    - macOS sandbox-exec integration for security isolation
    - Real Playwright browser automation
    - Full SandboxBase interface implementation
    - Proper session lifecycle management
    - Resource monitoring and limits
    """

    # Singleton runtime instance
    _shared_runtime: Optional[ImprovedLocalSandboxRuntime] = None
    _runtime_lock = asyncio.Lock()

    def __init__(self, **kwargs):
        config_dict = kwargs.get("local_sandbox_config", {})
        self._config = LocalSandboxConfig.from_dict(config_dict)

        self._file_storage_client = kwargs.get("file_storage_client")

        super().__init__(
            sandbox_id=kwargs.get("sandbox_id", ""),
            user_id=kwargs.get("user_id", "default"),
            agent=kwargs.get("agent", "default_agent"),
            conversation_id=kwargs.get("conversation_id"),
            sandbox_domain=kwargs.get("sandbox_domain"),
            sandbox_detail=kwargs.get("sandbox_detail"),
            work_dir=self._config.work_dir,
            enable_skill=kwargs.get("enable_skill", True),
            skill_dir=kwargs.get("skill_dir", self._config.skill_dir),
            connection_config=None,
        )

        self._runtime: Optional[ImprovedLocalSandboxRuntime] = None
        self._session: Optional[ImprovedLocalSandboxSession] = None

        self._shell: Optional[LocalShellClient] = None
        self._file: Optional[LocalFileClient] = None
        self._browser: Optional[PlaywrightBrowserClient] = None

        self._is_running = False
        self._created_at: Optional[float] = None
        self._timeout_at: Optional[float] = None
        self._metadata: Dict[str, str] = kwargs.get("metadata", {})

        self._enable_browser = kwargs.get("enable_browser", True)

    @classmethod
    def provider(cls) -> str:
        """Provider identifier."""
        return "local"

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
    ) -> "ImprovedLocalSandbox":
        """
        Create a new local sandbox instance.

        This is the factory method that should be used to create sandbox instances.
        """
        # Generate a unique sandbox ID
        sandbox_id = f"local_{user_id}_{agent}_{int(time.time() * 1000)}"

        # Apply template if specified
        if template:
            kwargs["template"] = template

        # Set timeout
        if timeout:
            kwargs["timeout"] = timeout

        # Set metadata
        if metadata:
            kwargs.update({"metadata": metadata})

        # Set network access
        kwargs.setdefault("local_sandbox_config", {})
        kwargs["local_sandbox_config"]["allow_network"] = allow_internet_access

        # Set work_dir if provided and not None (from kwargs)
        if "work_dir" in kwargs and kwargs["work_dir"] is not None:
            kwargs["local_sandbox_config"]["work_dir"] = kwargs["work_dir"]

        # Set skill_dir if provided and not None (from kwargs)
        if "skill_dir" in kwargs and kwargs["skill_dir"] is not None:
            kwargs["local_sandbox_config"]["skill_dir"] = kwargs["skill_dir"]

        # Create instance
        instance = cls(sandbox_id=sandbox_id, user_id=user_id, agent=agent, **kwargs)

        # Initialize the sandbox
        await instance._initialize()

        return instance

    async def _initialize(self) -> None:
        """Initialize the sandbox runtime and session."""
        # Sync skills from git repos on startup
        await self._sync_skills_from_git_repos()

        # Get or create shared runtime
        async with self.__class__._runtime_lock:
            if self.__class__._shared_runtime is None:
                self.__class__._shared_runtime = ImprovedLocalSandboxRuntime(
                    runtime_id=self._config.runtime_id
                )
                logger.info(f"Created shared runtime: {self._config.runtime_id}")
                # Start periodic cleanup
                asyncio.create_task(self._periodic_cleanup())

        self._runtime = self.__class__._shared_runtime

        # Create session
        session_config = self._config.to_session_config()
        if timeout_value := self._metadata.get("timeout"):
            try:
                session_config.timeout = int(timeout_value)
            except (ValueError, TypeError):
                pass

        self._session = await self._runtime.create_session(
            self.sandbox_id, session_config
        )

        # Initialize clients
        await self._init_clients()

        # Set state
        self._is_running = True
        self._created_at = time.time()

        # Set timeout if specified
        if timeout_value := self._metadata.get("timeout"):
            try:
                timeout = int(timeout_value)
                self._timeout_at = self._created_at + timeout
            except (ValueError, TypeError):
                pass

        logger.info(
            f"Initialized local sandbox {self.sandbox_id} for user {self.user_id}"
        )

    async def _init_clients(self) -> None:
        """Initialize the file, shell, and browser clients."""
        if not self._session or not self._runtime:
            raise RuntimeError("Session not initialized")

        work_dir = self._config.work_dir
        skill_dir = self._config.skill_dir

        self._file = LocalFileClient(
            sandbox_id=self.sandbox_id,
            work_dir=work_dir,
            runtime=self._runtime,
            skill_dir=skill_dir,
            file_storage_client=self._file_storage_client,
        )

        # Shell client
        self._shell = LocalShellClient(
            sandbox_id=self.sandbox_id,
            work_dir=work_dir,
            runtime=self._runtime,
            skill_dir=skill_dir,
        )

        # Browser client (if enabled)
        if self._enable_browser:
            browser_config = BrowserConfig(
                browser_type=self._config.browser_type,
                headless=self._config.browser_headless,
                viewport=self._config.browser_viewport,
            )
            self._browser = PlaywrightBrowserClient(
                instance_id=self.sandbox_id,
                runtime=self._runtime,
                browser_config=browser_config,
            )
        else:
            # Use stub browser if disabled
            from derisk_ext.sandbox.local.browser_client import LocalBrowserClient

            self._browser = LocalBrowserClient(
                instance_id=self.sandbox_id, runtime=self._runtime
            )

    async def _sync_skills_from_git_repos(self) -> None:
        """Sync skills from git repositories on sandbox startup.

        This method scans the skill_dir for git repositories and pulls updates
        from their remote origins. It also tries to sync from database-tracked
        repos if available.
        """
        if not self._config.enable_git_sync:
            logger.debug("Git sync disabled, skipping")
            return

        skill_dir = self._config.skill_dir

        if not skill_dir or not os.path.exists(skill_dir):
            logger.info(
                f"Skill directory does not exist, skipping git sync: {skill_dir}"
            )
            return

        try:
            from git import Repo, GitCommandError
        except ImportError:
            logger.warning("GitPython not installed, skipping git sync")
            return

        async def _do_sync():
            synced_count = 0
            failed_count = 0

            try:
                synced_from_db = await self._sync_from_database_tracked_repos()
                synced_count += synced_from_db
            except Exception as e:
                logger.warning(f"Failed to sync from database-tracked repos: {e}")

            try:
                for entry in os.scandir(skill_dir):
                    if entry.is_dir():
                        git_dir = os.path.join(entry.path, ".git")
                        if os.path.exists(git_dir):
                            try:
                                repo = Repo(entry.path)
                                if repo.remotes.origin:
                                    logger.info(
                                        f"Pulling updates for skill: {entry.name}"
                                    )
                                    repo.remotes.origin.pull()
                                    synced_count += 1
                                    logger.info(
                                        f"Successfully synced skill: {entry.name}"
                                    )
                            except GitCommandError as e:
                                logger.warning(
                                    f"Failed to pull updates for {entry.name}: {e}"
                                )
                                failed_count += 1
                            except Exception as e:
                                logger.warning(
                                    f"Error processing git repo {entry.name}: {e}"
                                )
                                failed_count += 1
            except Exception as e:
                logger.warning(f"Error scanning skill directory for git repos: {e}")

            if synced_count > 0 or failed_count > 0:
                logger.info(
                    f"Skill sync completed: {synced_count} synced, {failed_count} failed"
                )

        try:
            await asyncio.wait_for(_do_sync(), timeout=self._config.git_sync_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Git sync timed out after {self._config.git_sync_timeout}s, skipping"
            )

    async def _sync_from_database_tracked_repos(self) -> int:
        """Sync skills from database-tracked git repositories.

        This method queries the skill database for skills with repo_url
        and syncs them using the skill service.

        Returns:
            Number of skills synced
        """
        try:
            from derisk.agent.resource.manage import _SYSTEM_APP

            if not _SYSTEM_APP:
                return 0

            from derisk_serve.skill.service.service import (
                Service,
                SKILL_SERVICE_COMPONENT_NAME,
            )
            from derisk_serve.skill.api.schemas import SkillQueryFilter

            service: Service = _SYSTEM_APP.get_component(
                SKILL_SERVICE_COMPONENT_NAME, Service, default=None
            )

            if not service:
                return 0

            filter_request = SkillQueryFilter(filter="")
            query_result = service.filter_list_page(
                filter_request, page=1, page_size=1000
            )

            repo_urls = set()
            for skill in query_result.items:
                if skill.repo_url:
                    repo_urls.add((skill.repo_url, skill.branch or "main"))

            synced_count = 0
            for repo_url, branch in repo_urls:
                try:
                    await service.sync_from_git(repo_url, branch, force_update=False)
                    synced_count += 1
                except Exception as e:
                    logger.warning(f"Failed to sync from {repo_url}: {e}")

            return synced_count

        except ImportError:
            logger.debug("derisk_serve not available, skipping database-tracked sync")
            return 0
        except Exception as e:
            logger.warning(f"Error syncing from database-tracked repos: {e}")
            return 0

    async def _periodic_cleanup(self) -> None:
        """Periodically cleanup expired sessions."""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                if self._runtime:
                    await self._runtime.cleanup_expired_sessions(
                        max_idle_time=self._config.session_idle_timeout
                    )
            except Exception as e:
                logger.warning(f"Periodic cleanup error: {e}")

    async def run_code(self, code: str, language: str = "python") -> str:
        """Run code in the sandbox."""
        if not self._session:
            raise RuntimeError("Session not initialized")

        result = await self._session.execute(code)

        if result.status == ExecutionStatus.SUCCESS:
            return result.output
        elif result.status == ExecutionStatus.TIMEOUT:
            return f"Timeout after {result.execution_time}s: {result.error}"
        else:
            return (
                f"Error (exit code {result.exit_code}): {result.error}\n{result.output}"
            )

    async def install_dependencies(self, dependencies: List[str]) -> bool:
        """Install Python dependencies in the sandbox."""
        if not self._session:
            return False

        result = await self._session.install_dependencies(dependencies)
        return result.status == ExecutionStatus.SUCCESS

    async def get_state(self) -> str:
        """Get the current state of the sandbox."""
        if not self._session:
            return "stopped"
        return "running" if self._is_running else "stopped"

    # SandboxBase interface methods

    async def is_running(self, request_timeout: Optional[float] = None) -> bool:
        """Check if the sandbox is running."""
        if not self._session:
            return False

        # Check if session is still active
        if not self._session.is_active:
            self._is_running = False
            return False

        # Check timeout
        if self._timeout_at and time.time() > self._timeout_at:
            await self.kill()
            return False

        return self._is_running

    async def connect(
        self, timeout: Optional[int] = None, **opts
    ) -> "ImprovedLocalSandbox":
        """Connect to an existing sandbox instance."""
        # For local sandbox, we just need to ensure it's still running
        if not await self.is_running():
            # Try to recover
            if self.sandbox_id in (self._runtime.sessions if self._runtime else {}):
                self._session = self._runtime.sessions[self.sandbox_id]
                self._is_running = True
            else:
                raise RuntimeError(f"Sandbox {self.sandbox_id} not found or stopped")

        return self

    async def kill(self, template: Optional[str] = None) -> bool:
        """Kill the sandbox."""
        if self._runtime and self.sandbox_id:
            success = await self._runtime.destroy_session(self.sandbox_id)
            self._is_running = False
            self._session = None
            return success
        return False

    async def close(self, template: Optional[str] = None) -> bool:
        """Close the sandbox (alias for kill)."""
        return await self.kill(template)

    async def set_timeout(self, instance_id: str, timeout: int, **kwargs) -> None:
        """Set the timeout for the sandbox."""
        if self._created_at:
            self._timeout_at = self._created_at + timeout

    async def get_info(self, **opts) -> Dict[str, Any]:
        """Get sandbox information."""
        return {
            "sandbox_id": self.sandbox_id,
            "provider": self.provider(),
            "user_id": self.user_id,
            "agent": self.agent,
            "conversation_id": self.conversation_id,
            "work_dir": self.work_dir,
            "skill_dir": self.skill_dir,
            "is_running": await self.is_running(),
            "created_at": self._created_at,
            "timeout_at": self._timeout_at,
            "metadata": self._metadata,
            "config": {
                "max_memory": self._config.max_memory,
                "max_cpus": self._config.max_cpus,
                "allow_network": self._config.allow_network,
            },
            "session_status": await self._session.get_status() if self._session else {},
        }

    async def get_metrics(
        self, start: Optional[float] = None, end: Optional[float] = None, **opts
    ) -> List[Dict[str, Any]]:
        """Get sandbox metrics."""
        if not self._session:
            return []

        session_status = await self._session.get_status()
        resources = session_status.get("resources", {})

        return [
            {
                "timestamp": time.time(),
                "memory": resources.get("peak_memory", 0),
                "cpu": 0,  # Can be enhanced with actual CPU tracking
                "disk": 0,  # Can be enhanced with disk usage tracking
            }
        ]

    # Property overrides for SandboxBase

    @property
    def shell(self):
        return self._shell

    @property
    def file(self):
        return self._file

    @property
    def browser(self):
        return self._browser

    @property
    def detail(self) -> Optional[SandboxDetail]:
        """Get sandbox detail."""
        return self._sandbox_detail

    def __del__(self):
        """Cleanup on deletion."""
        # Note: async cleanup in __del__ is not recommended
        # Use explicit kill() or async context manager instead
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Async context manager exit."""
        await self.kill()


def get_local_sandbox_config_from_toml(toml_content: str) -> LocalSandboxConfig:
    """
    Parse local sandbox configuration from TOML content.

    Expected TOML format:
    ```toml
    [sandbox.local]
    work_dir = "/path/to/workspace"  # Default: DATA_DIR/workspace
    skill_dir = "/path/to/data/skill"  # Default: DATA_DIR/skill
    default_timeout = 300
    max_memory = 268435456  # 256MB
    max_cpus = 1
    use_sandbox_exec = true  # or auto-detect if not specified
    allow_network = true
    browser_type = "chromium"
    browser_headless = true
    max_sessions = 10
    session_idle_timeout = 3600

    [sandbox.local.browser_viewport]
    width = 1280
    height = 720
    ```
    """
    try:
        import tomli

        toml_dict = tomli.loads(toml_content)
    except ImportError:
        # Fallback to tomllib (Python 3.11+)
        import tomllib
        from io import StringIO

        toml_dict = tomllib.loads(toml_content)

    sandbox_config = toml_dict.get("sandbox", {}).get("local", {})
    return LocalSandboxConfig.from_dict(sandbox_config)


async def create_local_sandbox_from_toml(
    toml_content: str, user_id: str, agent: str, **kwargs
) -> ImprovedLocalSandbox:
    """
    Create a local sandbox from TOML configuration.

    Args:
        toml_content: TOML configuration content
        user_id: User ID
        agent: Agent identifier
        **kwargs: Additional arguments for sandbox creation

    Returns:
        Configured ImprovedLocalSandbox instance
    """
    config = get_local_sandbox_config_from_toml(toml_content)
    kwargs["local_sandbox_config"] = config.__dict__
    return await ImprovedLocalSandbox.create(user_id, agent, **kwargs)


# Predefined templates for common use cases


async def create_development_sandbox(
    user_id: str, agent: str, **kwargs
) -> ImprovedLocalSandbox:
    """Create a sandbox optimized for development (more permissive)."""
    kwargs.setdefault("local_sandbox_config", {})
    kwargs["local_sandbox_config"].update(
        {
            "allow_network": True,
            "max_memory": 512 * 1024 * 1024,  # 512MB
            "default_timeout": 600,  # 10 minutes
            "use_sandbox_exec": False,  # Disable for easier debugging
        }
    )
    return await ImprovedLocalSandbox.create(user_id, agent, **kwargs)


async def create_strict_sandbox(
    user_id: str, agent: str, **kwargs
) -> ImprovedLocalSandbox:
    """Create a sandbox with strict security settings."""
    kwargs.setdefault("local_sandbox_config", {})
    kwargs["local_sandbox_config"].update(
        {
            "allow_network": False,
            "max_memory": 128 * 1024 * 1024,  # 128MB
            "default_timeout": 60,  # 1 minute
            "use_sandbox_exec": True,
        }
    )
    return await ImprovedLocalSandbox.create(user_id, agent, **kwargs)


async def create_browser_sandbox(
    user_id: str, agent: str, **kwargs
) -> ImprovedLocalSandbox:
    """Create a sandbox optimized for browser automation."""
    kwargs.setdefault("local_sandbox_config", {})
    kwargs["local_sandbox_config"].update(
        {
            "allow_network": True,
            "max_memory": 512 * 1024 * 1024,  # 512MB
            "default_timeout": 300,  # 5 minutes
            "browser_type": "chromium",
            "browser_headless": True,
            "enable_browser": True,
        }
    )
    return await ImprovedLocalSandbox.create(user_id, agent, **kwargs)
