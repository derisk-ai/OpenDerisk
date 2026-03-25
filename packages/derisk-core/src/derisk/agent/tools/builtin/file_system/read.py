"""
ReadTool - 统一文件读取工具

支持两种执行环境：
- 有沙箱：通过 sandbox client 读取沙箱文件（支持目录列表、图片base64、交付物标记）
- 无沙箱：通过本地文件系统读取
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ..sandbox.base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class ReadTool(SandboxToolBase):
    """统一文件读取工具 - 自动检测执行环境"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read",
            display_name="Read File",
            description=(
                "Read the contents of a file or list a directory. "
                "By default, it returns up to 2000 lines.\n\n"
                "When running in a sandbox environment, additional capabilities are available:\n"
                "- Directory exploration (lists file tree up to 2 levels)\n"
                "- Image preview (returns base64)\n"
                "- Deliverable marking (mark files for delivery with download links)\n"
                "- Line range slicing via view_range parameter"
            ),
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            timeout=60,
            tags=["file", "read", "file-system", "view"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute path to the file (or directory in sandbox mode) to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "The line number to start reading from (1-based, local mode)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (local mode)",
                    "default": 2000,
                },
                "view_range": {
                    "anyOf": [
                        {
                            "maxItems": 2,
                            "minItems": 2,
                            "prefixItems": [{"type": "integer"}, {"type": "integer"}],
                            "type": "array",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "Line range [start, end] (1-based, sandbox mode). Use -1 for end of file.",
                },
                "mark_as_deliverable": {
                    "type": "boolean",
                    "default": False,
                    "description": "Mark this file as a deliverable with download link (sandbox mode only)",
                },
                "delivery_description": {
                    "type": "string",
                    "description": "Description for the deliverable (sandbox mode, when mark_as_deliverable=true)",
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
        """Delegate to sandbox ViewTool logic"""
        from ..sandbox.view import ViewTool

        view_tool = ViewTool()
        # Map parameters: offset/limit → view_range if no explicit view_range
        sandbox_args = {
            "path": args["path"],
            "mark_as_deliverable": args.get("mark_as_deliverable", False),
            "delivery_description": args.get("delivery_description", ""),
        }

        # Use explicit view_range if provided, otherwise convert offset/limit
        view_range = args.get("view_range")
        if view_range is not None:
            sandbox_args["view_range"] = view_range
        elif args.get("offset", 1) != 1 or args.get("limit", 2000) != 2000:
            offset = args.get("offset", 1)
            limit = args.get("limit", 2000)
            sandbox_args["view_range"] = [offset, offset + limit - 1]

        return await view_tool.execute(sandbox_args, context)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Execute locally using pathlib"""
        path = args["path"]
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)

        if context and context.working_directory:
            file_path = Path(context.working_directory) / path
        else:
            file_path = Path(path)

        if not file_path.exists():
            return ToolResult.fail(
                error=f"File does not exist: {path}",
                tool_name=self.name,
                error_code="FILE_NOT_FOUND",
            )

        if not file_path.is_file():
            return ToolResult.fail(
                error=f"Path is not a file: {path}",
                tool_name=self.name,
                error_code="NOT_A_FILE",
            )

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f, 1):
                    if i >= offset:
                        lines.append(f"{i}: {line.rstrip()}")
                    if len(lines) >= limit:
                        break

                content = "\n".join(lines)
                if len(lines) >= limit:
                    content += f"\n\n... (truncated, showing {limit} lines)"

            return ToolResult.ok(
                output=content,
                tool_name=self.name,
                metadata={
                    "path": str(file_path),
                    "lines_read": len(lines),
                    "file_size": file_path.stat().st_size,
                },
            )

        except Exception as e:
            logger.error(f"[ReadTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
