"""
SandboxDocker - Docker沙箱执行系统

实现安全的工具执行环境
支持资源限制、网络隔离、文件系统隔离
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
import asyncio
import logging
import os
import tempfile
import json

logger = logging.getLogger(__name__)


class SandboxType(str, Enum):
    """沙箱类型"""
    LOCAL = "local"
    DOCKER = "docker"
    REMOTE = "remote"


class SandboxStatus(str, Enum):
    """沙箱状态"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class ExecutionResult(BaseModel):
    """执行结果"""
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    
    execution_time: float = 0.0
    memory_used: Optional[int] = None
    cpu_used: Optional[float] = None
    
    error: Optional[str] = None
    error_type: Optional[str] = None
    
    files_created: List[str] = Field(default_factory=list)
    files_modified: List[str] = Field(default_factory=list)
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SandboxConfig(BaseModel):
    """沙箱配置"""
    sandbox_type: SandboxType = SandboxType.DOCKER
    image: str = "python:3.11-slim"
    
    memory_limit: str = "512m"
    cpu_quota: int = 50000
    timeout: int = 60
    
    network_enabled: bool = False
    network_mode: str = "none"
    
    workdir: str = "/workspace"
    
    volumes: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    environment: Dict[str, str] = Field(default_factory=dict)
    
    security_opts: List[str] = Field(default_factory=lambda: ["no-new-privileges"])
    cap_drop: List[str] = Field(default_factory=lambda: ["ALL"])
    read_only_root: bool = False
    
    auto_remove: bool = True
    keep_temp_files: bool = False
    
    allowed_commands: List[str] = Field(default_factory=list)
    blocked_commands: List[str] = Field(default_factory=lambda: ["rm -rf /", "mkfs", "dd"])

    class Config:
        use_enum_values = True


class SandboxBase(ABC):
    """沙箱基类"""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._status = SandboxStatus.CREATED
        self._created_at = datetime.now()
        self._execution_count = 0
    
    @abstractmethod
    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """执行命令"""
        pass
    
    @abstractmethod
    async def start(self):
        """启动沙箱"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止沙箱"""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """清理沙箱"""
        pass
    
    def get_status(self) -> SandboxStatus:
        """获取状态"""
        return self._status
    
    def validate_command(self, command: str) -> bool:
        """验证命令"""
        for blocked in self.config.blocked_commands:
            if blocked in command:
                return False
        
        if self.config.allowed_commands:
            first_word = command.strip().split()[0] if command.strip() else ""
            if first_word not in self.config.allowed_commands:
                return False
        
        return True


class LocalSandbox(SandboxBase):
    """本地沙箱（受限执行）"""
    
    def __init__(self, config: SandboxConfig):
        super().__init__(config)
        self._temp_dir: Optional[str] = None
    
    async def start(self):
        self._temp_dir = tempfile.mkdtemp(prefix="sandbox_")
        self._status = SandboxStatus.RUNNING
        logger.info(f"[LocalSandbox] 启动沙箱: {self._temp_dir}")
    
    async def stop(self):
        self._status = SandboxStatus.STOPPED
        logger.info(f"[LocalSandbox] 停止沙箱")
    
    async def cleanup(self):
        if self._temp_dir and os.path.exists(self._temp_dir):
            if not self.config.keep_temp_files:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
        logger.info(f"[LocalSandbox] 清理沙箱")
    
    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        start_time = datetime.now()
        self._execution_count += 1
        
        if not self.validate_command(command):
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error="Command not allowed",
                error_type="SecurityError"
            )
        
        try:
            merged_env = os.environ.copy()
            merged_env.update(self.config.environment)
            if env:
                merged_env.update(env)
            
            work_dir = cwd or self._temp_dir
            
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                env=merged_env,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                actual_timeout = timeout or self.config.timeout
                
                if input_data:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(input_data.encode()),
                        timeout=actual_timeout
                    )
                else:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=actual_timeout
                    )
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return ExecutionResult(
                    success=proc.returncode == 0,
                    exit_code=proc.returncode,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    output=stdout.decode("utf-8", errors="replace"),
                    execution_time=execution_time,
                )
                
            except asyncio.TimeoutError:
                proc.kill()
                return ExecutionResult(
                    success=False,
                    exit_code=-1,
                    error=f"Execution timeout after {actual_timeout}s",
                    error_type="TimeoutError"
                )
                
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error=str(e),
                error_type=type(e).__name__
            )


