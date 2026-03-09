"""
ThinkTool - 思考工具
已迁移到统一工具框架
"""

from typing import Any, Dict, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class ThinkTool(ToolBase):
    """思考工具 - 用于记录推理过程 - 已迁移"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="think",
            display_name="Think",
            description=(
                "Record your thinking and reasoning process. "
                "Use this tool to analyze complex problems, plan solutions, "
                "or document your thought process for transparency."
            ),
            category=ToolCategory.REASONING,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.CORE,
            requires_permission=False,
            tags=["reasoning", "thinking", "analysis", "planning"],
            timeout=10,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Your thinking content, reasoning process, or analysis",
                }
            },
            "required": ["thought"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        thought = args.get("thought", "")

        if not thought:
            return ToolResult(
                success=False, output="", error="思考内容不能为空", tool_name=self.name
            )

        logger.info(f"[Think] {thought[:200]}...")

        return ToolResult(
            success=True,
            output=f"💭 [思考] {thought}",
            tool_name=self.name,
            metadata={"thought": thought},
        )


def register_reasoning_tools(registry) -> None:
    """注册推理工具"""
    from ...registry import ToolRegistry

    registry.register(ThinkTool())
    logger.info("[ReasoningTools] 已注册推理工具: think")
