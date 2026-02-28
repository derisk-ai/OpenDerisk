"""
内置工具集实现

提供核心工具:
- BashTool: Shell命令执行
- ReadTool: 文件读取
- WriteTool: 文件写入
- EditTool: 文件编辑
- GlobTool: 文件搜索
"""

from typing import Dict, Any, Optional, List
import asyncio
import os
import re
import json
import logging
from pathlib import Path

from .tool_base import (
    ToolBase, ToolMetadata, ToolResult,
    ToolCategory, ToolRiskLevel
)

logger = logging.getLogger(__name__)


class BashTool(ToolBase):
    """
    Bash命令执行工具
    
    示例:
        tool = BashTool()
        result = await tool.execute({"command": "ls -la"})
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            description="执行Shell命令",
            category=ToolCategory.SHELL,
            risk_level=ToolRiskLevel.HIGH,
            requires_permission=True,
            tags=["shell", "command", "execute"]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的Shell命令"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间(秒)",
                    "default": 120
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录"
                },
                "env": {
                    "type": "object",
                    "description": "环境变量"
                }
            },
            "required": ["command"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        command = args.get("command")
        timeout = args.get("timeout", 120)
        cwd = args.get("cwd")
        env = args.get("env", {})
        
        blocked_commands = ["rm -rf /", "mkfs", "dd if=/dev/zero", "> /dev/sda"]
        for blocked in blocked_commands:
            if blocked in command:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Blocked dangerous command: {blocked}"
                )
        
        try:
            merged_env = os.environ.copy()
            merged_env.update(env)
            
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds"
                )
            
            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")
            
            success = process.returncode == 0
            
            return ToolResult(
                success=success,
                output=output,
                error=error if error else None,
                metadata={
                    "return_code": process.returncode,
                    "command": command,
                    "timeout": timeout
                }
            )
            
        except Exception as e:
            logger.error(f"[BashTool] 执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class ReadTool(ToolBase):
    """
    文件读取工具
    
    示例:
        tool = ReadTool()
        result = await tool.execute({"path": "/path/to/file"})
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read",
            description="读取文件内容",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["file", "read"]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号(从1开始)",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "读取行数限制",
                    "default": 2000
                }
            },
            "required": ["path"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        path = args.get("path")
        start_line = args.get("start_line", 1)
        limit = args.get("limit", 2000)
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件不存在: {path}"
                )
            
            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"路径不是文件: {path}"
                )
            
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = []
                for i, line in enumerate(f, 1):
                    if i >= start_line:
                        lines.append(line.rstrip('\n'))
                    if len(lines) >= limit:
                        break
                
                content = '\n'.join(lines)
                if len(lines) == limit:
                    content += f"\n\n... (truncated, showing {limit} lines)"
            
            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "path": str(file_path),
                    "lines_read": len(lines),
                    "file_size": file_path.stat().st_size
                }
            )
            
        except Exception as e:
            logger.error(f"[ReadTool] 读取失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class WriteTool(ToolBase):
    """
    文件写入工具
    
    示例:
        tool = WriteTool()
        result = await tool.execute({
            "path": "/path/to/file",
            "content": "Hello World"
        })
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="write",
            description="写入文件",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["file", "write", "create"]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                },
                "mode": {
                    "type": "string",
                    "description": "写入模式: write(覆盖) 或 append(追加)",
                    "enum": ["write", "append"],
                    "default": "write"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "是否自动创建目录",
                    "default": True
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        path = args.get("path")
        content = args.get("content", "")
        mode = args.get("mode", "write")
        create_dirs = args.get("create_dirs", True)
        
        try:
            file_path = Path(path)
            
            if create_dirs and not file_path.parent.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            write_mode = 'w' if mode == "write" else 'a'
            
            with open(file_path, write_mode, encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"成功写入文件: {path}",
                metadata={
                    "path": str(file_path),
                    "bytes_written": len(content.encode('utf-8')),
                    "mode": mode
                }
            )
            
        except Exception as e:
            logger.error(f"[WriteTool] 写入失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class EditTool(ToolBase):
    """
    文件编辑工具 - 精确字符串替换
    
    示例:
        tool = EditTool()
        result = await tool.execute({
            "path": "/path/to/file",
            "old_string": "old text",
            "new_string": "new text"
        })
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="edit",
            description="编辑文件(替换指定内容)",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["file", "edit", "replace"]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的内容"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的内容"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "是否替换所有匹配",
                    "default": False
                }
            },
            "required": ["path", "old_string", "new_string"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        path = args.get("path")
        old_string = args.get("old_string")
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        
        if old_string == new_string:
            return ToolResult(
                success=False,
                output="",
                error="old_string 和 new_string 相同，无需替换"
            )
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件不存在: {path}"
                )
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_string not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"未找到要替换的内容: {old_string[:50]}..."
                )
            
            occurrences = content.count(old_string)
            
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                if occurrences > 1:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"找到 {occurrences} 处匹配，请使用 replace_all 或提供更精确的内容"
                    )
                new_content = content.replace(old_string, new_string, 1)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return ToolResult(
                success=True,
                output=f"成功替换 {occurrences if replace_all else 1} 处",
                metadata={
                    "path": str(file_path),
                    "occurrences": occurrences,
                    "replaced": occurrences if replace_all else 1
                }
            )
            
        except Exception as e:
            logger.error(f"[EditTool] 编辑失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class GlobTool(ToolBase):
    """
    文件搜索工具
    
    示例:
        tool = GlobTool()
        result = await tool.execute({
            "pattern": "**/*.py",
            "path": "/project"
        })
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="glob",
            description="搜索文件",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["file", "search", "find"]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob模式(如 **/*.py)"
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录(默认当前目录)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数",
                    "default": 100
                }
            },
            "required": ["pattern"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        pattern = args.get("pattern")
        path = args.get("path", ".")
        max_results = args.get("max_results", 100)
        
        try:
            search_path = Path(path)
            
            if not search_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"目录不存在: {path}"
                )
            
            matches = list(search_path.glob(pattern))[:max_results]
            
            output_lines = [
                f"找到 {len(matches)} 个文件:\n",
                *[f"  - {m.relative_to(search_path)}" for m in matches]
            ]
            
            if len(matches) >= max_results:
                output_lines.append(f"\n(显示前 {max_results} 个结果)")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "total": len(matches),
                    "pattern": pattern,
                    "path": str(search_path)
                }
            )
            
        except Exception as e:
            logger.error(f"[GlobTool] 搜索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class GrepTool(ToolBase):
    """
    内容搜索工具
    
    示例:
        tool = GrepTool()
        result = await tool.execute({
            "pattern": "function\\s+\\w+",
            "path": "/project/src",
            "include": "*.py"
        })
    """
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="grep",
            description="在文件中搜索内容",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["search", "find", "regex"]
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "搜索模式(支持正则)"
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录或文件"
                },
                "include": {
                    "type": "string",
                    "description": "文件过滤模式(如 *.py)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数",
                    "default": 50
                }
            },
            "required": ["pattern"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        pattern = args.get("pattern")
        path = args.get("path", ".")
        include = args.get("include", "*")
        max_results = args.get("max_results", 50)
        
        try:
            search_path = Path(path)
            
            if not search_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"路径不存在: {path}"
                )
            
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
            
            output_lines = [
                f"找到 {len(results)} 处匹配:\n",
                *[f"{r['file']}:{r['line']}: {r['content']}" for r in results]
            ]
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "total": len(results),
                    "pattern": pattern
                }
            )
            
        except Exception as e:
            logger.error(f"[GrepTool] 搜索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


def register_builtin_tools(registry):
    """注册内置工具到注册表"""
    registry.register(BashTool())
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    
    logger.info("[BuiltinTools] 已注册内置工具")