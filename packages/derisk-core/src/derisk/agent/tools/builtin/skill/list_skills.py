"""
ListSkillsTool - 列出可用 Skill

支持两种执行环境：
- 有沙箱：通过 sandbox client 列出沙箱内的 skill
- 无沙箱：通过本地文件系统列出
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


class ListSkillsTool(SandboxToolBase):
    """列出可用 Skill 及其元数据"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="skill_list",
            display_name="List Skills",
            description=(
                "List all available skills with their names and descriptions. "
                "Each skill entry includes its name, description, and directory path."
            ),
            category=ToolCategory.SKILL,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            timeout=60,
            tags=["skill", "list", "discovery"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def _resolve_skill_base_dir(
        self, context: Optional[ToolContext], client: Any = None
    ) -> Optional[str]:
        """Resolve the base skill directory."""
        if client is not None:
            skill_dir = getattr(client, "skill_dir", None)
            if skill_dir:
                return skill_dir

        if context:
            config = context.config if hasattr(context, "config") else {}
            if isinstance(config, dict):
                skill_dir = config.get("skill_dir")
                if skill_dir:
                    return skill_dir

        try:
            from derisk._private.config import Config

            cfg = Config()
            data_dir = getattr(cfg, "DATA_DIR", None) or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "..", "..", "..", "..", "..", "..",
                "pilot", "data",
            )
            return os.path.join(data_dir, "skill")
        except Exception:
            return None

    @staticmethod
    def _parse_frontmatter(content: str) -> Dict[str, str]:
        """Parse YAML frontmatter from SKILL.md to extract name and description."""
        result = {}
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return result

        for line in match.group(1).splitlines():
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key in ("name", "description") and value and value not in ("|", ">"):
                    result[key] = value
        return result

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        client = self._get_sandbox_client(context)

        # Check pre-computed available_skills first
        if context:
            config = context.config if hasattr(context, "config") else {}
            if isinstance(config, dict):
                available_skills = config.get("available_skills", {})
                if isinstance(available_skills, dict) and available_skills:
                    return self._format_skills_from_map(available_skills)

        if client is not None:
            return await self._execute_sandbox(args, context, client)
        else:
            return await self._execute_local(args, context)

    def _format_skills_from_map(self, skills: Dict[str, str]) -> ToolResult:
        """Format skills from available_skills config map."""
        lines = []
        for name, path in sorted(skills.items()):
            lines.append(f"- **{name}** ({path})")

        if not lines:
            return ToolResult.ok(
                output="No skills available.",
                tool_name=self.name,
            )

        output = f"Available skills ({len(lines)}):\n" + "\n".join(lines)
        return ToolResult.ok(output=output, tool_name=self.name)

    async def _execute_sandbox(
        self, args: Dict[str, Any], context: Optional[ToolContext], client: Any
    ) -> ToolResult:
        """List skills in sandbox environment."""
        skill_dir = self._resolve_skill_base_dir(context, client)
        if not skill_dir:
            return ToolResult.fail(
                error="Cannot resolve skill directory",
                tool_name=self.name,
            )

        try:
            if hasattr(client, "shell_exec"):
                result = await client.shell_exec(
                    f"ls -d '{skill_dir}'/*/ 2>/dev/null | xargs -I{{}} basename {{}}"
                )
                if hasattr(result, "output"):
                    output = result.output or ""
                elif isinstance(result, dict):
                    output = result.get("output", "")
                else:
                    output = str(result)

                skill_names = [n.strip() for n in output.strip().splitlines() if n.strip()]
                return self._format_skill_list(skill_names, skill_dir)
            else:
                return ToolResult.fail(
                    error="Sandbox client does not support shell execution",
                    tool_name=self.name,
                )
        except Exception as e:
            logger.error(f"[ListSkillsTool] Sandbox list failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """List skills on local filesystem."""
        skill_dir = self._resolve_skill_base_dir(context)
        if not skill_dir or not os.path.isdir(skill_dir):
            return ToolResult.fail(
                error=f"Skill directory not found: {skill_dir}",
                tool_name=self.name,
            )

        try:
            skill_names = []
            for entry in sorted(Path(skill_dir).iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    skill_names.append(entry.name)

            lines = []
            for name in skill_names:
                skill_md = Path(skill_dir) / name / "SKILL.md"
                desc = ""
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        fm = self._parse_frontmatter(content)
                        desc = fm.get("description", "")
                    except Exception:
                        pass
                if desc:
                    lines.append(f"- **{name}**: {desc}")
                else:
                    lines.append(f"- **{name}**")

            if not lines:
                return ToolResult.ok(
                    output="No skills found.",
                    tool_name=self.name,
                )

            output = f"Available skills ({len(lines)}):\n" + "\n".join(lines)
            return ToolResult.ok(output=output, tool_name=self.name)

        except Exception as e:
            logger.error(f"[ListSkillsTool] Local list failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    @staticmethod
    def _format_skill_list(skill_names: list, skill_dir: str) -> ToolResult:
        """Format a list of skill names into output."""
        if not skill_names:
            return ToolResult.ok(
                output="No skills found.",
                tool_name="skill_list",
            )

        lines = [f"- **{name}**" for name in sorted(skill_names)]
        output = f"Available skills ({len(lines)}):\n" + "\n".join(lines)
        return ToolResult.ok(output=output, tool_name="skill_list")
