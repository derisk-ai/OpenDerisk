"""Code Action - Execute code in sandbox or local environment.

Supports:
- Python, JavaScript, Shell execution
- Sandbox environment integration
- Local fallback execution
- AgentFileSystem code file management
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from derisk.util.code_utils import UNKNOWN, execute_code, extract_code_v2, infer_lang
from derisk.util.logger import colored
from derisk.vis import SystemVisTag

from derisk.agent.core.action.base import Action, ActionOutput
from derisk.agent.core.agent import AgentContext
from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
from derisk.agent.core.memory.gpts.file_base import FileType
from derisk.agent.core.sandbox_manager import SandboxManager
from derisk.agent.resource.base import Resource


logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of code execution."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    language: str = "python"
    execution_time_ms: int = 0
    file_path: Optional[str] = None
    saved_files: List[str] = field(default_factory=list)


class CodeAction(Action[None]):
    """Code Action for executing code blocks.
    
    Features:
    1. Execute Python, JavaScript, and Shell code
    2. Support both sandbox and local execution
    3. Integrate with SandboxManager for isolated execution
    4. Save code files via AgentFileSystem
    5. Provide detailed execution results
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._code_execution_config = {}
        self.action_view_tag = SystemVisTag.VisCode.value
        self._supported_languages = ["python", "javascript", "js", "bash", "sh", "shell"]

    @property
    def supported_languages(self) -> List[str]:
        return self._supported_languages

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[Resource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        received_message: Optional["AgentMessage"] = None,
        agent_context: Optional[AgentContext] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        file_system: Optional[AgentFileSystem] = None,
        execution_timeout: int = 300,
        max_code_length: int = 50000,
        auto_save_code: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Execute code blocks from AI message.
        
        Args:
            ai_message: AI response containing code blocks
            resource: Agent resource (optional)
            rely_action_out: Previous action output (optional)
            need_vis_render: Whether to render visualization
            received_message: Original received message
            agent_context: Agent context
            sandbox_manager: Sandbox manager for isolated execution
            file_system: Agent file system for saving code
            execution_timeout: Timeout in seconds
            max_code_length: Maximum code length in characters
            auto_save_code: Whether to auto-save code to file system
        """
        action_id = kwargs.get("action_id", uuid.uuid4().hex)
        self.action_uid = action_id

        try:
            code_blocks, text_info = extract_code_v2(ai_message)
            
            if not code_blocks:
                logger.info(f"No executable code found in message: {ai_message[:200] if ai_message else ''}...")
                return ActionOutput(
                    name=self.name,
                    action_id=action_id,
                    is_exe_success=False,
                    content="No executable code found in the response. "
                            "Please provide code in a proper code block format:\n"
                            "```python\n# your code here\n```",
                    thoughts=text_info,
                )

            if len(code_blocks) > 1 and code_blocks[0][0] == UNKNOWN:
                logger.info(f"Unknown code block type in message: {ai_message[:200] if ai_message else ''}...")
                return ActionOutput(
                    name=self.name,
                    action_id=action_id,
                    is_exe_success=False,
                    content="Code block type not recognized. "
                            "Please specify the language (e.g., ```python or ```javascript)",
                    thoughts=text_info,
                )

            # Choose execution mode: sandbox or local
            if sandbox_manager and sandbox_manager.initialized and sandbox_manager.client:
                result = await self._execute_in_sandbox(
                    code_blocks=code_blocks,
                    sandbox_manager=sandbox_manager,
                    file_system=file_system,
                    execution_timeout=execution_timeout,
                    max_code_length=max_code_length,
                    auto_save_code=auto_save_code,
                )
            else:
                result = await self._execute_locally(
                    code_blocks=code_blocks,
                    file_system=file_system,
                    execution_timeout=execution_timeout,
                    max_code_length=max_code_length,
                    auto_save_code=auto_save_code,
                    agent_context=agent_context,
                )

            param = {
                "exit_success": result.success,
                "language": result.language,
                "code": [(code_block[0], code_block[1]) for code_block in code_blocks],
                "log": result.output,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
                "saved_files": result.saved_files,
            }

            view = None
            if self.render_protocol:
                view = await self.render_protocol.display(content=param)

            content = result.output if result.success else f"Execution failed (exit code: {result.exit_code})\n{result.output}"

            return ActionOutput(
                name=self.name,
                action_id=action_id,
                is_exe_success=result.success,
                content=content,
                view=view,
                simple_view=result.output,
                thoughts=text_info or ai_message,
                observations=content,
                metadata={
                    "language": result.language,
                    "execution_time_ms": result.execution_time_ms,
                    "exit_code": result.exit_code,
                    "saved_files": result.saved_files,
                },
            )

        except Exception as e:
            logger.exception("Code action execution failed")
            return ActionOutput(
                name=self.name,
                action_id=action_id,
                is_exe_success=False,
                content=f"Code execution error: {str(e)}",
                thoughts="Execution failed due to an unexpected error",
            )

    async def execute_code_blocks(
        self,
        code_blocks: List[Tuple[str, str]],
        agent_context: Optional[AgentContext] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        file_system: Optional[AgentFileSystem] = None,
        execution_timeout: int = 300,
        max_code_length: int = 50000,
        auto_save_code: bool = True,
    ) -> Tuple[int, str]:
        """Execute code blocks and return (exit_code, logs).
        
        This method is kept for backward compatibility.
        """
        if sandbox_manager and sandbox_manager.initialized and sandbox_manager.client:
            result = await self._execute_in_sandbox(
                code_blocks=code_blocks,
                sandbox_manager=sandbox_manager,
                file_system=file_system,
                execution_timeout=execution_timeout,
                max_code_length=max_code_length,
                auto_save_code=auto_save_code,
            )
        else:
            result = await self._execute_locally(
                code_blocks=code_blocks,
                file_system=file_system,
                execution_timeout=execution_timeout,
                max_code_length=max_code_length,
                auto_save_code=auto_save_code,
                agent_context=agent_context,
            )
        return result.exit_code, result.output

    async def _execute_in_sandbox(
        self,
        code_blocks: List[Tuple[str, str]],
        sandbox_manager: SandboxManager,
        file_system: Optional[AgentFileSystem],
        execution_timeout: int,
        max_code_length: int,
        auto_save_code: bool,
    ) -> ExecutionResult:
        """Execute code blocks in sandbox environment."""
        sandbox = sandbox_manager.client
        if not sandbox:
            return ExecutionResult(
                success=False,
                output="",
                error="Sandbox client not available",
            )

        logs_all = ""
        exit_code = 0
        current_language = "python"
        saved_files = []
        start_time = time.time()

        try:
            for i, code_block in enumerate(code_blocks):
                lang, code = code_block
                if not lang or lang == UNKNOWN:
                    lang = infer_lang(code)
                
                current_language = lang.lower()
                
                print(
                    colored(
                        f"\n>>>>>>>> EXECUTING CODE BLOCK {i} (language: {current_language})...",
                        "red",
                    ),
                    flush=True,
                )

                if len(code) > max_code_length:
                    return ExecutionResult(
                        success=False,
                        output=logs_all,
                        error=f"Code exceeds maximum length: {len(code)} > {max_code_length}",
                        language=current_language,
                    )

                work_dir = sandbox.work_dir or "/workspace"
                timeout = min(execution_timeout, 600)

                if current_language in ["python", "python3"]:
                    exit_code, logs = await self._execute_python_in_sandbox(
                        sandbox, code, work_dir, timeout
                    )
                elif current_language in ["javascript", "js", "node"]:
                    exit_code, logs = await self._execute_javascript_in_sandbox(
                        sandbox, code, work_dir, timeout
                    )
                elif current_language in ["bash", "sh", "shell"]:
                    exit_code, logs = await self._execute_bash_in_sandbox(
                        sandbox, code, work_dir, timeout
                    )
                else:
                    exit_code = 1
                    logs = f"Unsupported language: {current_language}\n"
                    return ExecutionResult(
                        success=False,
                        output=logs_all + logs,
                        error=f"Unsupported language: {current_language}",
                        exit_code=exit_code,
                        language=current_language,
                    )

                logs_all += f"\n[Code Block {i} - {current_language}]\n{logs}\n"

                if auto_save_code and file_system:
                    saved_key = await self._save_code_to_filesystem(
                        file_system=file_system,
                        code=code,
                        language=current_language,
                    )
                    if saved_key:
                        saved_files.append(saved_key)

                if exit_code != 0:
                    break

            execution_time_ms = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                success=exit_code == 0,
                output=logs_all.strip(),
                error=None if exit_code == 0 else logs_all.strip(),
                exit_code=exit_code,
                language=current_language,
                execution_time_ms=execution_time_ms,
                saved_files=saved_files,
            )

        except Exception as e:
            logger.exception("Sandbox execution error")
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                output=logs_all,
                error=f"Sandbox execution error: {str(e)}",
                exit_code=1,
                language=current_language,
                execution_time_ms=execution_time_ms,
                saved_files=saved_files,
            )

    async def _execute_python_in_sandbox(
        self,
        sandbox,
        code: str,
        work_dir: str,
        timeout: int,
    ) -> Tuple[int, str]:
        """Execute Python code in sandbox."""
        try:
            filename = None
            if code.startswith("# filename: "):
                filename = code[11:code.find("\n")].strip()
                code = code[code.find("\n") + 1:]
            
            if filename:
                file_path = f"{work_dir}/{filename}"
                await sandbox.file.create(file_path, code)
                cmd = f"python3 {file_path}"
            else:
                escaped_code = code.replace("'", "'\"'\"'")
                cmd = f"python3 -c '{escaped_code}'"
            
            result = await sandbox.shell.exec_command(
                command=cmd,
                timeout=timeout,
                work_dir=work_dir,
            )
            
            output = getattr(result, "output", "") or ""
            exit_code = getattr(result, "exit_code", 0)
            
            if getattr(result, "status", None) != "completed":
                exit_code = 1
            
            return exit_code, output
            
        except Exception as e:
            return 1, f"Python execution error: {str(e)}"

    async def _execute_javascript_in_sandbox(
        self,
        sandbox,
        code: str,
        work_dir: str,
        timeout: int,
    ) -> Tuple[int, str]:
        """Execute JavaScript code in sandbox."""
        try:
            escaped_code = code.replace("'", "'\"'\"'")
            cmd = f"node -e '{escaped_code}'"
            
            result = await sandbox.shell.exec_command(
                command=cmd,
                timeout=timeout,
                work_dir=work_dir,
            )
            
            output = getattr(result, "output", "") or ""
            exit_code = getattr(result, "exit_code", 0)
            
            return exit_code, output
            
        except Exception as e:
            return 1, f"JavaScript execution error: {str(e)}"

    async def _execute_bash_in_sandbox(
        self,
        sandbox,
        code: str,
        work_dir: str,
        timeout: int,
    ) -> Tuple[int, str]:
        """Execute Bash code in sandbox."""
        try:
            result = await sandbox.shell.exec_command(
                command=code,
                timeout=timeout,
                work_dir=work_dir,
            )
            
            output = getattr(result, "output", "") or ""
            exit_code = getattr(result, "exit_code", 0)
            
            return exit_code, output
            
        except Exception as e:
            return 1, f"Bash execution error: {str(e)}"

    async def _execute_locally(
        self,
        code_blocks: List[Tuple[str, str]],
        file_system: Optional[AgentFileSystem],
        execution_timeout: int,
        max_code_length: int,
        auto_save_code: bool,
        agent_context: Optional[AgentContext] = None,
    ) -> ExecutionResult:
        """Execute code blocks locally (fallback mode)."""
        logs_all = ""
        exit_code = 0
        current_language = "python"
        saved_files = []
        start_time = time.time()

        try:
            for i, code_block in enumerate(code_blocks):
                lang, code = code_block
                if not lang or lang == UNKNOWN:
                    lang = infer_lang(code)
                
                current_language = lang.lower()
                
                print(
                    colored(
                        f"\n>>>>>>>> EXECUTING CODE BLOCK {i} (language: {current_language}) [LOCAL]...",
                        "red",
                    ),
                    flush=True,
                )

                if len(code) > max_code_length:
                    return ExecutionResult(
                        success=False,
                        output=logs_all,
                        error=f"Code exceeds maximum length: {len(code)} > {max_code_length}",
                        language=current_language,
                    )

                filename = None
                if code.startswith("# filename: "):
                    filename = code[11:code.find("\n")].strip()

                # Use original execute_code for local execution
                exit_code, logs, image = execute_code(
                    code,
                    lang=current_language,
                    filename=filename,
                    timeout=execution_timeout,
                    **self._code_execution_config,
                )

                if image is not None:
                    self._code_execution_config["use_docker"] = image

                logs_all += f"\n[Code Block {i} - {current_language}]\n{logs}\n"

                if auto_save_code and file_system:
                    saved_key = await self._save_code_to_filesystem(
                        file_system=file_system,
                        code=code,
                        language=current_language,
                    )
                    if saved_key:
                        saved_files.append(saved_key)

                if exit_code != 0:
                    break

            execution_time_ms = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                success=exit_code == 0,
                output=logs_all.strip(),
                error=None if exit_code == 0 else logs_all.strip(),
                exit_code=exit_code,
                language=current_language,
                execution_time_ms=execution_time_ms,
                saved_files=saved_files,
            )

        except Exception as e:
            logger.exception("Local execution error")
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                output=logs_all,
                error=f"Local execution error: {str(e)}",
                exit_code=1,
                language=current_language,
                execution_time_ms=execution_time_ms,
                saved_files=saved_files,
            )

    async def _save_code_to_filesystem(
        self,
        file_system: AgentFileSystem,
        code: str,
        language: str,
    ) -> Optional[str]:
        """Save code to AgentFileSystem."""
        try:
            extension = self._get_file_extension(language)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_key = f"code_{timestamp}_{uuid.uuid4().hex[:8]}"
            
            await file_system.save_file(
                file_key=file_key,
                data=code,
                file_type=FileType.SANDBOX_FILE,
                extension=extension,
                created_by="CodeAction",
                metadata={"language": language},
            )
            
            logger.info(f"Saved code to file system: {file_key}")
            return file_key
            
        except Exception as e:
            logger.warning(f"Failed to save code to file system: {e}")
            return None

    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "python3": "py",
            "javascript": "js",
            "js": "js",
            "node": "js",
            "bash": "sh",
            "sh": "sh",
            "shell": "sh",
            "sql": "sql",
            "typescript": "ts",
            "ts": "ts",
        }
        return extensions.get(language.lower(), "txt")

    @property
    def use_docker(self) -> Union[bool, str, None]:
        """Whether to use docker for code execution."""
        if self._code_execution_config is False:
            return None
        return self._code_execution_config.get("use_docker")