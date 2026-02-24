"""Code Assistant Agent - Professional Code Generation and Execution Agent.

A specialized sub-agent for generating and executing code in sandbox environments.
Core capabilities:
1. Generate code in multiple languages (Python by default)
2. Execute code safely in sandbox environments
3. Manage code files through AgentFileSystem
4. Support iterative code refinement based on execution results
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from derisk._private.pydantic import Field
from derisk.core import ModelMessageRoleType
from derisk.sandbox.base import SandboxBase
from derisk.util.string_utils import str_to_bool

from ...core.agent import Agent, AgentMessage
from ...core.base_agent import ConversableAgent
from ...core.file_system.agent_file_system import AgentFileSystem
from ...core.memory.gpts.file_base import FileType
from ...core.profile import ProfileConfig
from .actions.code_action import CodeAction, ExecutionResult
from .prompt import (
    CHECK_RESULT_SYSTEM_MESSAGE,
    SYSTEM_PROMPT,
    USER_PROMPT,
)

logger = logging.getLogger(__name__)


class CodeLanguage(Enum):
    """Supported programming languages."""
    
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BASH = "bash"
    SQL = "sql"
    UNKNOWN = "unknown"





class CodeAssistantAgent(ConversableAgent):
    """Professional Code Assistant Agent for code generation and execution.
    
    This agent specializes in:
    1. Generating code solutions based on user requirements
    2. Executing code safely in sandbox environments
    3. Managing code files through AgentFileSystem
    4. Iteratively refining code based on execution feedback
    
    Attributes:
        sandbox_manager: Manager for sandbox environments
        file_system: File system for code file management
        default_language: Default programming language (Python)
        max_code_length: Maximum code length in characters
        execution_timeout: Timeout for code execution in seconds
        prompt_language: Language for prompts ("zh" for Chinese, "en" for English)
    """

    default_language: str = Field(default="python", description="Default programming language")
    max_code_length: int = Field(default=50000, description="Maximum code length in characters")
    execution_timeout: int = Field(default=300, description="Execution timeout in seconds")
    auto_save_code: bool = Field(default=True, description="Auto-save executed code to file system")


    profile: ProfileConfig = ProfileConfig(
        name="CodeAssistant",
        role="CodeAssistant",
        goal="你是一个专业的代码助手，专注于代码生成和执行。",
        system_prompt_template=SYSTEM_PROMPT,
        user_prompt_template=USER_PROMPT,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._execution_history: List[ExecutionResult] = []
        self._current_sandbox: Optional[SandboxBase] = None
        self._init_actions([CodeAction])

    @property
    def execution_history(self) -> List[ExecutionResult]:
        return self._execution_history

    @property
    def current_sandbox(self) -> Optional[SandboxBase]:
        if self.sandbox_manager:
            return self.sandbox_manager.client
        return self._current_sandbox

    async def get_file_system(self) -> Optional[AgentFileSystem]:
        if not self.agent_context:
            return None
        
        return AgentFileSystem(
            conv_id=self.agent_context.conv_id,
            session_id=self.agent_context.conv_session_id,
            sandbox=self.current_sandbox,
        )

    async def prepare_act_param(
        self,
        received_message: Optional[AgentMessage] = None,
        sender: Optional[Agent] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        params = await super().prepare_act_param(
            received_message=received_message,
            sender=sender,
            rely_messages=rely_messages,
            **kwargs,
        )
        params["sandbox_manager"] = self.sandbox_manager
        params["file_system"] = await self.get_file_system()
        params["execution_timeout"] = self.execution_timeout
        params["max_code_length"] = self.max_code_length
        params["auto_save_code"] = self.auto_save_code
        return params

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        save_to_file: bool = False,
        file_key: Optional[str] = None,
    ) -> ExecutionResult:
        if not self.sandbox_manager or not self.sandbox_manager.client:
            return ExecutionResult(
                success=False,
                error="Sandbox environment not available",
                language=language,
            )
        
        start_time = datetime.now()
        
        try:
            if len(code) > self.max_code_length:
                return ExecutionResult(
                    success=False,
                    error=f"Code exceeds maximum length ({len(code)} > {self.max_code_length})",
                    language=language,
                )
            
            sandbox = self.sandbox_manager.client
            work_dir = sandbox.work_dir or "/workspace"
            
            if language.lower() in ["python", "python3"]:
                result = await sandbox.shell.exec_command(
                    command=f"python3 -c {repr(code)}",
                    timeout=timeout or self.execution_timeout,
                    work_dir=work_dir,
                )
            elif language.lower() in ["javascript", "js", "node"]:
                result = await sandbox.shell.exec_command(
                    command=f"node -e {repr(code)}",
                    timeout=timeout or self.execution_timeout,
                    work_dir=work_dir,
                )
            elif language.lower() in ["bash", "sh", "shell"]:
                result = await sandbox.shell.exec_command(
                    command=code,
                    timeout=timeout or self.execution_timeout,
                    work_dir=work_dir,
                )
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unsupported language: {language}",
                    language=language,
                )
            
            output = getattr(result, "output", "") or ""
            exit_code = getattr(result, "exit_code", 0)
            success = exit_code == 0
            
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            saved_files = []
            if save_to_file and self.auto_save_code:
                file_system = await self.get_file_system()
                if file_system:
                    saved_key = file_key or f"code_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                    extension = self._get_file_extension(language)
                    await file_system.save_file(
                        file_key=saved_key,
                        data=code,
                        file_type=FileType.SANDBOX_FILE,
                        extension=extension,
                        created_by=self.name,
                    )
                    saved_files.append(saved_key)
            
            execution_result = ExecutionResult(
                success=success,
                output=output,
                error=None if success else output,
                exit_code=exit_code,
                language=language,
                execution_time_ms=execution_time_ms,
                saved_files=saved_files,
            )
            
            self._execution_history.append(execution_result)
            return execution_result
            
        except Exception as e:
            logger.exception("Code execution failed")
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return ExecutionResult(
                success=False,
                error=str(e),
                language=language,
                execution_time_ms=execution_time_ms,
            )

    def _get_file_extension(self, language: str) -> str:
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
        }
        return extensions.get(language.lower(), "txt")

    async def save_code_file(
        self,
        code: str,
        file_name: str,
        language: str = "python",
        description: Optional[str] = None,
    ) -> Optional[str]:
        file_system = await self.get_file_system()
        if not file_system:
            logger.warning("File system not available for saving code")
            return None
        
        extension = self._get_file_extension(language)
        file_key = f"code_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{file_name}"
        
        metadata = {"language": language}
        if description:
            metadata["description"] = description
        
        result = await file_system.save_file(
            file_key=file_key,
            data=code,
            file_type=FileType.SANDBOX_FILE,
            extension=extension,
            file_name=file_name if "." in file_name else f"{file_name}.{extension}",
            created_by=self.name,
            metadata=metadata,
        )
        
        logger.info(f"Saved code file: {result.file_key} -> {result.local_path}")
        return result.file_key

    async def load_code_file(self, file_key: str) -> Optional[str]:
        file_system = await self.get_file_system()
        if not file_system:
            return None
        
        content = await file_system.read_file(file_key)
        if content:
            logger.info(f"Loaded code file: {file_key}")
        return content

    async def list_code_files(self) -> List[Dict[str, Any]]:
        file_system = await self.get_file_system()
        if not file_system:
            return []
        
        files = await file_system.list_files(file_type=FileType.SANDBOX_FILE)
        return [
            {
                "file_key": f.file_key,
                "file_name": f.file_name,
                "file_size": f.file_size,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "metadata": f.metadata,
            }
            for f in files
        ]

    async def correctness_check(
        self,
        message: AgentMessage,
        **kwargs,
    ) -> Tuple[bool, Optional[str]]:
        task_goal = message.current_goal
        action_report = message.action_report
        
        if not action_report:
            return False, "No execution results to check"
        
        if isinstance(action_report, list) and len(action_report) > 0:
            action_report = action_report[0]
        
        from ...util.llm.llm_client import AgentLLMOut
        
        check_prompt = CHECK_RESULT_SYSTEM_MESSAGE
        
        agent_llm_out: AgentLLMOut = await self.thinking(
            messages=[
                AgentMessage(
                    role=ModelMessageRoleType.HUMAN,
                    content=(
                        f"Please analyze the following task goal and execution result:\n\n"
                        f"Task Goal: {task_goal}\n\n"
                        f"Execution Result: {action_report.content}\n\n"
                        "Provide your judgment based on the rules."
                    ),
                )
            ],
            reply_message_id=uuid.uuid4().hex,
            prompt=check_prompt,
        )
        
        success = str_to_bool(agent_llm_out.content)
        fail_reason = None
        
        if not success:
            fail_reason = (
                f"Code executed successfully but did not achieve the goal. "
                f"Reason: {agent_llm_out.content}"
            )
        
        return success, fail_reason

    def get_execution_summary(self) -> Dict[str, Any]:
        if not self._execution_history:
            return {"total_executions": 0, "successful": 0, "failed": 0}
        
        successful = sum(1 for r in self._execution_history if r.success)
        failed = len(self._execution_history) - successful
        total_time = sum(r.execution_time_ms for r in self._execution_history)
        
        return {
            "total_executions": len(self._execution_history),
            "successful": successful,
            "failed": failed,
            "total_execution_time_ms": total_time,
            "languages_used": list(set(r.language for r in self._execution_history)),
        }