class DockerSandbox(SandboxBase):
    """Docker沙箱"""
    
    def __init__(self, config: SandboxConfig):
        super().__init__(config)
        self._client = None
        self._container = None
        self._container_id: Optional[str] = None
    
    async def _ensure_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
                self._client.ping()
            except ImportError:
                raise ImportError("Please install docker: pip install docker")
            except Exception as e:
                raise RuntimeError(f"Docker not available: {e}")
    
    async def start(self):
        await self._ensure_client()
        
        try:
            volumes = {}
            for host_path, config in self.config.volumes.items():
                volumes[host_path] = {
                    "bind": config.get("bind", host_path),
                    "mode": config.get("mode", "rw")
                }
            
            self._container = self._client.containers.create(
                image=self.config.image,
                command="tail -f /dev/null",
                volumes=volumes,
                environment=self.config.environment,
                working_dir=self.config.workdir,
                mem_limit=self.config.memory_limit,
                cpu_quota=self.config.cpu_quota,
                network_mode=self.config.network_mode if not self.config.network_enabled else "bridge",
                security_opt=self.config.security_opts,
                cap_drop=self.config.cap_drop,
                read_only=self.config.read_only_root,
                auto_remove=False,
                detach=True,
            )
            
            self._container.start()
            self._container_id = self._container.id[:12]
            self._status = SandboxStatus.RUNNING
            
            logger.info(f"[DockerSandbox] 启动容器: {self._container_id}")
            
        except Exception as e:
            self._status = SandboxStatus.ERROR
            logger.error(f"[DockerSandbox] 启动失败: {e}")
            raise
    
    async def stop(self):
        if self._container:
            try:
                self._container.stop()
                self._status = SandboxStatus.STOPPED
                logger.info(f"[DockerSandbox] 停止容器: {self._container_id}")
            except Exception as e:
                logger.error(f"[DockerSandbox] 停止失败: {e}")
    
    async def cleanup(self):
        if self._container:
            try:
                if self.config.auto_remove:
                    self._container.remove(force=True)
                logger.info(f"[DockerSandbox] 清理容器: {self._container_id}")
            except Exception as e:
                logger.error(f"[DockerSandbox] 清理失败: {e}")
            finally:
                self._container = None
                self._container_id = None
    
    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        if not self._container or self._status != SandboxStatus.RUNNING:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error="Sandbox not running",
                error_type="StateError"
            )
        
        if not self.validate_command(command):
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error="Command not allowed",
                error_type="SecurityError"
            )
        
        start_time = datetime.now()
        self._execution_count += 1
        
        try:
            exec_config = {
                "cmd": ["/bin/sh", "-c", command],
                "workdir": cwd or self.config.workdir,
                "environment": {**self.config.environment, **(env or {})},
                "stdout": True,
                "stderr": True,
                "stdin": input_data is not None,
            }
            
            exec_id = self._client.api.exec_create(self._container.id, **exec_config)
            
            actual_timeout = timeout or self.config.timeout
            
            output = self._client.api.exec_start(
                exec_id["Id"],
                stream=False,
                detach=False,
            )
            
            exec_info = self._client.api.exec_inspect(exec_id["Id"])
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            output_str = output.decode("utf-8", errors="replace") if output else ""
            
            return ExecutionResult(
                success=exec_info["ExitCode"] == 0,
                exit_code=exec_info["ExitCode"],
                output=output_str,
                stdout=output_str,
                stderr="",
                execution_time=execution_time,
            )
            
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error=str(e),
                error_type=type(e).__name__
            )
    
    async def put_file(
        self,
        container_path: str,
        content: str
    ) -> bool:
        """写入文件到容器"""
        if not self._container:
            return False
        
        try:
            import io
            tar_stream = io.BytesIO()
            import tarfile
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                data = content.encode('utf-8')
                tarinfo = tarfile.TarInfo(name=os.path.basename(container_path))
                tarinfo.size = len(data)
                tar.addfile(tarinfo, io.BytesIO(data))
            
            tar_stream.seek(0)
            self._container.put_archive(os.path.dirname(container_path), tar_stream)
            return True
        except Exception as e:
            logger.error(f"[DockerSandbox] 写入文件失败: {e}")
            return False
    
    async def get_file(self, container_path: str) -> Optional[str]:
        """从容器读取文件"""
        if not self._container:
            return None
        
        try:
            bits, stat = self._container.get_archive(container_path)
            import io
            import tarfile
            
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                member = tar.getmembers()[0]
                f = tar.extractfile(member)
                if f:
                    return f.read().decode('utf-8')
            
        except Exception as e:
            logger.error(f"[DockerSandbox] 读取文件失败: {e}")
        
        return None
    
    async def health_check(self) -> bool:
        """健康检查"""
        if not self._container:
            return False
        
        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False


