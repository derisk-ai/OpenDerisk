"""
Agent工具模块

提供Agent核心能力：
- TerminateTool: 终止对话
- KnowledgeTool: 知识检索
"""

from typing import Dict, Any, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class TerminateTool(ToolBase):
    """
    终止对话工具

    用于结束当前对话
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="terminate",
            display_name="End Conversation",
            description="End the current conversation with a final message",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            requires_permission=False,
            tags=["conversation", "end", "finish"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Final message to the user",
                }
            },
            "required": ["message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        message = args.get("message", "Task completed")

        return ToolResult.ok(
            output=f"[TERMINATE] {message}",
            tool_name=self.name,
            metadata={"terminate": True, "message": message},
        )


class KnowledgeTool(ToolBase):
    """
    知识检索工具

    用于从知识库中检索相关信息
    """

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="knowledge_search",
            display_name="Knowledge Search",
            description="Search the knowledge base for relevant information",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["knowledge", "search", "rag", "retrieval"],
            timeout=60,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for the knowledge base",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of results to return",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional filters for knowledge search",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        query = args.get("query", "")
        top_k = args.get("top_k", 5)
        filters = args.get("filters", {})

        if not query:
            return ToolResult.fail(error="Search query cannot be empty", tool_name=self.name)

        try:
            knowledge_client = None
            if context:
                knowledge_client = context.get_resource("knowledge_client")

            if not knowledge_client:
                return ToolResult.fail(
                    error="Knowledge base not available", tool_name=self.name
                )

            results = await knowledge_client.search(
                query=query, top_k=top_k, filters=filters
            )

            if not results:
                return ToolResult.ok(
                    output="No relevant results found",
                    tool_name=self.name,
                    metadata={"query": query, "results_count": 0},
                )

            formatted = []
            for i, result in enumerate(results, 1):
                score = result.get("score", 0)
                content = result.get("content", "")
                source = result.get("source", "unknown")
                formatted.append(f"[{i}] (score: {score:.2f}) [{source}]\n{content}")

            return ToolResult.ok(
                output="\n\n".join(formatted),
                tool_name=self.name,
                metadata={"query": query, "results_count": len(results)},
            )

        except Exception as e:
            logger.error(f"[KnowledgeTool] Search failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
