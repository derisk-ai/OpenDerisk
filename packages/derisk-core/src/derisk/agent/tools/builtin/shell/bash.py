"""
BashTool - Shell命令执行工具
参考 OpenCode 和 OpenClaw 的 bash 工具
"""

from typing import Dict, Any, Optional
import asyncio
import os
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolEnvironment
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


class BashTool(ToolBase):
    """Bash命令执行工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            display_name="Execute Bash",
            description="Execute a shell command and return the output",
            category=ToolCategory.SHELL,
            risk_level=ToolRiskLevel.HIGH,
            requires_permission=True,
            timeout=120,
            environment=ToolEnvironment.LOCAL,
            tags=["shell", "command", "execute"],
            approval_message="This command will be executed on your system. Do you want to proceed?",
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "Timeout in seconds"
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory"
                },
                "env": {
                    "type": "object",
                    "description": "Environment variables"
                }
            },
            "required": ["command"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 120)
        cwd = args.get("cwd")
        env = args.get("env", {})
        
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult.fail(
                    error=f"Blocked dangerous command: {blocked}",
                    tool_name=self.name,
                    error_code="BLOCKED_COMMAND"
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
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
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
                    "cwd": cwd
                }
            )
            
        except Exception as e:
            logger.error(f"[BashTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)