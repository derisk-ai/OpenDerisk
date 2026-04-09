"""
ReadSkillTool - 读取 Skill 内容

支持两种执行环境：
- 有沙箱：通过 sandbox client 读取沙箱内的 skill 文件
- 无沙箱：通过本地文件系统读取

Skill 内容不受常规截断限制，返回完整的 SKILL.md 指令。
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
import logging

from ..sandbox.base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class ReadSkillTool(SandboxToolBase):
    """读取 Skill 内容工具 - 自动检测执行环境"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="skill_read",
            display_name="Read Skill Content",
            description=(
                "Read a skill's SKILL.md instructions or other files from the skill directory. "
                "The skill content is returned in full without truncation. "
                "After loading a skill, follow its instructions immediately.\n\n"
                "Use this tool instead of generic read/view tools when working with skills, "
                "as it provides proper skill path resolution and content protection."
            ),
            category=ToolCategory.SKILL,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            timeout=60,
            tags=["skill", "read", "knowledge"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill to read (matches the skill directory name or skill_code)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Relative path within the skill directory to read. Defaults to 'SKILL.md'",
                    "default": "SKILL.md",
                },
            },
            "required": ["skill_name"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        client = self._get_sandbox_client(context)
        if client is not None:
            return await self._execute_sandbox(args, context, client)
        else:
            return await self._execute_local(args, context)

    def _resolve_skill_dir(
        self, skill_name: str, context: Optional[ToolContext], client: Any = None
    ) -> Optional[str]:
        """Resolve the skill directory path.

        Resolution order:
        1. context.config["available_skills"][skill_name] (pre-computed by agent)
        2. sandbox_client.skill_dir / skill_name (sandbox mode)
        3. context.config["skill_dir"] / skill_name
        4. DATA_DIR/skill / skill_name (local fallback)
        """
        # 1. From pre-computed available_skills
        if context:
            config = context.config if hasattr(context, "config") else {}
            if isinstance(config, dict):
                available_skills = config.get("available_skills", {})
                if isinstance(available_skills, dict) and skill_name in available_skills:
                    return available_skills[skill_name]

        # 2. From sandbox client
        if client is not None:
            skill_dir = getattr(client, "skill_dir", None)
            if skill_dir:
                return os.path.join(skill_dir, skill_name)

        # 3. From context.config["skill_dir"]
        if context:
            config = context.config if hasattr(context, "config") else {}
            if isinstance(config, dict):
                skill_dir = config.get("skill_dir")
                if skill_dir:
                    return os.path.join(skill_dir, skill_name)

        # 4. Local fallback: DATA_DIR/skill
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

    async def _execute_sandbox(
        self, args: Dict[str, Any], context: Optional[ToolContext], client: Any
    ) -> ToolResult:
        """Read skill content from sandbox environment."""
        skill_name = args.get("skill_name", "")
        file_path = args.get("file_path", "SKILL.md")

        if not skill_name:
            return ToolResult.fail(
                error="skill_name is required", tool_name=self.name
            )

        skill_dir = self._resolve_skill_dir(skill_name, context, client)
        if not skill_dir:
            return ToolResult.fail(
                error=f"Cannot resolve skill directory for '{skill_name}'",
                tool_name=self.name,
            )

        # Sanitize file_path to prevent directory traversal
        if ".." in file_path:
            return ToolResult.fail(
                error="file_path cannot contain '..'", tool_name=self.name
            )

        full_path = os.path.join(skill_dir, file_path)

        try:
            # Use sandbox client to read the file
            if hasattr(client, "read_file"):
                content = await client.read_file(full_path)
            elif hasattr(client, "shell_exec"):
                result = await client.shell_exec(f"cat '{full_path}'")
                if hasattr(result, "output"):
                    content = result.output
                elif isinstance(result, dict):
                    content = result.get("output", str(result))
                else:
                    content = str(result)
            else:
                return ToolResult.fail(
                    error="Sandbox client does not support file reading",
                    tool_name=self.name,
                )

            if not content:
                return ToolResult.fail(
                    error=f"Skill file is empty or not found: {full_path}",
                    tool_name=self.name,
                )

            return ToolResult.ok(
                output=content,
                tool_name=self.name,
                metadata={
                    "is_skill_content": True,
                    "skill_name": skill_name,
                    "file_path": full_path,
                    "max_output_chars": 100_000,
                },
            )

        except Exception as e:
            logger.error(f"[ReadSkillTool] Sandbox read failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Read skill content from local filesystem."""
        skill_name = args.get("skill_name", "")
        file_path = args.get("file_path", "SKILL.md")

        if not skill_name:
            return ToolResult.fail(
                error="skill_name is required", tool_name=self.name
            )

        skill_dir = self._resolve_skill_dir(skill_name, context)
        if not skill_dir:
            return ToolResult.fail(
                error=f"Cannot resolve skill directory for '{skill_name}'",
                tool_name=self.name,
            )

        # Sanitize file_path to prevent directory traversal
        if ".." in file_path:
            return ToolResult.fail(
                error="file_path cannot contain '..'", tool_name=self.name
            )

        target = Path(skill_dir) / file_path

        if not target.exists():
            return ToolResult.fail(
                error=f"Skill file not found: {target}",
                tool_name=self.name,
            )

        try:
            content = target.read_text(encoding="utf-8")

            if not content.strip():
                return ToolResult.fail(
                    error=f"Skill file is empty: {target}",
                    tool_name=self.name,
                )

            return ToolResult.ok(
                output=content,
                tool_name=self.name,
                metadata={
                    "is_skill_content": True,
                    "skill_name": skill_name,
                    "file_path": str(target),
                    "max_output_chars": 100_000,
                },
            )

        except Exception as e:
            logger.error(f"[ReadSkillTool] Local read failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
