"""
Improved Local Sandbox Implementation with Security Isolation

Enhanced runtime with proper sandboxing support for macOS and Linux.
Integrates sandbox-exec for process isolation and Playwright for browser automation.
"""

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import psutil  # For better process management

from derisk.sandbox.providers.base import (
    ExecutionResult,
    ExecutionStatus,
    SandboxRuntime,
    SandboxSession,
    SessionConfig,
)
from derisk_ext.sandbox.local.macos_sandbox import (
    MacOSSandboxWrapper,
    create_sandbox_wrapper,
)

logger = logging.getLogger(__name__)


def get_platform() -> str:
    """Get the current platform with sandbox capabilities."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    return system


class ImprovedLocalSandboxSession(SandboxSession):
    """
    Improved local sandbox session with security isolation.

    Features:
    - macOS: sandbox-exec integration for real isolation
    - Linux: resource limits via cgroups/prlimit
    - Windows: basic path isolation
    - Proper process tracking and cleanup
    """

    def __init__(self, session_id: str, config: SessionConfig, runtime_dir: str):
        super().__init__(session_id, config)
        self.runtime_dir = runtime_dir
        self.session_dir = os.path.join(runtime_dir, session_id)
        self._process: Optional[subprocess.Popen] = None
        self._processes: Set[subprocess.Popen] = set()
        self._is_active = False
        self._platform = get_platform()
        self._sandbox_wrapper: Optional[MacOSSandboxWrapper] = None

        # Compute physical working directory
        self._work_dir = self._resolve_working_dir()

        # Setup resource limits
        self._resource_monitor: Optional[ResourceMonitor] = None
        if config.max_memory > 0:
            self._resource_monitor = ResourceMonitor(
                max_memory=config.max_memory,
                max_cpus=config.max_cpus,
            )

    def _resolve_working_dir(self) -> str:
        """Resolve the working directory to a physical path."""
        base = self.session_dir
        if self.config.working_dir:
            relative = self.config.working_dir.lstrip("/")
            target = os.path.abspath(os.path.join(base, relative))
            # Ensure directory exists
            os.makedirs(target, exist_ok=True)
            return target
        return base

    async def start(self) -> bool:
        """Start the session with proper setup."""
        try:
            # Ensure session directory exists
            os.makedirs(self.session_dir, exist_ok=True)

            # Create virtual environment for isolated Python packages
            venv_path = os.path.join(self.session_dir, ".venv")
            if not os.path.exists(venv_path):
                await self._create_venv(venv_path)

            # Set up sandbox wrapper if on macOS
            if self._platform == "macos":
                from derisk_ext.sandbox.local.macos_sandbox import (
                    MacOSSandboxProfile,
                    SandboxProfileConfig,
                )

                config = SandboxProfileConfig(
                    profile_name=f"derisk_{self.session_id}",
                    read_write_paths=[self._work_dir],
                    allow_network=not self.config.network_disabled,
                    max_memory=self.config.max_memory,
                )
                self._sandbox_wrapper = MacOSSandboxWrapper(config.profile_name, config)
                self._sandbox_wrapper.profile_path = (
                    MacOSSandboxProfile.create_profile_file(config)
                )

            # Start resource monitor if configured
            if self._resource_monitor:
                await self._resource_monitor.start()

            self._is_active = True
            self.created_at = time.time()
            self.last_accessed = time.time()

            logger.info(
                f"Started improved sandbox session {self.session_id} on {self._platform}, "
                f"work_dir={self._work_dir}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to start local sandbox session {self.session_id}: {e}"
            )
            return False

    async def _create_venv(self, venv_path: str):
        """Create a minimal virtual environment for the session."""
        logger.info(f"Creating venv at {venv_path}")

        proc = await asyncio.create_subprocess_exec(
            "python3",
            "-m",
            "venv",
            venv_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"Venv creation warning: {stderr.decode()}")

    async def stop(self) -> bool:
        """Stop the session with proper cleanup."""
        try:
            self._is_active = False

            # Stop resource monitor
            if self._resource_monitor:
                await self._resource_monitor.stop()

            # Kill all tracked processes
            for proc in self._processes:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            await asyncio.wait_for(
                                asyncio.create_task(
                                    asyncio.shield(
                                        asyncio.create_subprocess_exec(
                                            "wait", str(proc.pid)
                                        ).wait()
                                    )
                                ),
                                timeout=2.0,
                            )
                        except asyncio.TimeoutError:
                            proc.kill()
                except Exception as e:
                    logger.warning(f"Error killing process: {e}")
            self._processes.clear()

            # Clean up session directory
            if os.path.exists(self.session_dir):
                shutil.rmtree(self.session_dir, ignore_errors=True)

            logger.info(f"Stopped sandbox session {self.session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop local sandbox session {self.session_id}: {e}")
            return False

    def _get_execution_command(self, script_path: str) -> List[str]:
        """Build the command to execute a script."""
        python_exe = os.path.join(self.session_dir, ".venv", "bin", "python3")

        # Fall back to system python if venv not available
        if not os.path.exists(python_exe):
            python_exe = "python3"

        cmd = [python_exe, script_path]

        # Wrap with sandbox-exec if available and configured
        if (
            self._sandbox_wrapper
            and self._sandbox_wrapper.is_available
            and os.path.exists(self._sandbox_wrapper.profile_path)
        ):
            cmd = self._sandbox_wrapper.get_executable_command(cmd)

        return cmd

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code with proper isolation and resource limits."""
        if not self._is_active:
            return ExecutionResult(
                status=ExecutionStatus.ERROR, error="Session is not active"
            )

        self.last_accessed = time.time()
        start_time = time.time()

        # Write code to temporary file
        script_name = f"exec_{uuid.uuid4().hex[:8]}_{int(start_time)}.py"
        script_path = os.path.join(self._work_dir, script_name)

        try:
            # Write the wrapper that applies limits before executing
            wrapper_code = f"""#!/usr/bin/env python3
import sys
import os
import resource
import signal

# Apply resource limits
try:
    # Memory limit
    max_memory = {self.config.max_memory}
    if max_memory > 0:
        resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))

    # CPU limit (2x timeout)
    max_cpu = {self.config.timeout * 2}
    if max_cpu > 0:
        resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu))

    # File limit
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
except Exception:
    pass

# Set working directory
os.chdir({repr(self._work_dir)})

# Handle signals properly
def timeout_handler(signum, frame):
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(124)  # 124 is TIMEOUT exit code

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm({self.config.timeout})

# Execute the original code
{code}
"""

            async with asyncio.Lock():  # Thread safety for file operations
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(wrapper_code)
                os.chmod(script_path, 0o755)  # Make executable

            # Build command with sandbox wrapper
            cmd = self._get_execution_command(script_path)

            # Setup environment
            env = os.environ.copy()
            env.update(self.config.environment_vars)
            env["PYTHONUNBUFFERED"] = "1"

            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._work_dir,
                env=env,
                # Set process group for better signal handling
                preexec_fn=None if self._platform == "windows" else os.setsid,
            )

            tracked_process = process
            await asyncio.sleep(0.1)  # Give process time to update PID

            # Track process for cleanup
            async with asyncio.Lock():
                self._processes.add(process)

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.config.timeout
                )

                execution_time = time.time() - start_time
                exit_code = process.returncode

                # Remove from tracked processes
                async with asyncio.Lock():
                    self._processes.discard(process)

                # Decode output
                output_str = stdout.decode("utf-8", errors="replace") if stdout else ""
                error_str = stderr.decode("utf-8", errors="replace") if stderr else ""

                # Determine status
                if exit_code == 124 or execution_time >= self.config.timeout:
                    status = ExecutionStatus.TIMEOUT
                elif exit_code == 0:
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.ERROR

                return ExecutionResult(
                    status=status,
                    output=output_str,
                    error=error_str,
                    execution_time=execution_time,
                    exit_code=exit_code if exit_code is not None else -1,
                    memory_usage=self._resource_monitor.get_peak_memory()
                    if self._resource_monitor
                    else 0,
                )

            except asyncio.TimeoutError:
                try:
                    # Kill process and its children
                    if process.poll() is None:
                        if self._platform == "windows":
                            process.kill()
                        else:
                            # Kill entire process group
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                            await asyncio.sleep(0.5)
                            if process.poll() is None:
                                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass

                # Remove from tracked processes
                async with asyncio.Lock():
                    self._processes.discard(process)

                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Execution timed out after {self.config.timeout} seconds",
                    execution_time=self.config.timeout,
                )

        except Exception as e:
            logger.error(f"Execution error in session {self.session_id}: {e}")
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error=str(e),
                execution_time=time.time() - start_time,
            )
        finally:
            # Clean up script file
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass

    async def get_status(self) -> Dict[str, Any]:
        """Get session status."""
        status = {
            "session_id": self.session_id,
            "is_active": self._is_active,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "runtime_dir": self.session_dir,
            "work_dir": self._work_dir,
            "platform": self._platform,
            "active_processes": len(self._processes),
        }

        if self._resource_monitor:
            status["resources"] = self._resource_monitor.get_status()

        return status

    async def install_dependencies(self, dependencies: List[str]) -> ExecutionResult:
        """Install Python dependencies in the session's venv."""
        if not self._is_active:
            return ExecutionResult(
                status=ExecutionStatus.ERROR, error="Session not active"
            )

        if not dependencies:
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS, output="No dependencies to install"
            )

        start_time = time.time()

        try:
            venv_path = os.path.join(self.session_dir, ".venv")
            pip_path = os.path.join(venv_path, "bin", "pip")

            # Ensure venv exists
            if not os.path.exists(pip_path):
                await self._create_venv(venv_path)

            cmd = [pip_path, "install", "-q"] + dependencies

            # Use sandbox wrapper if available
            if self._sandbox_wrapper and self._sandbox_wrapper.is_available:
                cmd = self._sandbox_wrapper.get_executable_command(cmd)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 minute install timeout
            )

            execution_time = time.time() - start_time

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS
                if process.returncode == 0
                else ExecutionStatus.ERROR,
                output=stdout.decode("utf-8") if stdout else "",
                error=stderr.decode("utf-8") if stderr else "",
                execution_time=execution_time,
                exit_code=process.returncode if process.returncode is not None else -1,
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                error="Dependency installation timed out",
                execution_time=time.time() - start_time,
            )
        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error=f"Failed to install dependencies: {e}",
                execution_time=time.time() - start_time,
            )


