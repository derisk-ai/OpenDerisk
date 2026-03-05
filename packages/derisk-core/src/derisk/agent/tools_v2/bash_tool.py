"""
BashTool - Shell命令执行工具

参考OpenClaw的多环境执行模式
支持本地执行、Docker Sandbox执行
"""

import asyncio
from typing import Dict, Any, Optional
import os

from .tool_base import ToolBase, ToolMetadata, ToolResult, ToolCategory, ToolRiskLevel, tool_registry


class BashTool(ToolBase):
    """
    Bash工具 - 执行Shell命令

    设计原则:
    1. 多环境支持 - 本地/Docker execution
    2. 安全隔离 - Docker Sandbox
    3. 资源限制 - 超时、内存限制
    4. 错误处理 - 完善的错误返回

    示例:
        tool = BashTool()

        # 本地执行
        result = await tool.execute({
            "command": "ls -la",
            "timeout": 60
        })

        # Docker执行
        result = await tool.execute({
            "command": "python script.py",
            "sandbox": "docker",
            "image": "python:3.11"
        })
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            description="执行Shell命令",
            category=ToolCategory.SHELL,
            risk_level=ToolRiskLevel.HIGH,  # 高风险工具
            requires_permission=True,
            tags=["shell", "execution", "system"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的Shell命令"},
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "超时时间(秒),默认120秒",
                },
                "cwd": {"type": "string", "description": "工作目录,默认当前目录"},
                "env": {"type": "object", "description": "环境变量"},
                "sandbox": {
                    "type": "string",
                    "enum": ["local", "docker"],
                    "default": "local",
                    "description": "执行环境: local(本地) 或 docker(Docker容器)",
                },
                "image": {
                    "type": "string",
                    "default": "python:3.11",
                    "description": "Docker镜像名称(sandbox=docker时有效)",
                },
                "memory_limit": {
                    "type": "string",
                    "default": "512m",
                    "description": "Docker内存限制(sandbox=docker时有效)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        执行Shell命令

        Args:
            args: 工具参数
                - command: 要执行的命令
                - timeout: 超时时间(秒)
                - cwd: 工作目录
                - env: 环境变量
                - sandbox: 执行环境(local/docker)
                - image: Docker镜像
                - memory_limit: 内存限制
            context: 执行上下文

        Returns:
            ToolResult: 执行结果
        """
        # 提取参数
        command = args["command"]
        timeout = args.get("timeout", 120)
        cwd = args.get("cwd", os.getcwd())
        env = args.get("env")
        sandbox = args.get("sandbox", "local")
        image = args.get("image", "python:3.11")
        memory_limit = args.get("memory_limit", "512m")

        try:
            if sandbox == "docker":
                result = await self._execute_in_docker(
                    command, cwd, env, timeout, image, memory_limit
                )
            else:
                result = await self._execute_local(command, cwd, env, timeout)

            return result

        except Exception as e:
            return ToolResult(success=False, output="", error=f"执行失败: {str(e)}")

    async def _execute_local(
        self, command: str, cwd: str, env: Optional[Dict[str, str]], timeout: int
    ) -> ToolResult:
        """
        本地执行命令

        Args:
            command: 要执行的命令
            cwd: 工作目录
            env: 环境变量
            timeout: 超时时间

        Returns:
            ToolResult: 执行结果
        """
        try:
            # 合并环境变量
            exec_env = os.environ.copy()
            if env:
                exec_env.update(env)

            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                env=exec_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True,
            )

            # 等待执行完成(带超时)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )

                # 解码输出
                stdout_str = stdout.decode("utf-8", errors="replace")
                stderr_str = stderr.decode("utf-8", errors="replace")

                success = process.returncode == 0

                return ToolResult(
                    success=success,
                    output=stdout_str,
                    error=stderr_str if not success else None,
                    metadata={
                        "return_code": process.returncode,
                        "stdout_len": len(stdout_str),
                        "stderr_len": len(stderr_str),
                        "execution_mode": "local",
                    },
                )

            except asyncio.TimeoutError:
                # 超时,杀死进程
                process.kill()
                await process.wait()

                return ToolResult(
                    success=False,
                    output="",
                    error=f"命令执行超时({timeout}秒),进程已终止",
                    metadata={"execution_mode": "local", "timeout": timeout},
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"本地执行失败: {str(e)}",
                metadata={"execution_mode": "local"},
            )

    async def _execute_in_docker(
        self,
        command: str,
        cwd: str,
        env: Optional[Dict[str, str]],
        timeout: int,
        image: str,
        memory_limit: str,
    ) -> ToolResult:
        """
        在Docker容器中执行命令

        Args:
            command: 要执行的命令
            cwd: 工作目录(会挂载到容器)
            env: 环境变量
            timeout: 超时时间
            image: Docker镜像
            memory_limit: 内存限制

        Returns:
            ToolResult: 执行结果
        """
        try:
            import docker
        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="Docker SDK未安装,请执行: pip install docker",
            )

        try:
            # 创建Docker客户端
            client = docker.from_env()

            # 准备卷挂载
            volumes = {}
            if cwd and os.path.exists(cwd):
                volumes[cwd] = {"bind": "/workspace", "mode": "rw"}

            # 准备环境变量
            docker_env = []
            if env:
                docker_env = [f"{k}={v}" for k, v in env.items()]

            # 运行容器
            container = client.containers.run(
                image,
                command=f"sh -c '{command}'",
                volumes=volumes,
                environment=docker_env,
                working_dir="/workspace" if cwd else None,
                mem_limit=memory_limit,
                detach=True,
                remove=False,
            )

            try:
                # 等待容器完成(带超时)
                result = container.wait(timeout=timeout)

                # 获取日志
                logs = container.logs().decode("utf-8", errors="replace")

                success = result["StatusCode"] == 0

                return ToolResult(
                    success=success,
                    output=logs,
                    error=logs if not success else None,
                    metadata={
                        "return_code": result["StatusCode"],
                        "container_id": container.id[:12],
                        "image": image,
                        "execution_mode": "docker",
                        "memory_limit": memory_limit,
                    },
                )

            except Exception as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Docker执行失败: {str(e)}",
                    metadata={"execution_mode": "docker"},
                )

            finally:
                # 清理容器
                try:
                    container.remove()
                except:
                    pass

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Docker执行失败: {str(e)}",
                metadata={"execution_mode": "docker"},
            )


# 注册BashTool
tool_registry.register(BashTool())
