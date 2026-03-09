"""
SearchTool - 搜索文件内容工具
已迁移到统一工具框架
"""

import os
import re
import glob as glob_module
from typing import Any, Dict, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class SearchTool(ToolBase):
    """搜索文件内容工具 - 已迁移"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="search",
            display_name="Search Files",
            description=(
                "Search for patterns in files. Supports regular expressions. "
                "Use this tool to find specific content within files or directories."
            ),
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.CORE,
            requires_permission=False,
            tags=["search", "grep", "find", "pattern"],
            timeout=60,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (supports regex)",
                },
                "path": {
                    "type": "string",
                    "description": "Search path (file or directory)",
                    "default": ".",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "File name pattern (e.g., *.py)",
                    "default": "*",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        file_pattern = args.get("file_pattern", "*")

        if not pattern:
            return ToolResult(
                success=False, output="", error="搜索模式不能为空", tool_name=self.name
            )

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(
                success=False,
                output="",
                error=f"无效的正则表达式: {e}",
                tool_name=self.name,
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
                                results.append(
                                    f"{file_path}:{line_num}: {line.rstrip()}"
                                )

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
                    tool_name=self.name,
                    metadata={"matches": 0},
                )

            return ToolResult(
                success=True,
                output="\n".join(results),
                tool_name=self.name,
                metadata={"matches": len(results)},
            )

        except Exception as e:
            logger.error(f"[SearchTool] 搜索失败: {e}")
            return ToolResult(
                success=False, output="", error=str(e), tool_name=self.name
            )
