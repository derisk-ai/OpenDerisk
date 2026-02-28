from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel


class SandboxResult(BaseModel):
    """沙箱执行结果"""
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    duration_ms: float = 0
    metadata: Dict[str, Any] = {}


class SandboxConfig(BaseModel):
    """沙箱配置"""
    image: str = "python:3.11-slim"
    timeout: int = 300
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_enabled: bool = False
    workdir: str = "/workspace"
    env: Dict[str, str] = {}
    volumes: Dict[str, str] = {}
    auto_remove: bool = True


class SandboxBase(ABC):
    """沙箱基类"""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
    
    @abstractmethod
    async def execute(
        self, 
        command: str, 
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> SandboxResult:
        """在沙箱中执行命令"""
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """启动沙箱"""
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """停止沙箱"""
        pass
    
    @abstractmethod
    async def is_running(self) -> bool:
        """检查沙箱是否运行"""
        pass