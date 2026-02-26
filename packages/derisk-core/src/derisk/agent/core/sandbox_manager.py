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

# Try to import SandboxConfigParameters, but provide fallback if not available
try:
    from derisk_app.config import SandboxConfigParameters
except ImportError:
    # Fallback when derisk_app is not available (e.g., during testing)
    from dataclasses import dataclass
    from typing import Any, Dict

    @dataclass
    class SandboxConfigParameters:
        """Fallback SandboxConfigParameters when derisk_app is not available."""

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

        def __post_init__(self):
            if self.work_dir is None:
                if self.type == "local":
                    self.work_dir = "/Users/tuyang.yhj/Code/python/derisk/pilot"
                else:
                    self.work_dir = "/home/ubuntu"

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> "SandboxConfigParameters":
            return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


logger = logging.getLogger(__name__)
CFG = Config()


class SandboxManager:
    def __init__(self, sandbox_client: Optional[SandboxBase] = None):
        self._initialized: bool = False
        ## 是否完成初始化，默认拉起实例和初始化沙箱环境使用异步的方式，正式使用前需要检查是否初始化完成，如果未完成需要等待或者报错
        self._sandbox_client: Optional[SandboxBase] = sandbox_client
        self._work_dir: Optional[str] = None
        self._skill_path: Optional[str] = None  # Will be set from sandbox client

        self._init_task = None

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
        if provider != "local":
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
        return await AutoSandbox.create(
            user_id=sandbox_config.user_id,
            agent=sandbox_config.agent_name,
            type=sandbox_config.type,
            template=sandbox_config.template_id,
            work_dir=sandbox_config.work_dir,
            skill_dir=sandbox_config.skill_dir,
            oss_ak=sandbox_config.oss_ak,
            oss_sk=sandbox_config.oss_sk,
            oss_endpoint=sandbox_config.oss_endpoint,
            oss_bucket_name=sandbox_config.oss_bucket_name,
        )

    async def acquire(self) -> SandboxBase:
        logger.info("sandbox acquire!")
        if not self._sandbox_client:
            self._sandbox_client = await self._create_client()
        return await self.initialize(self._sandbox_client, prepare_knowledge_repo=True)

    async def close(self) -> None:
        try:
            logger.info(
                "释放 sandbox 资源, sandbox_id=%s", self._sandbox_client.sandbox_id
            )
            client = self._sandbox_client
            kill_fn = getattr(client, "kill", None)
            if kill_fn:
                result = kill_fn(client.sandbox_id)
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:
            logger.warning("释放 sandbox 资源失败: %s", exc)
