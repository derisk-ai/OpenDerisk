"""
ReadSkillTool - 读取 Skill 内容

支持两种执行环境：
- 有沙箱：通过 sandbox client 读取沙箱内的 skill 文件
- 无沙箱：通过本地文件系统读取

Skill 内容不受常规截断限制，返回完整的 SKILL.md 指令。
支持 offset/limit 分页读取，与 read 工具参数一致。
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging

from ..sandbox.base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)

# Skill 内容最大字符数（100K）
_MAX_SKILL_CHARS = 100_000


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
                "as it provides proper skill path resolution and content protection.\n\n"
                "Supports pagination via offset/limit (line-based, 1-indexed) for large files."
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
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (1-based). Default: 1 (beginning of file)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read. Default: 0 means read all (no limit)",
                    "default": 0,
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

    # ======================== Pagination ========================

    @staticmethod
    def _paginate(content: str, offset: int, limit: int) -> Tuple[str, Dict[str, Any]]:
        """Apply line-based pagination to content.

        Args:
            content: Full text content
            offset: 1-based starting line number
            limit: Max lines to return (0 = no limit)

        Returns:
            (paginated_content, pagination_metadata)
        """
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # Normalize offset to 0-based index
        start_idx = max(0, offset - 1)

        if limit > 0:
            end_idx = min(total_lines, start_idx + limit)
        else:
            end_idx = total_lines

        selected = lines[start_idx:end_idx]
        result = "".join(selected)

        meta: Dict[str, Any] = {
            "total_lines": total_lines,
            "offset": offset,
            "lines_read": len(selected),
        }

        if limit > 0:
            meta["limit"] = limit

        # Append pagination hint
        has_more = end_idx < total_lines
        if has_more:
            meta["has_more"] = True
            result += (
                f"\n... [{total_lines - end_idx} more lines, "
                f"use offset={end_idx + 1} to continue]"
            )

        return result, meta

    # ======================== Sandbox Mode ========================

    async def _execute_sandbox(
        self, args: Dict[str, Any], context: Optional[ToolContext], client: Any
    ) -> ToolResult:
        """Read skill content from sandbox environment."""
        skill_name = args.get("skill_name", "")
        file_path = args.get("file_path", "SKILL.md")
        offset = args.get("offset", 1)
        limit = args.get("limit", 0)

        if not skill_name:
            return ToolResult.fail(
                error="skill_name is required", tool_name=self.name
            )

        if ".." in file_path:
            return ToolResult.fail(
                error="file_path cannot contain '..'", tool_name=self.name
            )

        skill_dir = self._resolve_skill_dir(skill_name, context, client)
        if not skill_dir:
            return ToolResult.fail(
                error=f"Cannot resolve skill directory for '{skill_name}'",
                tool_name=self.name,
            )

        full_path = os.path.join(skill_dir, file_path)

        try:
            path_kind = await self._detect_path_kind(client, full_path)
            if path_kind == "none":
                return ToolResult.fail(
                    error=f"Skill file not found: {full_path}",
                    tool_name=self.name,
                )
            if path_kind == "dir":
                output = await self._render_directory_listing(client, full_path)
                return ToolResult.ok(
                    output=output,
                    tool_name=self.name,
                    metadata={
                        "is_skill_content": True,
                        "skill_name": skill_name,
                        "file_path": full_path,
                    },
                )

            content = await self._read_text_content(client, full_path)
            if content is None:
                return ToolResult.fail(
                    error=f"Skill file is empty or unreadable: {full_path}",
                    tool_name=self.name,
                )

            # Apply pagination
            has_pagination = offset > 1 or limit > 0
            if has_pagination:
                content, page_meta = self._paginate(content, offset, limit)
            else:
                # No pagination: cap at _MAX_SKILL_CHARS
                if len(content) > _MAX_SKILL_CHARS:
                    content = content[:_MAX_SKILL_CHARS] + f"\n... [truncated to {_MAX_SKILL_CHARS} chars]"
                page_meta = {"total_lines": content.count("\n") + 1}

            return ToolResult.ok(
                output=content,
                tool_name=self.name,
                metadata={
                    "is_skill_content": True,
                    "skill_name": skill_name,
                    "file_path": full_path,
                    "max_output_chars": _MAX_SKILL_CHARS,
                    **page_meta,
                },
            )

        except Exception as e:
            logger.error(f"[ReadSkillTool] Sandbox read failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    async def _read_text_content(self, client: Any, abs_path: str) -> Optional[str]:
        """Read text file content from sandbox - mirrors view.py:_read_text_content."""
        try:
            file_info = await client.file.read(abs_path)
            content = getattr(file_info, "content", None)
            if content is None:
                return None
            return content
        except Exception as exc:
            logger.warning(f"[ReadSkillTool] client.file.read failed: {exc}, falling back to shell")
            try:
                import shlex
                result = await client.shell.exec_command(
                    command=f"cat {shlex.quote(abs_path)}",
                    work_dir=getattr(client, "work_dir", "/"),
                    timeout=60.0,
                )
                if getattr(result, "status", None) != "completed":
                    return None
                from derisk.sandbox.sandbox_utils import collect_shell_output
                output = collect_shell_output(result)
                return output if output else None
            except Exception as shell_exc:
                logger.error(f"[ReadSkillTool] Shell cat fallback also failed: {shell_exc}")
                return None

    async def _detect_path_kind(self, client: Any, abs_path: str) -> str:
        """Detect if path is file/dir/none in sandbox."""
        try:
            from derisk.sandbox.sandbox_utils import detect_path_kind
            return await detect_path_kind(client, abs_path)
        except Exception:
            try:
                exists = await client.file.exists(abs_path)
                return "file" if exists else "none"
            except Exception:
                return "none"

    async def _render_directory_listing(self, client: Any, abs_path: str) -> str:
        """Render directory listing - delegates to view.py helper."""
        try:
            from ..sandbox.view import _render_directory_listing
            return await _render_directory_listing(client, abs_path)
        except Exception as e:
            try:
                import shlex
                result = await client.shell.exec_command(
                    command=f"ls -la {shlex.quote(abs_path)}",
                    work_dir=getattr(client, "work_dir", "/"),
                    timeout=60.0,
                )
                from derisk.sandbox.sandbox_utils import collect_shell_output
                output = collect_shell_output(result)
                return output or f"Directory: {abs_path} (listing failed)"
            except Exception:
                return f"Directory: {abs_path} (listing failed: {e})"

    # ======================== Local Mode ========================

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Read skill content from local filesystem."""
        skill_name = args.get("skill_name", "")
        file_path = args.get("file_path", "SKILL.md")
        offset = args.get("offset", 1)
        limit = args.get("limit", 0)

        if not skill_name:
            return ToolResult.fail(
                error="skill_name is required", tool_name=self.name
            )

        if ".." in file_path:
            return ToolResult.fail(
                error="file_path cannot contain '..'", tool_name=self.name
            )

        skill_dir = self._resolve_skill_dir(skill_name, context)
        if not skill_dir:
            return ToolResult.fail(
                error=f"Cannot resolve skill directory for '{skill_name}'",
                tool_name=self.name,
            )

        target = Path(skill_dir) / file_path

        if not target.exists():
            return ToolResult.fail(
                error=f"Skill file not found: {target}",
                tool_name=self.name,
            )

        if target.is_dir():
            return self._list_local_directory(target, skill_name)

        try:
            content = target.read_text(encoding="utf-8")

            if not content.strip():
                return ToolResult.fail(
                    error=f"Skill file is empty: {target}",
                    tool_name=self.name,
                )

            # Apply pagination
            has_pagination = offset > 1 or limit > 0
            if has_pagination:
                content, page_meta = self._paginate(content, offset, limit)
            else:
                if len(content) > _MAX_SKILL_CHARS:
                    content = content[:_MAX_SKILL_CHARS] + f"\n... [truncated to {_MAX_SKILL_CHARS} chars]"
                page_meta = {"total_lines": content.count("\n") + 1}

            return ToolResult.ok(
                output=content,
                tool_name=self.name,
                metadata={
                    "is_skill_content": True,
                    "skill_name": skill_name,
                    "file_path": str(target),
                    "max_output_chars": _MAX_SKILL_CHARS,
                    **page_meta,
                },
            )

        except Exception as e:
            logger.error(f"[ReadSkillTool] Local read failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    @staticmethod
    def _list_local_directory(target: Path, skill_name: str) -> ToolResult:
        """List local directory contents."""
        lines = [f"Skill directory: {target}\n"]
        try:
            for entry in sorted(target.iterdir()):
                prefix = "d " if entry.is_dir() else "- "
                size = ""
                if entry.is_file():
                    try:
                        size = f" ({entry.stat().st_size} bytes)"
                    except OSError:
                        pass
                lines.append(f"  {prefix}{entry.name}{size}")
        except OSError as e:
            lines.append(f"  (error listing: {e})")

        return ToolResult.ok(
            output="\n".join(lines),
            tool_name="skill_read",
            metadata={
                "is_skill_content": True,
                "skill_name": skill_name,
                "file_path": str(target),
            },
        )
