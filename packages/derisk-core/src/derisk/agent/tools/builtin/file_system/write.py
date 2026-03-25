"""
WriteTool - 统一文件写入工具

支持两种执行环境：
- 有沙箱：通过 sandbox client 创建文件（支持OSS上传、交付物标记、d-attach渲染）
- 无沙箱：通过本地文件系统写入
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


class WriteTool(SandboxToolBase):
    """统一文件写入工具 - 自动检测执行环境"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="write",
            display_name="Write File",
            description=(
                "Write content to a file. Creates the file if it doesn't exist.\n\n"
                "When running in a sandbox environment, additional capabilities are available:\n"
                "- Automatic OSS upload for file delivery\n"
                "- Deliverable marking (is_deliverable parameter)\n"
                "- d-attach rendering for download links"
            ),
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            timeout=60,
            tags=["file", "write", "create"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write (alias: file_text)",
                },
                "file_text": {
                    "type": "string",
                    "description": "Alias for content (sandbox compatibility)",
                },
                "mode": {
                    "type": "string",
                    "enum": ["write", "append"],
                    "default": "write",
                    "description": "Write mode: write (overwrite) or append",
                },
                "create_dirs": {
                    "type": "boolean",
                    "default": True,
                    "description": "Create parent directories if they don't exist",
                },
                "description": {
                    "type": "string",
                    "description": "Description of the file being created (sandbox mode)",
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
        """Delegate to sandbox CreateFileTool logic"""
        from ..sandbox.create_file import CreateFileTool

        create_tool = CreateFileTool()
        # Map parameters
        content = args.get("content") or args.get("file_text", "")
        sandbox_args = {
            "path": args["path"],
            "file_text": content,
            "description": args.get("description", ""),
            "is_deliverable": args.get("is_deliverable", True),
        }

        return await create_tool.execute(sandbox_args, context)

    async def _execute_local(
        self, args: Dict[str, Any], context: Optional[ToolContext]
    ) -> ToolResult:
        """Execute locally using pathlib"""
        path = args["path"]
        content = args.get("content") or args.get("file_text", "")
        mode = args.get("mode", "write")
        create_dirs = args.get("create_dirs", True)

        if context and context.working_directory:
            file_path = Path(context.working_directory) / path
        else:
            file_path = Path(path)

        try:
            if create_dirs and not file_path.parent.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)

            write_mode = "w" if mode == "write" else "a"

            with open(file_path, write_mode, encoding="utf-8") as f:
                f.write(content)

            return ToolResult.ok(
                output=f"Successfully wrote to file: {path}",
                tool_name=self.name,
                metadata={
                    "path": str(file_path),
                    "bytes_written": len(content.encode("utf-8")),
                    "mode": mode,
                },
            )

        except Exception as e:
            logger.error(f"[WriteTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
