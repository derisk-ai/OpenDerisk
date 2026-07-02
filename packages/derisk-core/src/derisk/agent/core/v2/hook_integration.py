"""HookManager 集成辅助：构造 hook context dict。

context 字段对齐 BAIZE：
- pre/post_tool_use: tool_action.py:1334-1341
- turn_complete: base_agent.py:1327-1355
"""
from typing import Any, Dict, Optional

from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult


def build_pre_tool_use_context(
    tool_call: V2ToolCall, ctx: Any,
) -> Dict[str, Any]:
    return {
        "tool_name": tool_call.name,
        "args": tool_call.args,
        "context": ctx,
        "conv_id": getattr(ctx, "conversation_id", None),
        "agent_id": getattr(ctx, "agent_id", None),
        "step_id": getattr(ctx, "step_id", None),
    }


def build_post_tool_use_context(
    tool_call: V2ToolCall,
    ctx: Any,
    result: Optional[V2ToolResult],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tool_name": tool_call.name,
        "args": tool_call.args,
        "context": ctx,
        "result": result,
        "error": error,
        "conv_id": getattr(ctx, "conversation_id", None),
        "agent_id": getattr(ctx, "agent_id", None),
    }


def build_turn_complete_context(
    *,
    round: int,
    interrupted: bool,
    user_prompt: str,
    final_answer: Optional[str],
    user_id: Optional[str],
    conv_id: str,
    agent_id: str,
    step_count: int,
) -> Dict[str, Any]:
    return {
        "round": round,
        "interrupted": interrupted,
        "user_prompt": user_prompt,
        "final_answer": final_answer,
        "user_id": user_id,
        "conv_id": conv_id,
        "agent_id": agent_id,
        "step_count": step_count,
    }


def build_conversation_complete_context(
    *,
    conv_id: str,
    agent_id: str,
    user_id: Optional[str],
    total_rounds: int,
) -> Dict[str, Any]:
    return {
        "conv_id": conv_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "total_rounds": total_rounds,
    }
