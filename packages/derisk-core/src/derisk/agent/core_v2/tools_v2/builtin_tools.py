"""
内置工具集合

提供Agent所需的核心工具：
- bash: 执行shell命令
- read: 读取文件
- write: 写入文件
- search: 搜索代码
- think: 思考
"""

from typing import Any, Dict, Optional
import asyncio
import subprocess
import os
import logging
import json

from .tool_base import ToolBase, ToolMetadata, ToolResult, ToolRegistry

logger = logging.getLogger(__name__)


class BashTool(ToolBase):
    """执行Shell命令工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            description="执行Shell命令。用于运行系统命令、脚本等。需要谨慎使用。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的shell命令"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒）",
                        "default": 60
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录"
                    }
                },
                "required": ["command"]
            },
            requires_permission=True,
            dangerous=True,
            category="system"
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        command = args.get("command", "")
        timeout = args.get("timeout", 60)
        cwd = args.get("cwd")
        
        if not command:
            return ToolResult(
                success=False,
                output="",
                error="命令不能为空"
            )
        
        forbidden = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", "chmod 777 /"]
        for pattern in forbidden:
            if pattern in command:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"禁止执行危险命令: {pattern}"
                )
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
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
                    error=f"命令执行超时（{timeout}秒）"
                )
            
            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")
            
            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    output=output,
                    error=f"命令返回非零: {process.returncode}\n{error_output}"
                )
            
            return ToolResult(
                success=True,
                output=output or "[命令执行成功，无输出]",
                metadata={"return_code": process.returncode}
            )
            
        except Exception as e:
            logger.error(f"[BashTool] 执行失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class ReadTool(ToolBase):
    """读取文件工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read",
            description="读取文件内容。支持文本文件，可指定行号范围。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（可选）"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（可选）"
                    }
                },
                "required": ["file_path"]
            },
            requires_permission=False,
            dangerous=False,
            category="file"
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        file_path = args.get("file_path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        
        if not file_path:
            return ToolResult(
                success=False,
                output="",
                error="文件路径不能为空"
            )
        
        if not os.path.exists(file_path):
            return ToolResult(
                success=False,
                output="",
                error=f"文件不存在: {file_path}"
            )
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            if start_line is not None:
                start_idx = max(0, start_line - 1)
                lines = lines[start_idx:]
            
            if end_line is not None:
                end_idx = min(len(lines), end_line - (start_line or 1) + 1)
                lines = lines[:end_idx]
            
            content = "".join(lines)
            
            if len(content) > 50000:
                content = content[:50000] + f"\n\n... [内容过长，已截断，共{total_lines}行]"
            
            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "total_lines": total_lines,
                    "file_path": file_path
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
    """写入文件工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="write",
            description="写入文件内容。可创建新文件或覆盖现有文件。需要谨慎使用。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的内容"
                    },
                    "mode": {
                        "type": "string",
                        "description": "写入模式：write（覆盖）或 append（追加）",
                        "enum": ["write", "append"],
                        "default": "write"
                    }
                },
                "required": ["file_path", "content"]
            },
            requires_permission=True,
            dangerous=True,
            category="file"
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        file_path = args.get("file_path", "")
        content = args.get("content", "")
        mode = args.get("mode", "write")
        
        if not file_path:
            return ToolResult(
                success=False,
                output="",
                error="文件路径不能为空"
            )
        
        try:
            dir_path = os.path.dirname(file_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            write_mode = "a" if mode == "append" else "w"
            
            with open(file_path, write_mode, encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"成功写入文件: {file_path}（{len(content)}字符）",
                metadata={
                    "file_path": file_path,
                    "bytes_written": len(content.encode("utf-8")),
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


class SearchTool(ToolBase):
    """搜索文件内容工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="search",
            description="在文件中搜索匹配的内容。支持正则表达式。",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（支持正则）"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（文件或目录）"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件名模式（如 *.py）",
                        "default": "*"
                    }
                },
                "required": ["pattern", "path"]
            },
            requires_permission=False,
            dangerous=False,
            category="search"
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        import re
        import glob as glob_module
        
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        file_pattern = args.get("file_pattern", "*")
        
        if not pattern:
            return ToolResult(
                success=False,
                output="",
                error="搜索模式不能为空"
            )
        
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"无效的正则表达式: {e}"
            )
        
        results = []
        
        try:
            if os.path.isfile(path):
                files = [path]
            else:
                search_path = os.path.join(path, "**", file_pattern)
                files = glob_module.glob(search_path, recursive=True)
            
            for file_path in files:
                if not os.path.isfile(file_path):
                    continue
                
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_num}: {line.rstrip()}")
                                
                                if len(results) >= 100:
                                    results.append("... [结果过多，已截断]")
                                    break
                except Exception:
                    continue
                
                if len(results) >= 100:
                    break
            
            if not results:
                return ToolResult(
                    success=True,
                    output="未找到匹配结果",
                    metadata={"matches": 0}
                )
            
            return ToolResult(
                success=True,
                output="\n".join(results),
                metadata={"matches": len(results)}
            )
            
        except Exception as e:
            logger.error(f"[SearchTool] 搜索失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class ListFilesTool(ToolBase):
    """列出文件工具"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_files",
            description="列出目录下的文件和子目录。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径",
                        "default": "."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出",
                        "default": False
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "是否显示隐藏文件",
                        "default": False
                    }
                },
                "required": []
            },
            requires_permission=False,
            dangerous=False,
            category="file"
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        path = args.get("path", ".")
        recursive = args.get("recursive", False)
        show_hidden = args.get("show_hidden", False)
        
        if not os.path.exists(path):
            return ToolResult(
                success=False,
                output="",
                error=f"路径不存在: {path}"
            )
        
        if not os.path.isdir(path):
            return ToolResult(
                success=False,
                output="",
                error=f"不是目录: {path}"
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
                metadata={"count": len(results)}
            )
            
        except Exception as e:
            logger.error(f"[ListFilesTool] 列出失败: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )


class ThinkTool(ToolBase):
    """思考工具 - 用于记录推理过程"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="think",
            description="记录思考和推理过程。用于复杂问题的分析和规划。",
            parameters={
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "思考内容"
                    }
                },
                "required": ["thought"]
            },
            requires_permission=False,
            dangerous=False,
            category="reasoning"
        )
    
    async def execute(self, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        thought = args.get("thought", "")
        
        logger.info(f"[Think] {thought}")
        
        return ToolResult(
            success=True,
            output=f"[思考] {thought}",
            metadata={"thought": thought}
        )


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    """注册所有内置工具"""
    registry.register(BashTool())
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(SearchTool())
    registry.register(ListFilesTool())
    registry.register(ThinkTool())
    
    logger.info(f"[Tools] 已注册 {len(registry.list_names())} 个内置工具: {registry.list_names()}")
    
    return registry