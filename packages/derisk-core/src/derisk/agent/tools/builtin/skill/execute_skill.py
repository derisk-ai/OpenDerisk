"""
ExecuteSkillScriptTool - 在 Skill 目录下执行脚本

支持两种执行环境：
- 有沙箱：通过 sandbox client 在沙箱内执行
- 无沙箱：通过本地 subprocess 执行

脚本输出适用常规截断限制。
"""

import asyncio
import os
from typing import Any, Dict, Optional
import logging

from ..sandbox.base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

# Output limits for script execution
_MAX_OUTPUT_BYTES = 16 * 1024  # 16KB
_MAX_OUTPUT_LINES = 500


class ExecuteSkillScriptTool(SandboxToolBase):
    """在 Skill 目录下执行脚本 - 自动检测执行环境"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="skill_exec",
            display_name="Execute Skill Script",
            description=(
                "Execute a script file within a skill's directory. "
                "The script runs with the skill directory as its working directory.\n\n"
                "Parameters:\n"
                "- skill_name: Name of the skill containing the script\n"
                "- file_name: Relative path to the script within the skill directory\n"
                "- args: Optional JSON string of arguments to pass to the script"
            ),
            category=ToolCategory.SKILL,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            timeout=120,
            tags=["skill", "execute", "script"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill containing the script",
                },
                "file_name": {
                    "type": "string",
                    "description": "Relative path to the script file within the skill directory (e.g., 'scripts/analyze.py')",
                },
                "args": {
                    "type": "string",
                    "description": "Optional JSON string of arguments to pass to the script",
                    "default": "",
                },
            },
            "required": ["skill_name", "file_name"],
        }

    def _resolve_skill_dir(
        self, skill_name: str, context: Optional[ToolContext], client: Any = None
    ) -> Optional[str]:
        """Resolve the skill directory path (same logic as ReadSkillTool)."""
        if context:
            config = context.config if hasattr(context, "config") else {}
            if isinstance(config, dict):
                available_skills = config.get("available_skills", {})
                if isinstance(available_skills, dict) and skill_name in available_skills:
                    return available_skills[skill_name]

        if client is not None:
            skill_dir = getattr(client, "skill_dir", None)
            if skill_dir:
                return os.path.join(skill_dir, skill_name)

        if context:
            config = context.config if hasattr(context, "config") else {}
            if isinstance(config, dict):
                skill_dir = config.get("skill_dir")
                if skill_dir:
                    return os.path.join(skill_dir, skill_name)

        try:
            from derisk._private.config import Config

            cfg = Config()
            data_dir = getattr(cfg, "DATA_DIR", None) or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "..", "..", "..", "..", "..",
                "pilot", "data",
            )
            return os.path.join(data_dir, "skill", skill_name)
        except Exception:
            return None

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        client = self._get_sandbox_client(context)
        if client is not None:
            return await self._execute_sandbox(args, context, client)
        else:
            return await self._execute_local(args, context)

    async def _execute_sandbox(
        self, args: Dict[str, Any], context: Optional[ToolContext], client: Any
    ) -> ToolResult:
        """Execute script in sandbox environment."""
        skill_name = args.get("skill_name", "")
        file_name = args.get("file_name", "")
        script_args = args.get("args", "")

        if not skill_name or not file_name:
            return ToolResult.fail(
                error="skill_name and file_name are required",
                tool_name=self.name,
            )

        if ".." in file_name:
            return ToolResult.fail(
                error="file_name cannot contain '..'", tool_name=self.name
            )

        skill_dir = self._resolve_skill_dir(skill_name, context, client)
        if not skill_dir:
            return ToolResult.fail(
                error=f"Cannot resolve skill directory for '{skill_name}'",
                tool_name=self.name,
            )

        script_path = os.path.join(skill_dir, file_name)

        # Determine interpreter based on file extension
        if file_name.endswith(".py"):
            cmd = f"cd '{skill_dir}' && python3 '{script_path}'"
        elif file_name.endswith(".sh"):
            cmd = f"cd '{skill_dir}' && bash '{script_path}'"
        else:
            cmd = f"cd '{skill_dir}' && '{script_path}'"

        if script_args:
            cmd += f" '{script_args}'"

        try:
            if hasattr(client, "shell_exec"):
                result = await client.shell_exec(cmd)
                if hasattr(result, "output"):
                    output = result.output or ""
                elif isinstance(result, dict):
                    output = result.get("output", str(result))
                else:
                    output = str(result)
            else:
                return ToolResult.fail(
                    error="Sandbox client does not support shell execution",
                    tool_name=self.name,
                )

            # Truncate output if too large
            output = self._truncate_output(output)

            return ToolResult.ok(
                output=output,
                tool_name=self.name,
                metadata={
                    "skill_name": skill_name,
                    "script": file_name,
                },
            )

        except Exception as e:
            logger.error(f"[ExecuteSkillScriptTool] Sandbox exec failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Execute script on local filesystem."""
        skill_name = args.get("skill_name", "")
        file_name = args.get("file_name", "")
        script_args = args.get("args", "")

        if not skill_name or not file_name:
            return ToolResult.fail(
                error="skill_name and file_name are required",
                tool_name=self.name,
            )

        if ".." in file_name:
            return ToolResult.fail(
                error="file_name cannot contain '..'", tool_name=self.name
            )

        skill_dir = self._resolve_skill_dir(skill_name, context)
        if not skill_dir or not os.path.isdir(skill_dir):
            return ToolResult.fail(
                error=f"Skill directory not found: {skill_dir}",
                tool_name=self.name,
            )

        script_path = os.path.join(skill_dir, file_name)
        if not os.path.isfile(script_path):
            return ToolResult.fail(
                error=f"Script not found: {script_path}",
                tool_name=self.name,
            )

        # Build command
        if file_name.endswith(".py"):
            cmd = f"python3 '{script_path}'"
        elif file_name.endswith(".sh"):
            cmd = f"bash '{script_path}'"
        else:
            cmd = f"'{script_path}'"

        if script_args:
            cmd += f" '{script_args}'"

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=skill_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=120
            )

            output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                combined = output
                if err_output:
                    combined += f"\n[STDERR]\n{err_output}"
                combined = self._truncate_output(combined)
                return ToolResult.fail(
                    error=f"Script exited with code {process.returncode}",
                    tool_name=self.name,
                    output=combined,
                )

            output = self._truncate_output(output)
            return ToolResult.ok(
                output=output,
                tool_name=self.name,
                metadata={
                    "skill_name": skill_name,
                    "script": file_name,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult.fail(
                error="Script execution timed out (120s)",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[ExecuteSkillScriptTool] Local exec failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    @staticmethod
    def _truncate_output(text: str) -> str:
        """Truncate output to size limits."""
        lines = text.split("\n")
        if len(lines) > _MAX_OUTPUT_LINES:
            lines = lines[:_MAX_OUTPUT_LINES]
            text = "\n".join(lines) + f"\n... [truncated, showing {_MAX_OUTPUT_LINES}/{len(text.splitlines())} lines]"

        if len(text.encode("utf-8", errors="replace")) > _MAX_OUTPUT_BYTES:
            text = text.encode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES].decode(
                "utf-8", errors="ignore"
            )
            text += "\n... [truncated to 16KB]"

        return text
