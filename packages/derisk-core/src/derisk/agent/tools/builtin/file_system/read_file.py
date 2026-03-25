"""
ReadFile Tool - 读取 AgentFileSystem 中保存的文件内容

用于读取之前执行结果中被归档的大文件。
"""

import logging
from typing import Any, Dict, Optional

from ..sandbox.base import SandboxToolBase
from ...base import ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


class ReadFileTool(SandboxToolBase):
    """
    读取 AgentFileSystem 中保存的文件内容

    用于读取之前执行结果中被归档的大文件。
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read_file",
            display_name="Read Archived File",
            description="读取 AgentFileSystem 中保存的文件内容。用于读取之前执行结果中被归档的大文件。",
            category=ToolCategory.FILE_SYSTEM,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["file", "read", "archive", "agent_file_system"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "文件 key，在截断提示中显示，如 'view_abc123_1234567890'",
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始）",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "读取行数，-1 表示读取到文件末尾",
                    "default": 500,
                },
            },
            "required": ["file_key"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """执行文件读取"""
        file_key = args.get("file_key")
        offset = args.get("offset", 1)
        limit = args.get("limit", 500)

        if not file_key:
            return ToolResult.fail(
                error="file_key 参数不能为空",
                tool_name=self.name,
            )

        agent_file_system = self._get_agent_file_system(context)
        if not agent_file_system:
            return ToolResult.fail(
                error="AgentFileSystem 未初始化",
                tool_name=self.name,
            )

        try:
            content = await agent_file_system.read_file(file_key)
            if content is None:
                return ToolResult.fail(
                    error=f"文件不存在: {file_key}",
                    tool_name=self.name,
                )

            lines = content.split("\n")
            total_lines = len(lines)

            start_idx = max(0, offset - 1)

            if limit == -1:
                end_idx = total_lines
            else:
                end_idx = min(start_idx + limit, total_lines)

            selected_lines = lines[start_idx:end_idx]
            result = "\n".join(selected_lines)

            header = f"[文件: {file_key}]\n[显示第 {offset}-{end_idx} 行，共 {total_lines} 行]\n\n"

            return ToolResult.ok(
                output=header + result,
                tool_name=self.name,
                metadata={
                    "file_key": file_key,
                    "total_lines": total_lines,
                    "start_line": offset,
                    "end_line": end_idx,
                },
            )

        except Exception as e:
            logger.exception(f"Failed to read file: {e}")
            return ToolResult.fail(
                error=f"读取文件失败: {str(e)}",
                tool_name=self.name,
            )

    def _get_agent_file_system(self, context: Optional[Any]):
        """获取 AgentFileSystem 实例"""
        if not context:
            return None

        agent_file_system = getattr(context, "agent_file_system", None)
        if agent_file_system:
            return agent_file_system

        agent = getattr(context, "agent", None) or context
        if hasattr(agent, "_agent_file_system"):
            return agent._agent_file_system

        return None
