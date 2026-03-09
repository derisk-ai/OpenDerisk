"""
ListFilesTool - 列出文件工具
已迁移到统一工具框架
"""

import os
from typing import Any, Dict, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class ListFilesTool(ToolBase):
    """列出目录文件工具 - 已迁移"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_files",
            display_name="List Files",
            description=(
                "List files and directories in a specified path. "
                "Use this tool to explore the file system and see what files are available."
            ),
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.CORE,
            requires_permission=False,
            tags=["file", "list", "directory", "explore"],
            timeout=30,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list",
                    "default": "."
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively",
                    "default": False
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Show hidden files (starting with .)",
                    "default": False
                }
            },
            "required": []
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        path = args.get("path", ".")
        recursive = args.get("recursive", False)
        show_hidden = args.get("show_hidden", False)
        
        if not os.path.exists(path):
            return ToolResult(
                success=False,
                output="",
                error=f"路径不存在: {path}",
                tool_name=self.name
            )
        
        if not os.path.isdir(path):
            return ToolResult(
                success=False,
                output="",
                error=f"不是目录: {path}",
                tool_name=self.name
            )
        
        results = []
        
        try:
            if recursive:
                for root, dirs, files in os.walk(path):
                    if not show_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        files = [f for f in files if not f.startswith(".")]
                    
                    rel_root = os.path.relpath(root, path)
                    if rel_root == ".":
                        rel_root = ""
                    
                    for d in dirs:
                        results.append(os.path.join(rel_root, d) + "/")
                    for f in files:
                        results.append(os.path.join(rel_root, f))
            else:
                for item in os.listdir(path):
                    if not show_hidden and item.startswith("."):
                        continue
                    
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        results.append(item + "/")
                    else:
                        results.append(item)
            
            return ToolResult(
                success=True,
                output="\n".join(sorted(results)) or "[目录为空]",
                tool_name=self.name,
                metadata={"count": len(results), "path": path}
            )
            
        except Exception as e:
            logger.error(f"[ListFilesTool] 列出失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                tool_name=self.name
            )
