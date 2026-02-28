from typing import Optional
from .base import SandboxBase, SandboxConfig
from .docker_sandbox import DockerSandbox
from .local_sandbox import LocalSandbox


class SandboxFactory:
    """沙箱工厂 - 自动选择最佳沙箱实现"""
    
    @staticmethod
    async def create(
        prefer_docker: bool = True,
        config: Optional[SandboxConfig] = None
    ) -> SandboxBase:
        """创建沙箱实例"""
        if prefer_docker:
            docker_sandbox = DockerSandbox(config)
            if await docker_sandbox._check_docker():
                return docker_sandbox
        
        return LocalSandbox(config)
    
    @staticmethod
    def create_docker(config: Optional[SandboxConfig] = None) -> DockerSandbox:
        """强制创建Docker沙箱"""
        return DockerSandbox(config)
    
    @staticmethod
    def create_local(config: Optional[SandboxConfig] = None) -> LocalSandbox:
        """创建本地沙箱"""
        return LocalSandbox(config)