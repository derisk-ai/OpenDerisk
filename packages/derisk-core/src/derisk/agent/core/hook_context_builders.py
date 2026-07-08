"""PR 6: Hook context builders 抽取（pure refactor，无行为变化）。

把散落在 tool_action.py / base_agent.py / react_master_agent.py 内联构造的
hook 上下文抽成独立函数，统一字段命名，提升可测性。

V1 已有的字段约定（保持向后兼容）：
- pre_tool_use: tool_name, tool_input, agent_name, agent_role, session_id, app_code
- post_tool_use: + tool_response, success
- turn_complete: agent_name, agent_role, session_id, app_code, user_id, user_name, round, user_prompt, final_answer
- conversation_complete: agent_name, agent_role, session_id, app_code, final_answer, success
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def build_pre_tool_use_context(
    tool_name: str,
    tool_input: Dict[str, Any],
    agent_name: Optional[str],
    agent_role: Optional[str],
    session_id: Optional[str],
    app_code: Optional[str],
) -> Dict[str, Any]:
    """构造 pre_tool_use hook 上下文。"""
    return {
        "tool_name": tool_name,
        "tool_input": dict(tool_input or {}),
        "agent_name": agent_name,
        "agent_role": agent_role,
        "session_id": session_id,
        "app_code": app_code,
    }


def build_post_tool_use_context(
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_response: Any,
    success: bool,
    agent_name: Optional[str],
    agent_role: Optional[str],
    session_id: Optional[str],
    app_code: Optional[str],
) -> Dict[str, Any]:
    """构造 post_tool_use hook 上下文。"""
    return {
        "tool_name": tool_name,
        "tool_input": dict(tool_input or {}),
        "tool_response": tool_response,
        "success": bool(success),
        "agent_name": agent_name,
        "agent_role": agent_role,
        "session_id": session_id,
        "app_code": app_code,
    }


def build_turn_complete_context(
    agent_name: str,
    agent_role: Optional[str],
    session_id: Optional[str],
    app_code: Optional[str],
    user_id: Optional[str],
    user_name: Optional[str],
    round_index: Optional[int],
    user_prompt: Optional[str],
    final_answer: Optional[str],
    interrupted: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 turn_complete hook 上下文。"""
    ctx = {
        "agent_name": agent_name,
        "agent_role": agent_role,
        "session_id": session_id,
        "app_code": app_code,
        "user_id": user_id,
        "user_name": user_name,
        "round": round_index,
        "user_prompt": user_prompt,
        "final_answer": final_answer,
        "interrupted": interrupted,
    }
    if extra:
        ctx.update(extra)
    return ctx


def build_conversation_complete_context(
    agent_name: str,
    agent_role: Optional[str],
    session_id: Optional[str],
    app_code: Optional[str],
    final_answer: Optional[str],
    success: bool,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 conversation_complete hook 上下文。"""
    ctx = {
        "agent_name": agent_name,
        "agent_role": agent_role,
        "session_id": session_id,
        "app_code": app_code,
        "final_answer": final_answer,
        "success": bool(success),
    }
    if extra:
        ctx.update(extra)
    return ctx
