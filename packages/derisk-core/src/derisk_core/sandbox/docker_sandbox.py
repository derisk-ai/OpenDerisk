import asyncio
import time
from typing import Dict, Optional
from pathlib import Path
from .base import SandboxBase, SandboxResult, SandboxConfig


class DockerSandbox(SandboxBase):
    """Docker沙箱 - 参考OpenClaw设计"""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        super().__init__(config)
        self._container_id: Optional[str] = None
        self._docker_available: Optional[bool] = None
    
    async def _check_docker(self) -> bool:
        """检查Docker是否可用"""
        if self._docker_available is not None:
            return self._docker_available
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
            self._docker_available = proc.returncode == 0
        except Exception:
            self._docker_available = False
        
        return self._docker_available
    
    async def start(self) -> bool:
        """启动沙箱容器"""
        if not await self._check_docker():
            raise RuntimeError("Docker不可用，请确保Docker已安装并运行")
        
        if self._container_id:
            return True
        
        cmd = [
            "docker", "run", "-d",
            "--memory", self.config.memory_limit,
            "--cpus", str(self.config.cpu_limit),
            "--workdir", self.config.workdir,
        ]
        
        if not self.config.network_enabled:
            cmd.append("--network=none")
        
        for host_path, container_path in self.config.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
        
        for key, value in self.config.env.items():
            cmd.extend(["-e", f"{key}={value}"])
        
        cmd.append(self.config.image)
        cmd.extend(["tail", "-f", "/dev/null"])
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                self._container_id = stdout.decode().strip()
                return True
        except Exception as e:
            raise RuntimeError(f"启动容器失败: {e}")
        
        return False
    
    async def stop(self) -> bool:
        """停止并清理容器"""
        if not self._container_id:
            return True
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self._container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            self._container_id = None
            return True
        except Exception:
            return False
    
    async def is_running(self) -> bool:
        """检查容器是否运行"""
        if not self._container_id:
            return False
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "ps", "-q", "-f", f"id={self._container_id}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return bool(stdout.decode().strip())
        except Exception:
            return False
    
    async def execute(
        self, 
        command: str, 
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> SandboxResult:
        """在Docker容器中执行命令"""
        start_time = time.time()
        exec_timeout = timeout or self.config.timeout
        
        if not self._container_id:
            return await self._execute_oneoff(command, cwd, env, exec_timeout)
        
        try:
            cmd = ["docker", "exec"]
            
            if cwd:
                cmd.extend(["-w", cwd])
            
            if env:
                for k, v in env.items():
                    cmd.extend(["-e", f"{k}={v}"])
            
            cmd.extend([self._container_id, "sh", "-c", command])
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=exec_timeout
                )
                
                duration_ms = (time.time() - start_time) * 1000
                
                return SandboxResult(
                    success=proc.returncode == 0,
                    exit_code=proc.returncode or 0,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_ms=duration_ms
                )
            except asyncio.TimeoutError:
                proc.kill()
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
    
    async def _execute_oneoff(
        self,
        command: str,
        cwd: Optional[str],
        env: Optional[Dict[str, str]],
        timeout: int
    ) -> SandboxResult:
        """一次性执行（不保持容器）"""
        start_time = time.time()
        
        if not await self._check_docker():
            return SandboxResult(
                success=False,
                error="Docker不可用",
                exit_code=-1
            )
        
        cmd = ["docker", "run", "--rm"]
        
        cmd.extend(["--memory", self.config.memory_limit])
        cmd.extend(["--cpus", str(self.config.cpu_limit)])
        
        if not self.config.network_enabled:
            cmd.append("--network=none")
        
        workdir = cwd or self.config.workdir
        cmd.extend(["-w", workdir])
        
        if cwd:
            abs_cwd = str(Path(cwd).resolve())
            cmd.extend(["-v", f"{abs_cwd}:{workdir}"])
        
        for host_path, container_path in self.config.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
        
        merged_env = {**self.config.env, **(env or {})}
        for k, v in merged_env.items():
            cmd.extend(["-e", f"{k}={v}"])
        
        cmd.append(self.config.image)
        cmd.extend(["sh", "-c", command])
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
                
                duration_ms = (time.time() - start_time) * 1000
                
                return SandboxResult(
                    success=proc.returncode == 0,
                    exit_code=proc.returncode or 0,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_ms=duration_ms
                )
            except asyncio.TimeoutError:
                proc.kill()
                return SandboxResult(
                    success=False,
                    error=f"命令执行超时({timeout}秒)",
                    exit_code=-1
                )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1
            )