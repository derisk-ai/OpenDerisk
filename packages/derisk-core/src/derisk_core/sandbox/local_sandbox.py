import asyncio
import time
from typing import Dict, Optional, Set
from pathlib import Path
from .base import SandboxBase, SandboxResult, SandboxConfig


class LocalSandbox(SandboxBase):
    """本地沙箱 - 受限执行环境"""
    
    FORBIDDEN_COMMANDS: Set[str] = {
        "rm -rf /", "mkfs", "dd if=/dev/zero",
        ":(){ :|:& };:",
    }
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        super().__init__(config)
        self._process: Optional[asyncio.subprocess.Process] = None
    
    async def start(self) -> bool:
        """本地沙箱无需启动"""
        return True
    
    async def stop(self) -> bool:
        """停止正在运行的进程"""
        if self._process and self._process.returncode is None:
            self._process.kill()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
        return True
    
    async def is_running(self) -> bool:
        """检查是否有进程在运行"""
        return self._process is not None and self._process.returncode is None
    
    async def execute(
        self, 
        command: str, 
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> SandboxResult:
        """在本地执行命令（受限环境）"""
        start_time = time.time()
        exec_timeout = timeout or self.config.timeout
        
        for forbidden in self.FORBIDDEN_COMMANDS:
            if forbidden in command:
                return SandboxResult(
                    success=False,
                    error=f"禁止执行的危险命令: {forbidden}",
                    exit_code=-1
                )
        
        exec_env = dict(env or {})
        exec_env.pop("API_KEY", None)
        exec_env.pop("SECRET", None)
        exec_env.pop("PASSWORD", None)
        
        workdir = Path(cwd) if cwd else Path.cwd()
        if not workdir.exists():
            return SandboxResult(
                success=False,
                error=f"工作目录不存在: {workdir}",
                exit_code=-1
            )
        
        try:
            self._process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=exec_env if exec_env else None
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    self._process.communicate(),
                    timeout=exec_timeout
                )
                
                duration_ms = (time.time() - start_time) * 1000
                
                return SandboxResult(
                    success=self._process.returncode == 0,
                    exit_code=self._process.returncode or 0,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_ms=duration_ms
                )
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
                return SandboxResult(
                    success=False,
                    error=f"命令执行超时({exec_timeout}秒)",
                    exit_code=-1
                )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1
            )