class SandboxManager:
    """
    沙箱管理器
    
    职责:
    1. 沙箱生命周期管理
    2. 多沙箱并行执行
    3. 资源统计
    4. 安全审计
    
    示例:
        manager = SandboxManager()
        
        sandbox = await manager.create_sandbox(config)
        
        result = await sandbox.execute("python script.py")
        print(result.output)
        
        await manager.cleanup_sandbox(sandbox)
    """
    
    def __init__(self):
        self._sandboxes: Dict[str, SandboxBase] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._total_executions = 0
        self._total_errors = 0
    
    async def create_sandbox(
        self,
        config: SandboxConfig,
        sandbox_id: Optional[str] = None
    ) -> SandboxBase:
        """创建沙箱"""
        if config.sandbox_type == SandboxType.DOCKER:
            sandbox = DockerSandbox(config)
        else:
            sandbox = LocalSandbox(config)
        
        await sandbox.start()
        
        sid = sandbox_id or sandbox._container_id or f"local-{id(sandbox)}"
        self._sandboxes[sid] = sandbox
        
        logger.info(f"[SandboxManager] 创建沙箱: {sid}")
        return sandbox
    
    async def execute_in_sandbox(
        self,
        sandbox_id: str,
        command: str,
        **kwargs
    ) -> ExecutionResult:
        """在指定沙箱中执行"""
        sandbox = self._sandboxes.get(sandbox_id)
        
        if not sandbox:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error=f"Sandbox {sandbox_id} not found",
                error_type="NotFoundError"
            )
        
        self._total_executions += 1
        
        result = await sandbox.execute(command, **kwargs)
        
        if not result.success:
            self._total_errors += 1
        
        self._execution_history.append({
            "sandbox_id": sandbox_id,
            "command": command[:100],
            "success": result.success,
            "exit_code": result.exit_code,
            "execution_time": result.execution_time,
            "timestamp": datetime.now().isoformat(),
        })
        
        return result
    
    async def cleanup_sandbox(self, sandbox_id: str):
        """清理沙箱"""
        sandbox = self._sandboxes.get(sandbox_id)
        
        if sandbox:
            await sandbox.stop()
            await sandbox.cleanup()
            del self._sandboxes[sandbox_id]
            logger.info(f"[SandboxManager] 清理沙箱: {sandbox_id}")
    
    async def cleanup_all(self):
        """清理所有沙箱"""
        for sandbox_id in list(self._sandboxes.keys()):
            await self.cleanup_sandbox(sandbox_id)
    
    def get_sandbox(self, sandbox_id: str) -> Optional[SandboxBase]:
        """获取沙箱"""
        return self._sandboxes.get(sandbox_id)
    
    def list_sandboxes(self) -> List[str]:
        """列出所有沙箱"""
        return list(self._sandboxes.keys())
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_sandboxes": len(self._sandboxes),
            "total_executions": self._total_executions,
            "total_errors": self._total_errors,
            "error_rate": self._total_errors / max(1, self._total_executions),
            "execution_history_count": len(self._execution_history),
        }


sandbox_manager = SandboxManager()