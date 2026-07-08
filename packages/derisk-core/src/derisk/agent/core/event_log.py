"""Tier 3.1: 事件日志发射器（derisk-core 层，加法版本）。

提供 fire-and-forget 的事件追加接口，供 base_agent / react_master_agent /
tool_action 在 think/act/tool_call 边界调用。

设计原则：
- 与 gpts_message/gpts_work_log 共存（additive），不替代
- emit_event 失败只 log warning，不影响主流程（fire-and-forget）
- 通过 derisk_serve 的 EventLogDao 持久化（lazy import 避免循环依赖）

事件类型（event_type）：
- think_start: LLM 调用开始（event_data: {prompt_rounds, model_name}）
- think_end: LLM 调用结束（event_data: {thinking, content, tool_calls, metrics}）
- act_start: 工具执行开始（event_data: {tool_name, args}）
- act_end: 工具执行结束（event_data: {tool_name, success, result_summary}）
- turn_start: 一轮 think+act 开始
- turn_end: 一轮 think+act 结束
- conversation_start / conversation_end: 会话级边界
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 标准事件类型常量
EVENT_THINK_START = "think_start"
EVENT_THINK_END = "think_end"
EVENT_ACT_START = "act_start"
EVENT_ACT_END = "act_end"
EVENT_TURN_START = "turn_start"
EVENT_TURN_END = "turn_end"
EVENT_CONVERSATION_START = "conversation_start"
EVENT_CONVERSATION_END = "conversation_end"


async def _emit_event_safe(
    conv_id: str,
    event_type: str,
    message_id: Optional[str],
    event_data: Optional[Dict[str, Any]],
) -> None:
    """fire-and-forget 事件追加，失败只 log warning。"""
    if not conv_id or not event_type:
        return
    try:
        from derisk_serve.agent.db.gpts_events_db import EventLogDao

        dao = EventLogDao()
        await asyncio.to_thread(
            dao.append_event, conv_id, event_type, message_id, event_data
        )
    except Exception as e:
        logger.debug(
            f"[event-log] emit failed conv={conv_id} type={event_type}: {e}"
        )


def emit_event(
    conv_id: str,
    event_type: str,
    message_id: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
) -> None:
    """非阻塞事件追加：spawn 一个 task 不 await，立即返回。

    在 agent loop 边界点调用（think 前后 / act 前后），不影响主流程。

    Args:
        conv_id: 会话 ID
        event_type: 事件类型（见模块顶部常量）
        message_id: 该事件所属的 message id（可选）
        event_data: 事件负载 dict（可选，会 JSON 序列化）
    """
    if not conv_id or not event_type:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed() or not loop.is_running():
            logger.debug(
                f"[event-log] no running event loop, skipping emit for conv={conv_id} type={event_type}"
            )
            return
        # 在 loop 内 create_task（coroutine 不会泄漏）
        loop.create_task(
            _emit_event_safe(conv_id, event_type, message_id, event_data)
        )
    except RuntimeError:
        # No running event loop — 静默跳过
        logger.debug(
            f"[event-log] no event loop, skipping emit for conv={conv_id} type={event_type}"
        )


# ---- 高层便捷函数 ----

def emit_think_start(
    conv_id: str,
    message_id: Optional[str] = None,
    model_name: Optional[str] = None,
    round_index: Optional[int] = None,
) -> None:
    """LLM think 开始事件。"""
    emit_event(
        conv_id=conv_id,
        event_type=EVENT_THINK_START,
        message_id=message_id,
        event_data={
            "model_name": model_name,
            "round_index": round_index,
        },
    )


def emit_think_end(
    conv_id: str,
    message_id: Optional[str] = None,
    thinking: Optional[str] = None,
    content: Optional[str] = None,
    tool_calls: Optional[list] = None,
    total_tokens: Optional[int] = None,
) -> None:
    """LLM think 结束事件。"""
    emit_event(
        conv_id=conv_id,
        event_type=EVENT_THINK_END,
        message_id=message_id,
        event_data={
            "thinking": (thinking or "")[:500],  # 截断避免超大事件
            "content": (content or "")[:500],
            "tool_calls": tool_calls or [],
            "total_tokens": total_tokens,
        },
    )


def emit_act_start(
    conv_id: str,
    tool_name: str,
    message_id: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
) -> None:
    """工具执行开始事件。"""
    emit_event(
        conv_id=conv_id,
        event_type=EVENT_ACT_START,
        message_id=message_id,
        event_data={
            "tool_name": tool_name,
            "args": args or {},
        },
    )


def emit_act_end(
    conv_id: str,
    tool_name: str,
    success: bool,
    message_id: Optional[str] = None,
    result_summary: Optional[str] = None,
) -> None:
    """工具执行结束事件。"""
    emit_event(
        conv_id=conv_id,
        event_type=EVENT_ACT_END,
        message_id=message_id,
        event_data={
            "tool_name": tool_name,
            "success": success,
            "result_summary": (result_summary or "")[:500],
        },
    )
