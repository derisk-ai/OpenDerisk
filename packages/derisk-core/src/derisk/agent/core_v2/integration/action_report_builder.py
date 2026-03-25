"""
ActionOutput 构建工具函数

从 V2StreamChunk 构建 ActionOutput 列表，供 runtime._push_stream_chunk()
和 core_v2_api.py 共用，为 vis_window3 渲染提供 action_report 数据。
"""

import logging
from typing import List, Optional

from .adapter import V2StreamChunk

logger = logging.getLogger(__name__)


def build_action_report_from_chunk(chunk: V2StreamChunk) -> Optional[List]:
    """根据 V2StreamChunk 构建 ActionOutput 列表。

    Args:
        chunk: 解析后的流式数据块

    Returns:
        ActionOutput 列表，或 None（非工具类型 chunk）
    """
    if chunk.type not in ("tool_start", "tool_result"):
        return None

    try:
        from derisk.agent.core.action.base import ActionOutput
    except ImportError:
        logger.warning("ActionOutput import failed, skipping action_report build")
        return None

    tool_name = chunk.metadata.get("tool_name", "unknown")
    action_id = chunk.metadata.get("action_id", "")

    if chunk.type == "tool_start":
        action = ActionOutput(
            content="",
            action_id=action_id,
            action=tool_name,
            action_name=tool_name,
            name=tool_name,
            action_input=chunk.metadata.get("tool_args"),
            state="running",
            stream=True,
            is_exe_success=True,
        )
        return [action]

    elif chunk.type == "tool_result":
        success = chunk.metadata.get("success", True)
        content = chunk.content or ""
        view = content[:2000] if content else ""

        action = ActionOutput(
            content=content,
            action_id=action_id,
            action=tool_name,
            action_name=tool_name,
            name=tool_name,
            state="complete" if success else "failed",
            is_exe_success=success,
            view=view,
            stream=False,
        )
        return [action]

    return None