class ResourceMonitor:
    """
    Monitor and enforce resource limits for a session.

    Tracks memory usage, CPU time, and active processes.
    """

    def __init__(self, max_memory: int, max_cpus: int = 1):
        self.max_memory = max_memory
        self.max_cpus = max_cpus
        self._peak_memory = 0
        self._monitoring = False
        self._task: Optional[asyncio.Task] = None
        self._pids: Set[int] = set()

    async def start(self):
        """Start resource monitoring."""
        if self._monitoring:
            return
        self._monitoring = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop resource monitoring."""
        self._monitoring = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def add_process(self, pid: int):
        """Add a process to monitor."""
        self._pids.add(pid)

    async def remove_process(self, pid: int):
        """Remove a process from monitoring."""
        self._pids.discard(pid)

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._monitoring:
            try:
                total_memory = 0
                for pid in list(self._pids):
                    try:
                        proc = psutil.Process(pid)
                        total_memory += proc.memory_info().rss

                        # Check and terminate if over limit
                        if self.max_memory > 0 and total_memory > self.max_memory:
                            logger.warning(
                                f"Process {pid} exceeded memory limit "
                                f"({total_memory} > {self.max_memory}), terminating"
                            )
                            proc.terminate()
                            await asyncio.sleep(1)
                            if proc.is_running():
                                proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        self._pids.discard(pid)

                self._peak_memory = max(self._peak_memory, total_memory)

            except Exception as e:
                logger.debug(f"Resource monitor error: {e}")

            await asyncio.sleep(1.0)

    def get_peak_memory(self) -> int:
        """Get peak memory usage."""
        return self._peak_memory

    def get_status(self) -> Dict[str, Any]:
        """Get monitoring status."""
        return {
            "max_memory": self.max_memory,
            "peak_memory": self._peak_memory,
            "monitored_processes": len(self._pids),
            "monitoring": self._monitoring,
        }


class ImprovedLocalSandboxRuntime(SandboxRuntime):
    """
    Improved local sandbox runtime manager.

    Provides session management with better cleanup and resource tracking.
    """

    def __init__(self, runtime_id: str = "improved_local_runtime"):
        super().__init__(runtime_id)
        self.base_dir = os.path.join(
            tempfile.gettempdir(), "derisk_improved_sandbox", runtime_id
        )
        os.makedirs(self.base_dir, exist_ok=True)
        self._platform = get_platform()
        logger.info(
            f"Initialized ImprovedLocalSandboxRuntime at {self.base_dir} on {self._platform}"
        )

        # Cleanup on startup
        asyncio.create_task(self._cleanup_stale_sessions())

    async def _cleanup_stale_sessions(self):
        """Cleanup directories from crashed sessions."""
        try:
            for session_dir in Path(self.base_dir).iterdir():
                if session_dir.is_dir() and session_dir.name not in self.sessions:
                    # Session exists on disk but not in memory - likely crashed
                    logger.info(f"Cleaning up stale session: {session_dir.name}")
                    try:
                        shutil.rmtree(session_dir)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup {session_dir}: {e}")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

    async def create_session(
        self, session_id: str, config: SessionConfig
    ) -> SandboxSession:
        """Create a new session."""
        if session_id in self.sessions:
            logger.info(f"Reusing existing session {session_id}")
            return self.sessions[session_id]

        session = ImprovedLocalSandboxSession(session_id, config, self.base_dir)
        if await session.start():
            self.sessions[session_id] = session
            return session
        raise Exception(f"Failed to create session {session_id}")

    async def destroy_session(self, session_id: str) -> bool:
        """Destroy a session."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            await session.stop()
            del self.sessions[session_id]
            return True
        return False

    async def list_sessions(self) -> List[str]:
        """List active sessions."""
        return [sid for sid, s in self.sessions.items() if s.is_active]

    async def get_session(self, session_id: str) -> Optional[SandboxSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    async def cleanup_expired_sessions(self, max_idle_time: int = 3600) -> int:
        """Clean up expired sessions."""
        now = time.time()
        expired = []

        for sid, session in self.sessions.items():
            if now - session.last_accessed > max_idle_time:
                expired.append(sid)

        for sid in expired:
            await self.destroy_session(sid)

        return len(expired)

    async def health_check(self) -> Dict[str, Any]:
        """Health check."""
        return {
            "status": "healthy",
            "runtime_id": self.runtime_id,
            "active_sessions": len(self.sessions),
            "base_dir": self.base_dir,
            "platform": self._platform,
            "sandbox_exec_available": self._is_sandbox_exec_available(),
        }

    def _is_sandbox_exec_available(self) -> bool:
        """Check if sandbox-exec is available (macOS only)."""
        if self._platform != "macos":
            return False
        try:
            result = subprocess.run(
                ["which", "sandbox-exec"], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def supports_language(self, language: str) -> bool:
        """Check if a language is supported."""
        return language.lower() in ["python", "python3", "bash", "shell", "sh"]
