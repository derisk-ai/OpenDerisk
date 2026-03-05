"""History recovery tools — injected ONLY after first compaction.

Provides agents with read-only access to archived history chapters,
search over past conversations, tool-call history, and catalog overview.

Uses FunctionTool(name=..., func=..., description=...) constructor.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Dict

from derisk.agent.resource.tool.base import FunctionTool

if TYPE_CHECKING:
    from derisk.agent.core.memory.compaction_pipeline import UnifiedCompactionPipeline

logger = logging.getLogger(__name__)


def create_history_tools(
    pipeline: "UnifiedCompactionPipeline",
) -> Dict[str, FunctionTool]:
    """Create history recovery tools bound to the given pipeline.

    These tools should ONLY be registered after the first compaction
    (i.e. ``pipeline.has_compacted is True``).
    """

    # -----------------------------------------------------------------
    # 1. read_history_chapter
    # -----------------------------------------------------------------
    async def read_history_chapter(chapter_index: int) -> str:
        """读取指定历史章节的完整归档内容。

        当你需要回顾之前的操作细节或找回之前的发现时使用此工具。
        章节索引从 0 开始，可通过 get_history_overview 获取所有章节列表。

        Args:
            chapter_index: 章节索引号 (从 0 开始)

        Returns:
            章节的完整归档内容，包括所有消息和工具调用结果
        """
        result = await pipeline.read_chapter(chapter_index)
        return result or f"Chapter {chapter_index} 内容为空。"

    # -----------------------------------------------------------------
    # 2. search_history
    # -----------------------------------------------------------------
    async def search_history(query: str, max_results: int = 10) -> str:
        """在所有已归档的历史章节中搜索信息。

        搜索范围包括章节总结、关键决策和工具调用记录。
        当你需要查找之前讨论过的特定主题或做出的决定时使用此工具。

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            匹配的历史记录，包含章节引用
        """
        return await pipeline.search_chapters(query, max_results)

    # -----------------------------------------------------------------
    # 3. get_tool_call_history
    # -----------------------------------------------------------------
    async def get_tool_call_history(
        tool_name: str = "",
        limit: int = 20,
    ) -> str:
        """获取工具调用历史记录。

        从 WorkLog 中检索工具调用记录。可按工具名称过滤。

        Args:
            tool_name: 工具名称过滤（空字符串表示所有工具）
            limit: 返回的最大记录数

        Returns:
            工具调用历史的格式化文本
        """
        if not pipeline.work_log_storage:
            return "WorkLog 未配置，无法获取工具调用历史。"

        try:
            entries = await pipeline.work_log_storage.get_work_log(pipeline.conv_id)
        except Exception as e:
            logger.warning(f"Failed to get work log: {e}")
            return f"获取工具调用历史失败: {e}"

        if tool_name:
            entries = [e for e in entries if e.tool == tool_name]

        entries = entries[-limit:]

        if not entries:
            msg = "没有找到工具调用记录"
            if tool_name:
                msg += f" (工具名: {tool_name})"
            return msg + "。"

        lines = [f"=== 工具调用历史 (最近 {len(entries)} 条) ===", ""]
        for i, entry in enumerate(entries, 1):
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            status = "✓" if entry.success else "✗"
            summary = entry.summary or (entry.result or "")[:120]
            lines.append(f"{i}. [{status}] {ts} | {entry.tool}")
            if entry.args:
                args_str = str(entry.args)[:200]
                lines.append(f"   Args: {args_str}")
            if summary:
                lines.append(f"   Result: {summary}")
            lines.append("")

        return "\n".join(lines)

    # -----------------------------------------------------------------
    # 4. get_history_overview
    # -----------------------------------------------------------------
    async def get_history_overview() -> str:
        """获取历史章节目录概览。

        返回所有已归档章节的列表，包括每个章节的时间范围、
        消息数、工具调用数和摘要。可以根据概览信息决定
        是否需要 read_history_chapter 读取特定章节的详情。

        Returns:
            历史章节目录的格式化文本
        """
        catalog = await pipeline.get_catalog()
        return catalog.get_overview()

    # -----------------------------------------------------------------
    # Assemble tools using FunctionTool constructor (NOT from_function!)
    # -----------------------------------------------------------------
    return {
        "read_history_chapter": FunctionTool(
            name="read_history_chapter",
            func=read_history_chapter,
            description=(
                "读取指定历史章节的完整归档内容。"
                "当你需要回顾之前的操作细节或找回之前的发现时使用此工具。"
                "章节索引从 0 开始，可通过 get_history_overview 获取所有章节列表。"
            ),
        ),
        "search_history": FunctionTool(
            name="search_history",
            func=search_history,
            description=(
                "在所有已归档的历史章节中搜索信息。"
                "搜索范围包括章节总结、关键决策和工具调用记录。"
                "当你需要查找之前讨论过的特定主题或做出的决定时使用此工具。"
            ),
        ),
        "get_tool_call_history": FunctionTool(
            name="get_tool_call_history",
            func=get_tool_call_history,
            description=(
                "获取工具调用历史记录。"
                "从 WorkLog 中检索工具调用记录，可按工具名称过滤。"
            ),
        ),
        "get_history_overview": FunctionTool(
            name="get_history_overview",
            func=get_history_overview,
            description=(
                "获取历史章节目录概览。"
                "返回所有已归档章节的列表，包括时间范围、消息数、工具调用数和摘要。"
            ),
        ),
    }
