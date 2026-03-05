"""
DockerSandbox - Docker容器隔离执行环境

参考OpenClaw的Docker Sandbox设计
提供安全的代码执行环境
"""

import asyncio
from typing import Dict, Any, Optional
import os
import tempfile
import logging

logger = logging.getLogger(__name__)


class SandboxExecutionResult:
    """沙箱执行结果"""

    def __init__(
        self,
        success: bool,
        output: str,
        error: Optional[str] = None,
        return_code: int = 0,
        execution_time: float = 0.0,
        container_id: Optional[str] = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.return_code = return_code
        self.execution_time = execution_time
        self.container_id = container_id

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "return_code": self.return_code,
            "execution_time": self.execution_time,
            "container_id": self.container_id,
        }


class DockerSandbox:
    """
    Docker沙箱 - 参考OpenClaw设计

    提供安全的Docker容器执行环境，用于隔离危险操作

    示例:
        sandbox = DockerSandbox(
            image="python:3.11",
            memory_limit="512m",
            cpu_limit=1.0,
            timeout=300
        )

        result = await sandbox.execute(
            command="python script.py",
            cwd="/workspace",
            volumes={"/host/path": "/container/path"}
        )

        if result.success:
            print(result.output)
    """

    def __init__(
        self,
        image: str = "python:3.11",
        memory_limit: str = "512m",
        cpu_limit: float = 1.0,
        timeout: int = 300,
        network_disabled: bool = False,
        read_only_root: bool = False,
        security_opts: Optional[list] = None,
    ):
        """
        初始化Docker沙箱

        Args:
            image: Docker镜像
            memory_limit: 内存限制 (如 "512m", "1g")
            cpu_limit: CPU限制 (如 1.0 表示1个CPU核心)
            timeout: 执行超时时间(秒)
            network_disabled: 是否禁用网络
            read_only_root: 是否只读根文件系统
            security_opts: 安全选项
        """
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.timeout = timeout
        self.network_disabled = network_disabled
        self.read_only_root = read_only_root
        self.security_opts = security_opts or []

        # Docker客户端
        self._client = None

        logger.info(
            f"[DockerSandbox] 初始化: image={image}, "
            f"memory={memory_limit}, cpu={cpu_limit}, timeout={timeout}s"
        )

    async def _get_client(self):
        """获取Docker客户端(懒加载)"""
        if self._client is None:
            try:
                import docker

                self._client = docker.from_env()
            except ImportError:
                raise RuntimeError("Docker SDK未安装,请执行: pip install docker")
        return self._client

    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        workdir: str = "/workspace",
        auto_remove: bool = True,
    ) -> SandboxExecutionResult:
        """
        在Docker容器中执行命令

        Args:
            command: 要执行的命令
            cwd: 当前工作目录(会自动挂载)
            env: 环境变量
            volumes: 卷挂载 {"主机路径": {"bind": "容器路径", "mode": "rw"}}
            workdir: 容器内工作目录
            auto_remove: 是否自动删除容器

        Returns:
            SandboxExecutionResult: 执行结果
        """
        import time

        start_time = time.time()

        try:
            client = await self._get_client()

            # 准备卷挂载
            docker_volumes = {}
            if cwd and os.path.exists(cwd):
                docker_volumes[cwd] = {"bind": workdir, "mode": "rw"}

            if volumes:
                docker_volumes.update(volumes)

            # 准备环境变量
            docker_env = []
            if env:
                docker_env = [f"{k}={v}" for k, v in env.items()]

            # 准备安全选项
            security_opts = self.security_opts.copy()
            if self.read_only_root:
                security_opts.append("read-only:true")

            logger.info(f"[DockerSandbox] 启动容器: {command}")

            # 创建并运行容器
            container = client.containers.run(
                self.image,
                command=f"sh -c '{command}'",
                volumes=docker_volumes,
                environment=docker_env,
                working_dir=workdir,
                mem_limit=self.memory_limit,
                nano_cpus=int(self.cpu_limit * 1e9),
                network_disabled=self.network_disabled,
                security_opt=security_opts if security_opts else None,
                detach=True,
                remove=False,
            )

            container_id = container.id[:12]
            logger.debug(f"[DockerSandbox] 容器启动: {container_id}")

            try:
                # 等待容器完成(带超时)
                result = await self._wait_container(container, self.timeout)

                # 获取日志
                logs = container.logs().decode("utf-8", errors="replace")

                execution_time = time.time() - start_time

                success = result["StatusCode"] == 0

                logger.info(
                    f"[DockerSandbox] 执行完成: container={container_id}, "
                    f"success={success}, time={execution_time:.2f}s"
                )

                return SandboxExecutionResult(
                    success=success,
                    output=logs,
                    error=logs if not success else None,
                    return_code=result["StatusCode"],
                    execution_time=execution_time,
                    container_id=container_id,
                )

            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"[DockerSandbox] 执行失败: {e}")

                return SandboxExecutionResult(
                    success=False,
                    output="",
                    error=str(e),
                    return_code=-1,
                    execution_time=execution_time,
                    container_id=container_id,
                )

            finally:
                # 清理容器
                if auto_remove:
                    try:
                        container.remove()
                        logger.debug(f"[DockerSandbox] 清理容器: {container_id}")
                    except Exception as e:
                        logger.warning(f"[DockerSandbox] 清理容器失败: {e}")

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[DockerSandbox] Docker执行失败: {e}")

            return SandboxExecutionResult(
                success=False,
                output="",
                error=f"Docker执行失败: {str(e)}",
                return_code=-1,
                execution_time=execution_time,
            )

    async def _wait_container(self, container, timeout: int) -> Dict[str, Any]:
        """
        等待容器完成

        Args:
            container: 容器对象
            timeout: 超时时间

        Returns:
            Dict: 容器状态
        """
        loop = asyncio.get_event_loop()

        # 使用线程池执行阻塞的wait操作
        result = await loop.run_in_executor(
            None, lambda: container.wait(timeout=timeout)
        )

        return result

    async def execute_python(
        self, code: str, cwd: Optional[str] = None, timeout: Optional[int] = None
    ) -> SandboxExecutionResult:
        """
        执行Python代码

        Args:
            code: Python代码
            cwd: 工作目录
            timeout: 超时时间

        Returns:
            SandboxExecutionResult: 执行结果
        """
        # 创建临时Python文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # 执行Python文件
            command = f"python {os.path.basename(temp_file)}"

            # 将临时文件目录挂载到容器
            temp_dir = os.path.dirname(temp_file)
            volumes = {temp_dir: {"bind": "/tmp/scripts", "mode": "ro"}}

            return await self.execute(
                command=command,
                cwd=cwd,
                volumes=volumes,
                workdir="/tmp/scripts",
                timeout=timeout or self.timeout,
            )

        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)

    async def execute_script(
        self,
        script_path: str,
        interpreter: str = "python",
        cwd: Optional[str] = None,
        args: Optional[list] = None,
        timeout: Optional[int] = None,
    ) -> SandboxExecutionResult:
        """
        执行脚本文件

        Args:
            script_path: 脚本文件路径
            interpreter: 解释器(python/bash/node等)
            cwd: 工作目录
            args: 脚本参数
            timeout: 超时时间

        Returns:
            SandboxExecutionResult: 执行结果
        """
        # 检查文件存在
        if not os.path.exists(script_path):
            return SandboxExecutionResult(
                success=False, output="", error=f"脚本文件不存在: {script_path}"
            )

        # 构造命令
        script_name = os.path.basename(script_path)
        args_str = " ".join(args) if args else ""
        command = f"{interpreter} {script_name} {args_str}"

        # 挂载脚本目录
        script_dir = os.path.dirname(os.path.abspath(script_path))
        volumes = {script_dir: {"bind": "/workspace/scripts", "mode": "ro"}}

        return await self.execute(
            command=command,
            cwd=cwd,
            volumes=volumes,
            workdir="/workspace/scripts",
            timeout=timeout or self.timeout,
        )


