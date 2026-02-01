"""
本地沙箱实现

基于SandboxRuntime的本地进程隔离实现，支持Mac/Linux。
"""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from derisk.sandbox.providers.base import (
    ExecutionResult,
    ExecutionStatus,
    SandboxRuntime,
    SandboxSession,
    SessionConfig,
)

logger = logging.getLogger(__name__)


class LocalSandboxSession(SandboxSession):
    """本地沙箱会话实现"""

    def __init__(self, session_id: str, config: SessionConfig, runtime_dir: str):
        super().__init__(session_id, config)
        self.runtime_dir = runtime_dir
        self.session_dir = os.path.join(runtime_dir, session_id)
        self._process: Optional[subprocess.Popen] = None
        self._is_active = False

    async def start(self) -> bool:
        """启动会话 - 准备环境"""
        try:
            # 创建会话工作目录
            os.makedirs(self.session_dir, exist_ok=True)
            
            # 如果配置了工作目录，尝试在沙箱内创建
            if self.config.working_dir:
                work_path = os.path.join(self.session_dir, self.config.working_dir.lstrip('/'))
                os.makedirs(work_path, exist_ok=True)
            
            self._is_active = True
            self.created_at = time.time()
            self.last_accessed = time.time()
            return True
        except Exception as e:
            logger.error(f"Failed to start local sandbox session {self.session_id}: {e}")
            return False

    async def stop(self) -> bool:
        """停止会话 - 清理资源"""
        try:
            self._is_active = False
            if os.path.exists(self.session_dir):
                shutil.rmtree(self.session_dir, ignore_errors=True)
            return True
        except Exception as e:
            logger.error(f"Failed to stop local sandbox session {self.session_id}: {e}")
            return False

    async def execute(self, code: str) -> ExecutionResult:
        """在本地环境执行代码"""
        if not self._is_active:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error="Session is not active"
            )

        self.last_accessed = time.time()
        start_time = time.time()

        # 确定工作目录并进行安全检查
        work_dir = self.session_dir
        if self.config.working_dir:
            # 防止路径遍历
            safe_work_dir = os.path.abspath(self.session_dir)
            target_path = os.path.abspath(os.path.join(self.session_dir, self.config.working_dir.lstrip('/')))
            
            if target_path.startswith(safe_work_dir) and os.path.exists(target_path):
                work_dir = target_path
            else:
                # 如果路径非法或不存在，回退到会话根目录，或者报错
                # 这里选择保持在 session_dir
                pass

        # 写入代码到临时文件
        script_name = f"exec_{uuid.uuid4().hex[:8]}.py"
        script_path = os.path.join(work_dir, script_name)
        
        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            # 构建执行命令
            cmd = [
                "python3", 
                script_path
            ]
            
            # 环境变量
            env = os.environ.copy()
            if self.config.environment_vars:
                env.update(self.config.environment_vars)
            
            # 限制 - Mac/Linux下可以使用ulimit，这里做简单的Process封装
            # 注意：实际生产中需要更严格的隔离，如Docker或系统级沙箱(sandbox-exec on Mac, bubblewrap on Linux)
            # 这里实现的是基础的进程隔离
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
                limit=1024*1024 # 1MB buffer
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.config.timeout)
                
                execution_time = time.time() - start_time
                exit_code = process.returncode
                
                output_str = stdout.decode('utf-8') if stdout else ""
                error_str = stderr.decode('utf-8') if stderr else ""
                
                status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.ERROR
                
                return ExecutionResult(
                    status=status,
                    output=output_str,
                    error=error_str,
                    execution_time=execution_time,
                    exit_code=exit_code if exit_code is not None else -1
                )
                
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Execution timed out after {self.config.timeout} seconds",
                    execution_time=self.config.timeout
                )
                
        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error=str(e),
                execution_time=time.time() - start_time
            )
        finally:
            # 清理脚本文件
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except:
                    pass

    async def get_status(self) -> Dict[str, Any]:
        """获取会话状态"""
        return {
            "session_id": self.session_id,
            "is_active": self._is_active,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "runtime_dir": self.session_dir
        }
    
    async def install_dependencies(self, dependencies: List[str]) -> ExecutionResult:
        """在本地会话中安装依赖"""
        if not self._is_active:
             return ExecutionResult(status=ExecutionStatus.ERROR, error="Session not active")
        
        if not dependencies:
            return ExecutionResult(status=ExecutionStatus.SUCCESS, output="No dependencies to install")

        start_time = time.time()
        
        # 使用 pip install --target 安装到会话目录，或者使用 venv
        # 简单起见，这里直接 install 到当前 python 环境 (不推荐用于生产)
        # 更安全的方式是为每个 session 创建 venv
        
        # 这里演示创建 venv 的方式
        venv_path = os.path.join(self.session_dir, ".venv")
        if not os.path.exists(venv_path):
             proc = await asyncio.create_subprocess_exec(
                "python3", "-m", "venv", venv_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
             )
             await proc.communicate()
        
        pip_path = os.path.join(venv_path, "bin", "pip")
        
        cmd = [pip_path, "install"] + dependencies
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300) # 5 min timeout for install
            
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.ERROR,
                output=stdout.decode(),
                error=stderr.decode(),
                execution_time=time.time() - start_time,
                exit_code=process.returncode if process.returncode is not None else -1
            )
        except Exception as e:
             return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error=f"Failed to install dependencies: {e}",
                execution_time=time.time() - start_time
            )


class LocalSandboxRuntime(SandboxRuntime):
    """本地沙箱运行时管理"""
    
    def __init__(self, runtime_id: str = "local_runtime"):
        super().__init__(runtime_id)
        # 基础运行目录，所有会话都在这个目录下隔离
        self.base_dir = os.path.join(tempfile.gettempdir(), "derisk_sandbox", runtime_id)
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"Initialized LocalSandboxRuntime at {self.base_dir}")

    async def create_session(
        self, session_id: str, config: SessionConfig
    ) -> SandboxSession:
        """创建新会话"""
        if session_id in self.sessions:
            return self.sessions[session_id]
            
        session = LocalSandboxSession(session_id, config, self.base_dir)
        if await session.start():
            self.sessions[session_id] = session
            return session
        raise Exception(f"Failed to create session {session_id}")

    async def destroy_session(self, session_id: str) -> bool:
        """销毁会话"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            await session.stop()
            del self.sessions[session_id]
            return True
        return False

    async def list_sessions(self) -> List[str]:
        """列出活跃会话"""
        return [sid for sid, s in self.sessions.items() if s.is_active]

    async def get_session(self, session_id: str) -> Optional[SandboxSession]:
        """获取会话"""
        return self.sessions.get(session_id)

    async def cleanup_expired_sessions(self, max_idle_time: int = 3600) -> int:
        """清理过期会话"""
        now = time.time()
        expired = []
        for sid, session in self.sessions.items():
            if now - session.last_accessed > max_idle_time:
                expired.append(sid)
        
        for sid in expired:
            await self.destroy_session(sid)
            
        return len(expired)

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "runtime_id": self.runtime_id,
            "active_sessions": len(self.sessions),
            "base_dir": self.base_dir
        }

    def supports_language(self, language: str) -> bool:
        """支持的语言"""
        # 本地环境主要支持 python 和 bash
        return language.lower() in ["python", "bash", "shell"]
