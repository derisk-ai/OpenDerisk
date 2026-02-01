"""
Register local sandbox provider
"""
from derisk_ext.sandbox.local.runtime import LocalSandboxRuntime, SessionConfig
from derisk.sandbox.providers.base import SandboxSession
from derisk.sandbox.base import SandboxOpts, SandboxBase

from typing import Optional, Dict, Any, List
import logging
import asyncio

logger = logging.getLogger(__name__)

from derisk_ext.sandbox.local.shell_client import LocalShellClient
from derisk_ext.sandbox.local.file_client import LocalFileClient
from derisk_ext.sandbox.local.browser_client import LocalBrowserClient

class LocalSandbox(SandboxBase):
    """Local Sandbox Provider"""

    def __init__(self, **kwargs):
        self.config = kwargs
        self._runtime: Optional[LocalSandboxRuntime] = None
        self._session: Optional[SandboxSession] = None
        self._session_id = kwargs.get("user_id", "default_user") # 使用 user_id 作为会话标识，简单实现
        
        # Initialize clients
        work_dir = self.config.get("work_dir", "/workspace")
        self._shell = LocalShellClient(self._session_id, work_dir, self._get_runtime())
        self._file = LocalFileClient(self._session_id, work_dir, self._get_runtime())
        self._browser = LocalBrowserClient(self._session_id, self._get_runtime())

    @classmethod
    def provider(cls) -> str:
        return "local"

    def _get_runtime(self) -> LocalSandboxRuntime:
        if not self._runtime:
             # 在这里初始化运行时，实际场景可能需要单例或其他管理方式
             # 简单起见，这里每个LocalSandbox实例管理一个Runtime，但共用session目录
             self._runtime = LocalSandboxRuntime()
        return self._runtime

    async def _get_session(self) -> SandboxSession:
        if not self._session:
            runtime = self._get_runtime()
            # 从配置中提取会话配置
            session_config = SessionConfig(
                working_dir=self.config.get("work_dir", "/workspace"),
                # 其他配置映射...
            )
            # 确保会话存在
            self._session = await runtime.create_session(self._session_id, session_config)
        return self._session

    async def run_code(self, code: str, language: str = "python", opts: Optional[SandboxOpts] = None) -> str:
        """运行代码"""
        if language not in ["python", "bash", "shell"]:
             return f"Error: Language {language} not supported by local sandbox."

        try:
            session = await self._get_session()
            
            if language in ["bash", "shell"]:
                wrapped_code = f"""
import subprocess
import sys
# Use triple double quotes for the outer string and handle the inner content carefully
# But since we are generating python code, we just need to make sure the string literal is valid
code_content = {repr(code)}
try:
    result = subprocess.run(code_content, shell=True, capture_output=True, text=True, timeout=60)
    print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
except Exception as e:
    print(e)
"""
                # Update code to wrapped python code
                code = wrapped_code
                # However, LocalSandboxSession executes code by writing it to a .py file and running python3 file.py
                # This works for the wrapper.

            # 直接执行
            result = await session.execute(code)
            
            # 调整输出格式，避免多余的 Error: 
            if result.status.value == "success": # 注意 status 是 Enum
                return result.output
            else:
                return f"Error: {result.error}\nOutput: {result.output}"
                
        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return f"System Error: {str(e)}"

    async def install_dependencies(self, dependencies: List[str]) -> bool:
        """安装依赖"""
        try:
             session = await self._get_session()
             result = await session.install_dependencies(dependencies)
             return result.status.value == "success"
        except Exception:
            return False

    async def get_state(self) -> str:
         session = await self._get_session()
         return "running" if session.is_active else "stopped"

    def __del__(self):
        # 清理逻辑，注意 async cleanup 在析构中不好处理
        pass
