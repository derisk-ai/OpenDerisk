"""
ActionOutput 构建工具函数

从 V2StreamChunk 构建 ActionOutput 列表，供 runtime._push_stream_chunk()
和 core_v2_api.py 共用，为 vis_window3 渲染提供 action_report 数据。

注意：现在 Agent 内部已经实现了完整的 VIS 推送能力（通过 _push_vis_message 方法），
此模块作为 Runtime 层的备用方案，确保向后兼容。
"""

import logging
from typing import List, Optional, Dict, Any

from .adapter import V2StreamChunk

logger = logging.getLogger(__name__)


def build_action_report_from_chunk(
    chunk: V2StreamChunk,
    thought: Optional[str] = None,
) -> Optional[List]:
    """根据 V2StreamChunk 构建 ActionOutput 列表。

    Args:
        chunk: 解析后的流式数据块
        thought: 思考内容（可选）

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
    tool_args = chunk.metadata.get("tool_args", {})

    if chunk.type == "tool_start":
        action = ActionOutput(
            content="",
            action_id=action_id,
            action=tool_name,
            action_name=tool_name,
            name=tool_name,
            action_input=tool_args,
            state="running",
            stream=True,
            is_exe_success=True,
            thought=thought or "",
        )
        logger.debug(
            f"[action_report_builder] Built tool_start ActionOutput: {tool_name}"
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
            action_input=tool_args,
            state="complete" if success else "failed",
            is_exe_success=success,
            view=view,
            stream=False,
            thought=thought or "",
        )
        logger.debug(
            f"[action_report_builder] Built tool_result ActionOutput: {tool_name}, success={success}, len={len(content)}"
        )
        return [action]

    return None


def build_complete_action_report(
    tool_name: str,
    tool_args: Dict[str, Any],
    result_content: str,
    action_id: str,
    success: bool = True,
    state: str = "complete",
    thought: Optional[str] = None,
) -> Optional[List]:
    """
    构建完整的 ActionOutput 列表（供外部调用）

    Args:
        tool_name: 工具名称
        tool_args: 工具参数
        result_content: 执行结果内容
        action_id: 动作ID
        success: 是否成功
        state: 状态（running/complete/failed）
        thought: 思考内容

    Returns:
        ActionOutput 列表
    """
    try:
        from derisk.agent.core.action.base import ActionOutput
    except ImportError:
        logger.warning("ActionOutput import failed")
        return None

    view = result_content[:2000] if result_content else ""

    action = ActionOutput(
        content=result_content,
        action_id=action_id,
        action=tool_name,
        action_name=tool_name,
        name=tool_name,
        action_input=tool_args,
        state=state,
        is_exe_success=success,
        view=view,
        stream=False,
        thought=thought or "",
    )

    return [action]
