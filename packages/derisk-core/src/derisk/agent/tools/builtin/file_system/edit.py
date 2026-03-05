"""
EditTool - 文件编辑工具
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class EditTool(ToolBase):
    """文件编辑工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="edit",
            display_name="Edit File",
            description="Edit a file by replacing specific text. Performs exact string matching.",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            timeout=30,
            tags=["file", "edit", "replace"],
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The file path to edit"},
                "old_string": {"type": "string", "description": "The text to replace"},
                "new_string": {"type": "string", "description": "The replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Replace all occurrences"
                }
            },
            "required": ["path", "old_string", "new_string"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        path = args["path"]
        old_string = args["old_string"]
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        
        if old_string == new_string:
            return ToolResult.fail(
                error="old_string and new_string are identical",
                tool_name=self.name
            )
        
        if context and context.working_directory:
            file_path = Path(context.working_directory) / path
        else:
            file_path = Path(path)
        
        if not file_path.exists():
            return ToolResult.fail(
                error=f"File does not exist: {path}",
                tool_name=self.name
            )
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_string not in content:
                return ToolResult.fail(
                    error=f"Text not found: {old_string[:50]}...",
                    tool_name=self.name
                )
            
            occurrences = content.count(old_string)
            
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                if occurrences > 1:
                    return ToolResult.fail(
                        error=f"Found {occurrences} matches. Use replace_all or provide more specific text.",
                        tool_name=self.name
                    )
                new_content = content.replace(old_string, new_string, 1)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return ToolResult.ok(
                output=f"Successfully replaced {occurrences if replace_all else 1} occurrence(s)",
                tool_name=self.name,
                metadata={
                    "path": str(file_path),
                    "occurrences": occurrences,
                    "replaced": occurrences if replace_all else 1
                }
            )
            
        except Exception as e:
            logger.error(f"[EditTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)


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
        import re
        
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