class SandboxManager:
    """
    沙箱管理器 - 管理多个沙箱实例

    示例:
        manager = SandboxManager()

        # 创建沙箱
        sandbox = manager.create_sandbox(
            name="python-env",
            image="python:3.11",
            memory_limit="512m"
        )

        # 执行命令
        result = await sandbox.execute("python -c 'print(1+1)'")
    """

    def __init__(self):
        self._sandboxes: Dict[str, DockerSandbox] = {}

    def create_sandbox(
        self, name: str, image: str = "python:3.11", **kwargs
    ) -> DockerSandbox:
        """
        创建沙箱

        Args:
            name: 沙箱名称
            image: Docker镜像
            **kwargs: 其他参数

        Returns:
            DockerSandbox: 沙箱实例
        """
        sandbox = DockerSandbox(image=image, **kwargs)
        self._sandboxes[name] = sandbox

        logger.info(f"[SandboxManager] 创建沙箱: {name}")

        return sandbox

    def get_sandbox(self, name: str) -> Optional[DockerSandbox]:
        """获取沙箱"""
        return self._sandboxes.get(name)

    def remove_sandbox(self, name: str):
        """删除沙箱"""
        if name in self._sandboxes:
            del self._sandboxes[name]
            logger.info(f"[SandboxManager] 删除沙箱: {name}")

    def list_sandboxes(self) -> Dict[str, Dict[str, Any]]:
        """列出所有沙箱"""
        return {
            name: {
                "image": sandbox.image,
                "memory_limit": sandbox.memory_limit,
                "cpu_limit": sandbox.cpu_limit,
                "timeout": sandbox.timeout,
            }
            for name, sandbox in self._sandboxes.items()
        }


# 全局沙箱管理器
_sandbox_manager: Optional[SandboxManager] = None


def get_sandbox_manager() -> SandboxManager:
    """获取全局沙箱管理器"""
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager


def create_sandbox(name: str = "default", **kwargs) -> DockerSandbox:
    """创建沙箱(便捷函数)"""
    return get_sandbox_manager().create_sandbox(name, **kwargs)
