"""
BashTool - 统一Shell命令执行工具

支持两种执行环境：
- 有沙箱：通过 sandbox client 在沙箱中执行命令（带命令验证和输出截断）
- 无沙箱：通过本地 subprocess 执行
"""

from typing import Dict, Any, Optional
import asyncio
import os
import logging

from ..sandbox.base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel, ToolEnvironment
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


BLOCKED_COMMANDS = [
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    "> /dev/sda",
    ":(){ :|:& };:",
]


class BashTool(SandboxToolBase):
    """统一Shell命令执行工具 - 自动检测执行环境"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            display_name="Execute Bash",
            description=(
                "Execute a shell command and return the output.\n\n"
                "When running in a sandbox environment:\n"
                "- Commands execute in the sandbox workspace\n"
                "- Output is limited to 16KB / 500 lines\n"
                "- Working directory is the sandbox workspace root\n\n"
                "When running locally:\n"
                "- Commands execute on the local system\n"
                "- Supports custom working directory and environment variables"
            ),
            category=ToolCategory.SHELL,
            risk_level=ToolRiskLevel.HIGH,
            requires_permission=True,
            timeout=120,
            tags=["shell", "command", "execute"],
            approval_message="This command will be executed. Do you want to proceed?",
            # 授权配置：可以禁用 cwd 检查
            # authorization_config={"disable_cwd_check": True},
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "Timeout in seconds",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (local mode only)",
                },
                "env": {
                    "type": "object",
                    "description": "Environment variables (local mode only)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        client = self._get_sandbox_client(context)
        if client is not None:
            return await self._execute_sandbox(args, context, client)
        else:
            return await self._execute_local(args, context)

    async def _execute_sandbox(
        self, args: Dict[str, Any], context: Optional[ToolContext], client: Any
    ) -> ToolResult:
        """Delegate to sandbox ShellExecTool logic"""
        from ..sandbox.shell_exec import ShellExecTool

        shell_tool = ShellExecTool()
        sandbox_args = {
            "command": args["command"],
            "timeout": args.get("timeout", 60),
        }

        return await shell_tool.execute(sandbox_args, context)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Execute locally using subprocess"""
        command = args["command"]
        timeout = args.get("timeout", 120)
        cwd = args.get("cwd")
        env = args.get("env", {})

        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult.fail(
                    error=f"Blocked dangerous command: {blocked}",
                    tool_name=self.name,
                    error_code="BLOCKED_COMMAND",
                )

        if context:
            if not cwd and context.working_directory:
                cwd = context.working_directory

        try:
            merged_env = os.environ.copy()
            merged_env.update(env)

            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult.timeout(self.name, timeout)

            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")

            success = process.returncode == 0

            result_output = output
            if error and not success:
                result_output = f"{output}\nStderr:\n{error}" if output else error

            return ToolResult(
                success=success,
                output=result_output,
                error=error if error and not success else None,
                tool_name=self.name,
                metadata={
                    "return_code": process.returncode,
                    "command": command,
                    "timeout": timeout,
                    "cwd": cwd,
                },
            )

        except Exception as e:
            logger.error(f"[BashTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
