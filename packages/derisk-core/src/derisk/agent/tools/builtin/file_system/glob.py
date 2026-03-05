"""
GlobTool - 文件搜索工具
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class GlobTool(ToolBase):
    """文件搜索工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="glob",
            display_name="Find Files",
            description="Search for files matching a glob pattern",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            timeout=30,
            tags=["file", "search", "find"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., **/*.py)"},
                "path": {"type": "string", "description": "Directory to search in"},
                "max_results": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum results to return"
                }
            },
            "required": ["pattern"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        pattern = args["pattern"]
        path = args.get("path", ".")
        max_results = args.get("max_results", 100)
        
        if context and context.working_directory:
            search_path = Path(context.working_directory) / path
        else:
            search_path = Path(path)
        
        if not search_path.exists():
            return ToolResult.fail(
                error=f"Directory does not exist: {path}",
                tool_name=self.name
            )
        
        try:
            matches = list(search_path.glob(pattern))[:max_results]
            
            output_lines = [f"Found {len(matches)} files:\n"]
            output_lines.extend([f"  - {m.relative_to(search_path)}" for m in matches])
            
            if len(matches) >= max_results:
                output_lines.append(f"\n(Showing first {max_results} results)")
            
            return ToolResult.ok(
                output="\n".join(output_lines),
                tool_name=self.name,
                metadata={
                    "total": len(matches),
                    "pattern": pattern,
                    "path": str(search_path)
                }
            )
            
        except Exception as e:
            logger.error(f"[GlobTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)