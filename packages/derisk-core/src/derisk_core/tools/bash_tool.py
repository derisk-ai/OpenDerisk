import asyncio
from typing import Dict, Any, Optional
from .base import ToolBase, ToolMetadata, ToolResult, ToolCategory, ToolRisk
from ..sandbox import DockerSandbox, LocalSandbox, SandboxFactory

class BashTool(ToolBase):
    """Bash命令执行工具 - 支持多环境"""
    
    def __init__(self, sandbox_mode: str = "auto"):
        super().__init__()
        self.sandbox_mode = sandbox_mode
        self._sandbox = None
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            description="执行Shell命令，支持本地和Docker沙箱环境",
            category=ToolCategory.SYSTEM,
            risk=ToolRisk.HIGH,
            requires_permission=True,
            examples=[
                "bash('ls -la')",
                "bash('pytest tests/', timeout=60)"
            ]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的Shell命令"
                },
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "超时时间(秒)"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录"
                },
                "sandbox": {
                    "type": "string",
                    "enum": ["auto", "local", "docker"],
                    "default": "auto",
                    "description": "执行环境"
                }
            },
            "required": ["command"]
        }
    
    async def _get_sandbox(self, sandbox_type: str):
        """获取沙箱实例"""
        if self._sandbox is None:
            if sandbox_type == "docker":
                self._sandbox = DockerSandbox()
            elif sandbox_type == "local":
                self._sandbox = LocalSandbox()
            else:
                self._sandbox = await SandboxFactory.create(prefer_docker=True)
        return self._sandbox
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 120)
        cwd = args.get("cwd")
        sandbox_type = args.get("sandbox", self.sandbox_mode)
        
        try:
            sandbox = await self._get_sandbox(sandbox_type)
            result = await sandbox.execute(command, cwd=cwd, timeout=timeout)
            
            return ToolResult(
                success=result.success,
                output=result.stdout,
                error=result.error or result.stderr,
                metadata={
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                    "sandbox_type": type(sandbox).__name__
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))