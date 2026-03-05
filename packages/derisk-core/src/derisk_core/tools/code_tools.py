import os
import re
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from difflib import unified_diff
from .base import ToolBase, ToolMetadata, ToolResult, ToolCategory, ToolRisk

class ReadTool(ToolBase):
    """读取文件工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read",
            description="读取文件内容，支持行号范围和偏移",
            category=ToolCategory.FILE,
            risk=ToolRisk.LOW,
            requires_permission=False,
            examples=[
                "read('src/main.py')",
                "read('config.yaml', offset=100, limit=50)"
            ]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件绝对路径"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号(1-indexed)",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "读取行数上限",
                    "default": 2000
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        file_path = args["file_path"]
        offset = args.get("offset", 1)
        limit = args.get("limit", 2000)
        
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, error=f"文件不存在: {file_path}")
            
            if not path.is_file():
                return ToolResult(success=False, error=f"不是文件: {file_path}")
            
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            start = max(0, offset - 1)
            end = min(len(lines), start + limit)
            selected_lines = lines[start:end]
            
            output_lines = []
            for i, line in enumerate(selected_lines, start=offset):
                output_lines.append(f"{i}: {line}")
            
            return ToolResult(
                success=True,
                output="".join(output_lines),
                metadata={
                    "total_lines": len(lines),
                    "lines_read": len(selected_lines),
                    "file_size": path.stat().st_size
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

class WriteTool(ToolBase):
    """写入文件工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="write",
            description="创建或覆盖写入文件",
            category=ToolCategory.FILE,
            risk=ToolRisk.MEDIUM,
            requires_permission=True,
            examples=[
                "write('new_file.py', content='print(\"hello\")')"
            ]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件绝对路径"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容"
                },
                "mode": {
                    "type": "string",
                    "enum": ["write", "append"],
                    "default": "write",
                    "description": "写入模式"
                }
            },
            "required": ["file_path", "content"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        file_path = args["file_path"]
        content = args["content"]
        mode = args.get("mode", "write")
        
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            write_mode = "a" if mode == "append" else "w"
            with open(path, write_mode, encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"成功写入: {file_path}",
                metadata={"bytes_written": len(content)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

class EditTool(ToolBase):
    """编辑文件工具 - 精确字符串替换"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="edit",
            description="编辑文件，进行精确字符串替换",
            category=ToolCategory.CODE,
            risk=ToolRisk.MEDIUM,
            requires_permission=True,
            examples=[
                "edit('main.py', old='print(x)', new='print(y)')"
            ]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件绝对路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的原字符串（必须精确匹配）"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新字符串"
                },
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否替换所有匹配项"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        file_path = args["file_path"]
        old_string = args["old_string"]
        new_string = args["new_string"]
        replace_all = args.get("replace_all", False)
        
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, error=f"文件不存在: {file_path}")
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            count = content.count(old_string)
            if count == 0:
                return ToolResult(success=False, error="未找到要替换的内容")
            
            if count > 1 and not replace_all:
                return ToolResult(
                    success=False, 
                    error=f"找到 {count} 处匹配，请提供更多上下文或设置 replace_all=true"
                )
            
            new_content = content.replace(old_string, new_string, -1 if replace_all else 1)
            diff = self._generate_diff(content, new_content, str(path))
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return ToolResult(
                success=True,
                output=f"成功替换 {count} 处\n{diff}",
                metadata={"replacements": count}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def _generate_diff(self, old: str, new: str, filename: str) -> str:
        """生成统一差异格式"""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff_lines = list(unified_diff(old_lines, new_lines, fromfile=filename, tofile=filename))
        return "".join(diff_lines)

class GlobTool(ToolBase):
    """文件搜索工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="glob",
            description="使用通配符模式搜索文件",
            category=ToolCategory.SEARCH,
            risk=ToolRisk.LOW,
            requires_permission=False
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "通配符模式，如 **/*.py"
                },
                "path": {
                    "type": "string",
                    "description": "搜索起始目录"
                }
            },
            "required": ["pattern"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        import glob as glob_module
        from pathlib import Path
        
        pattern = args["pattern"]
        path = args.get("path", ".")
        
        try:
            search_path = Path(path)
            full_pattern = str(search_path / pattern)
            
            matches = sorted(glob_module.glob(full_pattern, recursive=True), 
                           key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0,
                           reverse=True)
            
            return ToolResult(
                success=True,
                output="\n".join(matches) if matches else "未找到匹配文件",
                metadata={"count": len(matches)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

class GrepTool(ToolBase):
    """内容搜索工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="grep",
            description="在文件内容中搜索正则表达式",
            category=ToolCategory.SEARCH,
            risk=ToolRisk.LOW,
            requires_permission=False
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "正则表达式模式"
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录或文件"
                },
                "include": {
                    "type": "string",
                    "description": "文件模式过滤，如 *.py"
                }
            },
            "required": ["pattern"]
        }
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        import re
        from pathlib import Path
        
        pattern = args["pattern"]
        path = args.get("path", ".")
        include = args.get("include", "*")
        
        try:
            search_path = Path(path)
            regex = re.compile(pattern)
            results = []
            
            files_to_search = []
            if search_path.is_file():
                files_to_search = [search_path]
            else:
                files_to_search = search_path.rglob(include)
            
            for file_path in files_to_search:
                if not file_path.is_file():
                    continue
                
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_num}: {line.rstrip()}")
                except Exception:
                    continue
            
            return ToolResult(
                success=True,
                output="\n".join(results) if results else "未找到匹配内容",
                metadata={"matches": len(results)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))