import asyncio
import inspect
import logging
import os
import shlex
import textwrap
from typing import Optional

from derisk._private.config import Config
from derisk.sandbox.base import SandboxBase, DEFAULT_SKILL_DIR
from derisk.sandbox.sandbox_client import AutoSandbox
from derisk.sandbox.sandbox_utils import collect_shell_output
from derisk.sandbox.watchdog_manager import (
    WatchdogManager,
    WatchdogClient,
    get_watchdog_manager,
    initialize_watchdog_manager,
    shutdown_watchdog_manager,
)

# Try to import SandboxConfigParameters, but provide fallback if not available
try:
    from derisk_app.config import SandboxConfigParameters
except ImportError:
    # Fallback when derisk_app is not available (e.g., during testing)
    from dataclasses import dataclass
    from typing import Any, Dict

    @dataclass
    class SandboxConfigParameters:
        """Fallback SandboxConfigParameters when derisk_app is not available.

        Note: Default values for work_dir and skill_dir should be defined by
        the sandbox implementation (e.g., LocalSandboxConfig), not here.
        """

        type: str = "local"
        user_id: str = "default"
        agent_name: str = "default"
        template_id: Optional[str] = None
        work_dir: Optional[str] = None
        skill_dir: Optional[str] = None
        oss_ak: Optional[str] = None
        oss_sk: Optional[str] = None
        oss_endpoint: Optional[str] = None
        oss_bucket_name: Optional[str] = None

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> "SandboxConfigParameters":
            return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


logger = logging.getLogger(__name__)
CFG = Config()


