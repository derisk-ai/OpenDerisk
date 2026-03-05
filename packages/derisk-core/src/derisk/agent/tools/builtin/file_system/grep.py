"""
GrepTool - 内容搜索工具
"""

from typing import Dict, Any, Optional
from pathlib import Path
import re
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class GrepTool(ToolBase):
    """内容搜索工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="grep",
            display_name="Search Content",
            description="Search for content in files using regex",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            timeout=60,
            tags=["search", "find", "regex"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex supported)"},
                "path": {"type": "string", "description": "Directory or file to search"},
                "include": {"type": "string", "description": "File filter pattern (e.g., *.py)"},
                "max_results": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum results"
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
        include = args.get("include", "*")
        max_results = args.get("max_results", 50)
        
        if context and context.working_directory:
            search_path = Path(context.working_directory) / path
        else:
            search_path = Path(path)
        
        if not search_path.exists():
            return ToolResult.fail(
                error=f"Path does not exist: {path}",
                tool_name=self.name
            )
        
        try:
            regex = re.compile(pattern)
            results = []
            
            files = search_path.glob(f"**/{include}")
            
            for file_path in files:
                if not file_path.is_file():
                    continue
                
                if len(results) >= max_results:
                    break
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append({
                                    "file": str(file_path),
                                    "line": line_num,
                                    "content": line.strip()[:200]
                                })
                                
                                if len(results) >= max_results:
                                    break
                except Exception:
                    continue
            
            output_lines = [f"Found {len(results)} matches:\n"]
            output_lines.extend([f"{r['file']}:{r['line']}: {r['content']}" for r in results])
            
            return ToolResult.ok(
                output="\n".join(output_lines),
                tool_name=self.name,
                metadata={
                    "total": len(results),
                    "pattern": pattern
                }
            )
            
        except Exception as e:
            logger.error(f"[GrepTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)