"""
ReadTool - 文件读取工具
参考 OpenCode 的 read 工具
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class ReadTool(ToolBase):
    """文件读取工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read",
            display_name="Read File",
            description="Read the contents of a file. By default, it returns up to 2000 lines.",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            timeout=30,
            tags=["file", "read", "file-system"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute path to the file to read"
                },
                "offset": {
                    "type": "integer",
                    "description": "The line number to start reading from (1-based)",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                    "default": 2000
                }
            },
            "required": ["path"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
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
                error_code="FILE_NOT_FOUND"
            )
        
        if not file_path.is_file():
            return ToolResult.fail(
                error=f"Path is not a file: {path}",
                tool_name=self.name,
                error_code="NOT_A_FILE"
            )
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = []
                for i, line in enumerate(f, 1):
                    if i >= offset:
                        lines.append(f"{i}: {line.rstrip()}")
                    if len(lines) >= limit:
                        break
                
                content = '\n'.join(lines)
                if len(lines) >= limit:
                    content += f"\n\n... (truncated, showing {limit} lines)"
            
            return ToolResult.ok(
                output=content,
                tool_name=self.name,
                metadata={
                    "path": str(file_path),
                    "lines_read": len(lines),
                    "file_size": file_path.stat().st_size
                }
            )
            
        except Exception as e:
            logger.error(f"[ReadTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)