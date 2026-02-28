"""
WriteTool - 文件写入工具
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class WriteTool(ToolBase):
    """文件写入工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="write",
            display_name="Write File",
            description="Write content to a file. Creates the file if it doesn't exist.",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            timeout=30,
            tags=["file", "write", "create"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The file path to write to"},
                "content": {"type": "string", "description": "The content to write"},
                "mode": {
                    "type": "string",
                    "enum": ["write", "append"],
                    "default": "write",
                    "description": "Write mode: write (overwrite) or append"
                },
                "create_dirs": {
                    "type": "boolean",
                    "default": True,
                    "description": "Create parent directories if they don't exist"
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        path = args["path"]
        content = args.get("content", "")
        mode = args.get("mode", "write")
        create_dirs = args.get("create_dirs", True)
        
        if context and context.working_directory:
            file_path = Path(context.working_directory) / path
        else:
            file_path = Path(path)
        
        try:
            if create_dirs and not file_path.parent.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            write_mode = 'w' if mode == "write" else 'a'
            
            with open(file_path, write_mode, encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult.ok(
                output=f"Successfully wrote to file: {path}",
                tool_name=self.name,
                metadata={
                    "path": str(file_path),
                    "bytes_written": len(content.encode('utf-8')),
                    "mode": mode
                }
            )
            
        except Exception as e:
            logger.error(f"[WriteTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)