class SandboxManager:
    """
    沙箱管理器

    负责沙箱的生命周期管理，包括：
    - 沙箱创建和初始化
    - 看门狗（Watchdog）自动管理沙箱存活时间
    - 资源释放
    """

    # 看门狗配置
    WATCHDOG_CHECK_INTERVAL = 60  # 检查间隔（秒）
    WATCHDOG_EXTEND_THRESHOLD = 300  # 延长阈值（秒）
    WATCHDOG_EXTEND_MINUTES = 10  # 延长时间（分钟）

    def __init__(
        self,
        sandbox_client: Optional[SandboxBase] = None,
        enable_watchdog: bool = True,
        watchdog_base_url: Optional[str] = None,
    ):
        """
        初始化沙箱管理器

        Args:
            sandbox_client: 已存在的沙箱客户端（可选）
            enable_watchdog: 是否启用看门狗自动管理
            watchdog_base_url: 看门狗 API 基础 URL（可选，从配置读取）
        """
        self._initialized: bool = False
        ## 是否完成初始化，默认拉起实例和初始化沙箱环境使用异步的方式，正式使用前需要检查是否初始化完成，如果未完成需要等待或者报错
        self._sandbox_client: Optional[SandboxBase] = sandbox_client
        self._work_dir: Optional[str] = None
        self._skill_path: Optional[str] = None  # Will be set from sandbox client

        self._init_task = None

        # 看门狗管理
        self._enable_watchdog = enable_watchdog
        self._watchdog_base_url = watchdog_base_url
        self._watchdog_manager: Optional[WatchdogManager] = None

    @property
    def initialized(self):
        return self._initialized

    def set_init_task(self, task):
        self._init_task = task

    @property
    def init_task(self):
        return self._init_task

    @property
    def work_dir(self):
        return self._work_dir

    @property
    def skill_path(self):
        return self._skill_path

    @property
    def client(self):
        return self._sandbox_client

    async def _exec(
        self,
        command: str,
        *,
        work_dir: Optional[str],
        timeout: float,
    ):
        exec_dir = work_dir
        logger.info("sandbox exec: %s (cwd=%s)", command, exec_dir)
        result = await self.client.shell.exec_command(
            command=command, timeout=timeout, work_dir=exec_dir
        )
        if getattr(result, "status", None) != "completed":
            output = collect_shell_output(result)
            raise RuntimeError(
                f"命令执行失败: {command} -> {result.status}, 输出: {output}"
            )
        return result

    async def _ensure_directory(self, path: str) -> None:
        command = f"mkdir -p {shlex.quote(path)}"
        await self._exec(command, work_dir=None, timeout=60.0)

    async def _ensure_sudo_nopasswd(self) -> None:
        """在沙箱中以最快方式配置 sudo 免密，避免后续命令阻塞。"""
        username = os.getenv("SANDBOX_SUDO_USER", "ubuntu")
        password = os.getenv("SANDBOX_SUDO_PASSWORD", "ubuntu")
        root_script = textwrap.dedent(
            f"""
                #!/usr/bin/env bash
                set -euo pipefail
                HOST_NAME="$(hostname)"
                if ! grep -q "$HOST_NAME" /etc/hosts; then
                    echo "127.0.1.1 $HOST_NAME" >> /etc/hosts
                fi
                cat <<'EOF' > /etc/sudoers.d/{username}-nopasswd
    {username} ALL=(ALL) NOPASSWD:ALL
    EOF
                chmod 0440 /etc/sudoers.d/{username}-nopasswd
                """
        ).strip()
        safe_password = password.replace("'", "'\"'\"'")
        bootstrap_script = textwrap.dedent(
            f"""
                set -euo pipefail
                ROOT_SCRIPT=/tmp/auto_sudo_fix.sh
                cat <<'PYROOT' > "$ROOT_SCRIPT"
    {root_script}
    PYROOT
                chmod +x "$ROOT_SCRIPT"
                if sudo -n true 2>/dev/null; then
                    rm -f "$ROOT_SCRIPT"
                    exit 0
                fi
                printf '%s\n' '{safe_password}' | sudo -S "$ROOT_SCRIPT"
                sudo -k
                rm -f "$ROOT_SCRIPT"
                sudo -n true
                """
        ).strip()
        command = f"bash -lc {shlex.quote(bootstrap_script)}"
        await self._exec(command, work_dir=self.work_dir, timeout=10.0)

    async def _update_repo(self, repo_path: str) -> None:
        """更新已有的 git 仓库"""
        pull_cmd = "git fetch --depth=1 --no-tags --prune --quiet origin master && git reset --hard origin/master --quiet"
        logger.info("更新知识库仓库: %s", repo_path)
        result = await self._exec(pull_cmd, work_dir=repo_path, timeout=60.0)
        output = collect_shell_output(result)
        logger.info("git pull 完成: %s", output)

    async def initialize(
        self,
        sandbox: SandboxBase,
        prepare_knowledge_repo: bool = True,
    ):
        """
        从已存在的 sandbox 实例初始化环境（创建或恢复）
        统一执行：工作目录设置、目录创建、知识库更新

        Args:
            sandbox: 已创建或恢复的 sandbox 实例
            prepare_knowledge_repo: 是否准备知识库，默认 True

        Returns:
            SandboxRuntimeState: 包含初始化完成的状态
        """
        # 1. 从 sandbox 获取工作目录
        self._work_dir = sandbox.work_dir

        # 2. 确保工作目录存在 (local sandbox 不需要，runtime 会自动处理)
        provider = getattr(sandbox, "provider", lambda: None)()
        if provider != "local" and self.work_dir:
            await self._ensure_directory(self.work_dir)
        logger.info(
            "工作目录已准备: sandbox_id=%s, work_dir=%s",
            sandbox.sandbox_id,
            self.work_dir,
        )

        # 3. 确保 sudo 免密配置，避免后续命令阻塞在密码提示
        try:
            await self._ensure_sudo_nopasswd()
            logger.info("sudo 免密配置成功: sandbox_id=%s", sandbox.sandbox_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sudo 免密配置失败: %s", exc, exc_info=True)

        # 4. 准备知识库（如果需要）
        if prepare_knowledge_repo:
            # Use skill_dir from sandbox client instead of hardcoded path
            repo_path = sandbox.skill_dir or DEFAULT_SKILL_DIR
            if not repo_path:
                logger.warning(
                    "skill_dir not configured, skipping knowledge repo preparation"
                )
            else:
                self._skill_path = repo_path
                logger.info(
                    "知识库更新开始准备: sandbox_id=%s, repo_path=%s",
                    sandbox.sandbox_id,
                    repo_path,
                )
                try:
                    await self._ensure_directory(repo_path)
                    await self._update_repo(repo_path)
                    logger.info(
                        "知识库已准备: sandbox_id=%s, repo_path=%s",
                        sandbox.sandbox_id,
                        repo_path,
                    )
                except Exception as exc:
                    logger.warning(
                        "知识库准备失败: sandbox_id=%s, repo_path=%s, error=%s",
                        sandbox.sandbox_id,
                        repo_path,
                        exc,
                        exc_info=True,
                    )
        logger.info(f"Sandbox id={sandbox.sandbox_id} Initialized Success!")
        self._initialized = True

    async def _create_client(self) -> SandboxBase:
        app_config = CFG.SYSTEM_APP.config.configs.get("app_config")
        sandbox_config: SandboxConfigParameters = app_config.sandbox
        if not sandbox_config:
            logger.error("未配置sandbox，无法进行sandbox启动")
            raise ValueError("未配置sandbox，无法进行sandbox启动!")
        logger.info(
            f"创建 sandbox client,type={sandbox_config.type} user_id={sandbox_config.user_id}, template_id={sandbox_config.template_id}"
        )

        file_storage_client = self._get_file_storage_client()

        return await AutoSandbox.create(
            user_id=sandbox_config.user_id,
            agent=sandbox_config.agent_name,
            type=sandbox_config.type,
            template=sandbox_config.template_id,
            work_dir=sandbox_config.work_dir,
            skill_dir=sandbox_config.skill_dir,
            file_storage_client=file_storage_client,
            oss_ak=sandbox_config.oss_ak,
            oss_sk=sandbox_config.oss_sk,
            oss_endpoint=sandbox_config.oss_endpoint,
            oss_bucket_name=sandbox_config.oss_bucket_name,
        )

    def _get_file_storage_client(self):
        """从系统应用获取文件存储客户端"""
        try:
            from derisk.core.interface.file import FileStorageClient

            system_app = CFG.SYSTEM_APP
            if not system_app:
                logger.warning(
                    "[SandboxManager] CFG.SYSTEM_APP is None, cannot get FileStorageClient"
                )
                return None

            file_storage_client = FileStorageClient.get_instance(system_app)

            if file_storage_client:
                logger.info(
                    f"[SandboxManager] FileStorageClient retrieved successfully. "
                    f"client_name={file_storage_client.name}, "
                    f"default_storage_type={file_storage_client.default_storage_type}, "
                    f"storage_backends={list(file_storage_client.storage_system.storage_backends.keys())}"
                )
            else:
                logger.warning(
                    "[SandboxManager] FileStorageClient.get_instance() returned None"
                )

            return file_storage_client

        except ValueError as e:
            logger.warning(
                f"[SandboxManager] FileStorageClient not found in system_app. "
                f"Error: {e}. Available components: {list(CFG.SYSTEM_APP.components.keys()) if CFG.SYSTEM_APP else 'N/A'}"
            )
            return None
        except Exception as e:
            logger.warning(
                f"[SandboxManager] Failed to get FileStorageClient: {e}. "
                f"Error type: {type(e).__name__}",
                exc_info=True,
            )
            return None

    async def acquire(self) -> SandboxBase:
        logger.info("sandbox acquire!")
        if not self._sandbox_client:
            self._sandbox_client = await self._create_client()

        # 初始化看门狗管理（如果启用）
        if self._enable_watchdog and self._sandbox_client:
            await self._init_watchdog()

        return await self.initialize(self._sandbox_client, prepare_knowledge_repo=True)

    async def _init_watchdog(self) -> None:
        """
        初始化看门狗管理器

        如果全局看门狗管理器不存在，则创建一个
        然后将当前沙箱实例注册到看门狗管理器
        """
        if not self._sandbox_client:
            return

        try:
            # 尝试获取全局看门狗管理器
            watchdog_mgr = get_watchdog_manager()

            if not watchdog_mgr:
                # 获取 API 基础 URL
                base_url = self._watchdog_base_url
                if not base_url:
                    # 尝试从沙箱客户端获取
                    if (
                        hasattr(self._sandbox_client, "connection_config")
                        and self._sandbox_client.connection_config
                    ):
                        base_url = self._sandbox_client.connection_config.domain

                if not base_url:
                    # 尝试从配置获取
                    try:
                        app_config = CFG.SYSTEM_APP.config.configs.get("app_config")
                        if app_config and hasattr(app_config, "sandbox"):
                            base_url = getattr(
                                app_config.sandbox, "watchdog_base_url", None
                            )
                    except Exception:
                        pass

                if not base_url:
                    logger.warning(
                        "[SandboxManager] Watchdog base URL not configured, "
                        "watchdog management disabled"
                    )
                    self._enable_watchdog = False
                    return

                # 初始化看门狗管理器
                watchdog_mgr = await initialize_watchdog_manager(
                    base_url=base_url,
                    check_interval=self.WATCHDOG_CHECK_INTERVAL,
                    extend_threshold=self.WATCHDOG_EXTEND_THRESHOLD,
                    extend_minutes=self.WATCHDOG_EXTEND_MINUTES,
                    auto_start=True,
                )

            self._watchdog_manager = watchdog_mgr

            # 注册当前沙箱实例
            instance_id = self._sandbox_client.sandbox_id
            watchdog_mgr.register(instance_id)

            logger.info(
                f"[SandboxManager] Watchdog management enabled for instance: {instance_id}"
            )

        except Exception as e:
            logger.warning(f"[SandboxManager] Failed to initialize watchdog: {e}")
            self._enable_watchdog = False

    async def feed_watchdog(self, instance_timeout: Optional[int] = None) -> bool:
        """
        手动延长沙箱存活时间

        Args:
            instance_timeout: 延长时间（分钟），不传则使用默认值

        Returns:
            bool: 是否成功延长
        """
        if not self._sandbox_client or not self._watchdog_manager:
            logger.warning("[SandboxManager] Watchdog not initialized")
            return False

        try:
            instance_id = self._sandbox_client.sandbox_id
            await self._watchdog_manager.client.feed_watchdog(
                instance_id=instance_id,
                instance_timeout=instance_timeout or self.WATCHDOG_EXTEND_MINUTES,
            )
            logger.info(f"[SandboxManager] Manual watchdog feed: {instance_id}")
            return True
        except Exception as e:
            logger.error(f"[SandboxManager] Failed to feed watchdog: {e}")
            return False

    async def get_remaining_time(self) -> Optional[float]:
        """
        获取沙箱剩余存活时间

        Returns:
            Optional[float]: 剩余时间（秒），获取失败返回 None
        """
        if not self._sandbox_client or not self._watchdog_manager:
            return None

        try:
            instance_id = self._sandbox_client.sandbox_id
            status = await self._watchdog_manager.client.get_remaining_time(instance_id)
            return status.remaining_time_seconds
        except Exception as e:
            logger.error(f"[SandboxManager] Failed to get remaining time: {e}")
            return None

    async def close(self) -> None:
        """
        释放沙箱资源

        包括：
        1. 取消看门狗监控
        2. 终止沙箱实例
        """
        # 取消看门狗注册
        if self._watchdog_manager and self._sandbox_client:
            try:
                instance_id = self._sandbox_client.sandbox_id
                self._watchdog_manager.unregister(instance_id)
                logger.info(
                    f"[SandboxManager] Unregistered from watchdog: {instance_id}"
                )
            except Exception as e:
                logger.warning(f"[SandboxManager] Failed to unregister watchdog: {e}")

        # 终止沙箱
        try:
            logger.info(
                "释放 sandbox 资源, sandbox_id=%s",
                self._sandbox_client.sandbox_id if self._sandbox_client else "None",
            )
            client = self._sandbox_client
            if client:
                kill_fn = getattr(client, "kill", None)
                if kill_fn:
                    result = kill_fn(client.sandbox_id)
                    if inspect.isawaitable(result):
                        await result
        except Exception as exc:
            logger.warning("释放 sandbox 资源失败: %s", exc)
