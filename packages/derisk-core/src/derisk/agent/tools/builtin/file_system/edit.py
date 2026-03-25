"""
EditTool - 统一文件编辑工具

支持两种执行环境：
- 有沙箱：通过 sandbox client 编辑沙箱文件（支持OSS上传、交付物标记）
- 无沙箱：通过本地文件系统编辑
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ..sandbox.base import SandboxToolBase
from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class EditTool(SandboxToolBase):
    """统一文件编辑工具 - 自动检测执行环境"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="edit",
            display_name="Edit File",
            description=(
                "Edit a file by replacing specific text. Performs exact string matching.\n\n"
                "When running in a sandbox environment, additional capabilities are available:\n"
                "- Append mode (add content to end of file)\n"
                "- Automatic OSS upload for file delivery\n"
                "- Deliverable marking"
            ),
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            timeout=60,
            tags=["file", "edit", "replace"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The text to replace (alias: old_str)",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text (alias: new_str)",
                },
                "old_str": {
                    "type": "string",
                    "description": "Alias for old_string (sandbox compatibility)",
                },
                "new_str": {
                    "type": "string",
                    "description": "Alias for new_string (sandbox compatibility)",
                },
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Replace all occurrences (local mode)",
                },
                "append": {
                    "type": "boolean",
                    "default": False,
                    "description": "Append mode: add new_string to end of file instead of replacing",
                },
                "description": {
                    "type": "string",
                    "description": "Description of the edit (sandbox mode)",
                },
                "is_deliverable": {
                    "type": "boolean",
                    "default": True,
                    "description": "Mark file as deliverable (sandbox mode only)",
                },
            },
            "required": ["path"],
        }

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
        """Delegate to sandbox EditFileTool logic"""
        from ..sandbox.edit_file import EditFileTool

        edit_tool = EditFileTool()
        # Map parameters
        old_str = args.get("old_string") or args.get("old_str")
        new_str = args.get("new_string") or args.get("new_str", "")
        append = args.get("append", False)

        sandbox_args = {
            "path": args["path"],
            "description": args.get("description", "edit file"),
            "new_str": new_str,
            "append": append or (old_str is None),
            "is_deliverable": args.get("is_deliverable", True),
        }
        if old_str is not None:
            sandbox_args["old_str"] = old_str

        return await edit_tool.execute(sandbox_args, context)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Execute locally using pathlib"""
        path = args["path"]
        old_string = args.get("old_string") or args.get("old_str")
        new_string = args.get("new_string") or args.get("new_str", "")
        replace_all = args.get("replace_all", False)
        append = args.get("append", False)

        if context and context.working_directory:
            file_path = Path(context.working_directory) / path
        else:
            file_path = Path(path)

        # Append mode
        if append:
            try:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(new_string)
                return ToolResult.ok(
                    output=f"Successfully appended to file: {path}",
                    tool_name=self.name,
                )
            except Exception as e:
                logger.error(f"[EditTool] Append failed: {e}")
                return ToolResult.fail(error=str(e), tool_name=self.name)

        # Replace mode
        if not old_string:
            return ToolResult.fail(
                error="old_string is required for replace mode (or use append=true)",
                tool_name=self.name,
            )

        if old_string == new_string:
            return ToolResult.fail(
                error="old_string and new_string are identical",
                tool_name=self.name,
            )

        if not file_path.exists():
            return ToolResult.fail(
                error=f"File does not exist: {path}",
                tool_name=self.name,
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_string not in content:
                return ToolResult.fail(
                    error=f"Text not found: {old_string[:50]}...",
                    tool_name=self.name,
                )

            occurrences = content.count(old_string)

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                if occurrences > 1:
                    return ToolResult.fail(
                        error=f"Found {occurrences} matches. Use replace_all or provide more specific text.",
                        tool_name=self.name,
                    )
                new_content = content.replace(old_string, new_string, 1)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult.ok(
                output=f"Successfully replaced {occurrences if replace_all else 1} occurrence(s)",
                tool_name=self.name,
                metadata={
                    "path": str(file_path),
                    "occurrences": occurrences,
                    "replaced": occurrences if replace_all else 1,
                },
            )

        except Exception as e:
            logger.error(f"[EditTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
