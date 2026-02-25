"""
Local Shell Client Implementation
"""

from typing import Optional, Dict, cast, Any
import os
import logging
import asyncio
import shlex
import subprocess
import time
from derisk.sandbox.client.shell.client import ShellClient
from derisk.sandbox.client.shell.type.shell_command_result import ShellCommandResult

logger = logging.getLogger(__name__)

OMIT = cast(Any, ...)


class LocalShellClient(ShellClient):
    """本地 Shell 客户端实现"""

    def __init__(
        self, sandbox_id: str, work_dir: str, runtime, skill_dir: str = None, **kwargs
    ):
        super().__init__(sandbox_id, work_dir, connection_config=None, **kwargs)
        self._runtime = runtime
        self._skill_dir = skill_dir
        self._whitelist_paths = {"/mnt"}
        if skill_dir:
            self._whitelist_paths.add(skill_dir)

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
        """执行 Shell 命令"""

        # 确定工作目录
        # 这里需要将逻辑工作目录转换为物理工作目录，类似于 LocalFileClient
        # 假设 runtime.base_dir + sandbox_id 是根

        # 简单处理：如果 cwd 是绝对路径且存在，则直接使用
        # 如果 cwd 是相对路径，则拼接到 sandbox 根

        sandbox_root = os.path.join(self._runtime.base_dir, self._sandbox_id)

        target_cwd = self._work_dir
        if work_dir is not OMIT and work_dir is not None:
            target_cwd = work_dir

        # Resolve path
        if not target_cwd:
            cwd = sandbox_root
        elif os.path.isabs(target_cwd):
            # Check if path is in whitelist (should be accessed directly on host)
            is_whitelisted = False
            for allowed in self._whitelist_paths:
                if target_cwd == allowed or target_cwd.startswith(f"{allowed}/"):
                    is_whitelisted = True
                    break

            if is_whitelisted:
                # Path is in whitelist, use it directly
                cwd = target_cwd
            else:
                # 如果是绝对路径，我们假设它是相对于沙箱内部的路径，需要映射到物理路径
                rel = target_cwd.lstrip("/")
                cwd = os.path.abspath(os.path.join(sandbox_root, rel))
        else:
            cwd = os.path.abspath(os.path.join(sandbox_root, target_cwd))

        # Ensure dir exists, otherwise subprocess fails
        if not os.path.exists(cwd):
            # 尝试创建或回退
            try:
                os.makedirs(cwd, exist_ok=True)
            except:
                cwd = sandbox_root

        timeout_val = 60.0
        if timeout is not OMIT and timeout is not None:
            timeout_val = timeout

        logger.info(f"LocalShellClient exec: {command} in {cwd}")

        try:
            # 使用 runtime 的会话来执行，或者直接使用 subprocess
            # 为了复用 runtime 的隔离（虽然现在 runtime 也是 subprocess）
            # 我们这里直接用 subprocess，因为 LocalShellClient 主要是作为 helper

            # 安全性提示：这里直接执行命令，需要确保 LocalSandboxRuntime 已经做好 chroot 或其他隔离
            # 当前简单实现仅做路径切换

            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_val
                )
                exit_code = process.returncode
                output = stdout.decode() if stdout else ""
                error = stderr.decode() if stderr else ""

                # 构造符合 ShellCommandResult 预期的结果
                status_val = (
                    "completed" if exit_code == 0 else "failed"
                )  # 注意 BashCommandStatus 类型

                return ShellCommandResult(
                    session_id=self._sandbox_id,
                    status=status_val,
                    command=command,
                    output=output + error,
                    exit_code=exit_code,
                    console=[],  # console record mock
                )

            except asyncio.TimeoutError:
                process.kill()
                raise TimeoutError(f"Command timed out: {command}")

        except Exception as e:
            logger.error(f"Local exec failed: {e}")
            raise
