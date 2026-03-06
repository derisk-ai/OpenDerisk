"""Unified Message Adapter for v1 and v2 AgentMessage.

Adapts both v1 (dataclass) and v2 (Pydantic) AgentMessage to a unified read interface.
Uses adapter pattern — does NOT modify existing AgentMessage classes.

Also supports plain dict messages (as used in function_callning_reply_messages).

v1 AgentMessage (dataclass in core/types.py):
    - tool_calls: Optional[List[Dict]]          # top-level field
    - context: Dict                              # contains tool_call_id, tool_calls
    - role, content, message_id, rounds, round_id, gmt_create, ...

v2 AgentMessage (Pydantic in core_v2/agent_base.py):
    - metadata: Dict                             # contains tool_calls, tool_call_id
    - role, content, timestamp

Plain dict messages (from base_agent.function_callning_reply_messages):
    - {"role": "ai"/"tool", "content": "...", "tool_calls": [...], "tool_call_id": "..."}
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Role name normalization: map legacy role names to standard ones
_ROLE_ALIASES = {
    "ai": "assistant",
    "human": "user",
}


def _getval(msg: Any, key: str, default: Any = None) -> Any:
    """Get a value from either a dict or object attribute."""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


class UnifiedMessageAdapter:
    """Adapts v1 and v2 AgentMessage to a unified read interface.

    All methods are static — no state, no side effects.
    Works with any object that has the expected attributes, including plain dicts.
    """

    @staticmethod
    def get_tool_calls(msg: Any) -> Optional[List[Dict]]:
        """Extract tool_calls from v1, v2, or dict message."""
        tc = _getval(msg, "tool_calls")
        if tc:
            return tc
        # v2: metadata dict
        metadata = _getval(msg, "metadata")
        if isinstance(metadata, dict):
            tc = metadata.get("tool_calls")
            if tc:
                return tc
        # v1: context fallback
        context = _getval(msg, "context")
        if isinstance(context, dict):
            tc = context.get("tool_calls")
            if tc:
                return tc
        return None

    @staticmethod
    def get_tool_call_id(msg: Any) -> Optional[str]:
        """Extract tool_call_id from v1, v2, or dict message."""
        tcid = _getval(msg, "tool_call_id")
        if tcid:
            return tcid
        # v2: metadata
        metadata = _getval(msg, "metadata")
        if isinstance(metadata, dict):
            tcid = metadata.get("tool_call_id")
            if tcid:
                return tcid
        # v1: context
        context = _getval(msg, "context")
        if isinstance(context, dict):
            tcid = context.get("tool_call_id")
            if tcid:
                return tcid
        return None

    @staticmethod
    def get_role(msg: Any) -> str:
        """Get message role (normalized: 'ai' -> 'assistant', 'human' -> 'user')."""
        raw = _getval(msg, "role", "")
        role = str(raw) if raw else "unknown"
        return _ROLE_ALIASES.get(role, role)

    @staticmethod
    def get_raw_role(msg: Any) -> str:
        """Get message role without normalization."""
        raw = _getval(msg, "role", "")
        return str(raw) if raw else "unknown"

    @staticmethod
    def get_content(msg: Any) -> str:
        """Get message content."""
        val = _getval(msg, "content", "")
        return str(val) if val else ""

    @staticmethod
    def get_timestamp(msg: Any) -> float:
        """Get timestamp as float epoch (unified for v1 and v2)."""
        # v2: datetime timestamp
        ts = _getval(msg, "timestamp")
        if isinstance(ts, datetime):
            return ts.timestamp()
        if isinstance(ts, (int, float)):
            return float(ts)
        # v1: gmt_create
        gmt = _getval(msg, "gmt_create")
        if isinstance(gmt, datetime):
            return gmt.timestamp()
        return 0.0

    @staticmethod
    def get_message_id(msg: Any) -> Optional[str]:
        """Get message ID."""
        return _getval(msg, "message_id")

    @staticmethod
    def get_round_id(msg: Any) -> Optional[str]:
        """Get round ID (v1-specific, v2 returns None)."""
        return _getval(msg, "round_id")

    @staticmethod
    def is_tool_call_message(msg: Any) -> bool:
        """Check if message is an assistant message containing tool_calls."""
        role = UnifiedMessageAdapter.get_role(msg)
        if role != "assistant":
            return False
        return UnifiedMessageAdapter.get_tool_calls(msg) is not None

    @staticmethod
    def is_tool_result_message(msg: Any) -> bool:
        """Check if message is a tool result message."""
        role = UnifiedMessageAdapter.get_role(msg)
        return role == "tool"

    @staticmethod
    def is_in_tool_call_group(msg: Any) -> bool:
        """Check if message belongs to a tool-call atomic group."""
        return (
            UnifiedMessageAdapter.is_tool_call_message(msg)
            or UnifiedMessageAdapter.is_tool_result_message(msg)
        )

    @staticmethod
    def get_token_estimate(msg: Any) -> int:
        """Estimate token count for a message."""
        content = UnifiedMessageAdapter.get_content(msg)
        tool_calls = UnifiedMessageAdapter.get_tool_calls(msg)
        tokens = len(content) // 4
        if tool_calls:
            tokens += len(json.dumps(tool_calls, ensure_ascii=False)) // 4
        return tokens

    @staticmethod
    def serialize_message(msg: Any) -> Dict:
        """Serialize message to a storable dict format."""
        return {
            "role": UnifiedMessageAdapter.get_role(msg),
            "content": UnifiedMessageAdapter.get_content(msg),
            "tool_calls": UnifiedMessageAdapter.get_tool_calls(msg),
            "tool_call_id": UnifiedMessageAdapter.get_tool_call_id(msg),
            "timestamp": UnifiedMessageAdapter.get_timestamp(msg),
            "message_id": UnifiedMessageAdapter.get_message_id(msg),
            "round_id": UnifiedMessageAdapter.get_round_id(msg),
        }

    @staticmethod
    def is_system_message(msg: Any) -> bool:
        """Check if message is a system message."""
        return UnifiedMessageAdapter.get_role(msg) == "system"

    @staticmethod
    def is_user_message(msg: Any) -> bool:
        """Check if message is a user message."""
        return UnifiedMessageAdapter.get_role(msg) in ("user", "human")

    @staticmethod
    def is_compaction_summary(msg: Any) -> bool:
        """Check if message is a compaction summary (should be skipped in re-compaction)."""
        context = _getval(msg, "context")
        if isinstance(context, dict) and context.get("is_compaction_summary"):
            return True
        metadata = _getval(msg, "metadata")
        if isinstance(metadata, dict) and metadata.get("is_compaction_summary"):
            return True
        content = UnifiedMessageAdapter.get_content(msg)
        if content and content.startswith("[History Compaction]"):
            return True
        return False

    @staticmethod
    def get_tool_name_for_tool_result(
        tool_result_msg: Any,
        messages: List[Any],
        tool_result_idx: int,
    ) -> Optional[str]:
        """Get tool name for a tool result by looking up its tool_call_id in preceding assistant messages."""
        tool_call_id = UnifiedMessageAdapter.get_tool_call_id(tool_result_msg)
        if not tool_call_id:
            return None

        for i in range(tool_result_idx - 1, max(tool_result_idx - 10, -1), -1):
            msg = messages[i]
            if UnifiedMessageAdapter.get_role(msg) != "assistant":
                continue

            tool_calls = UnifiedMessageAdapter.get_tool_calls(msg)
            if not tool_calls:
                continue

            for tc in tool_calls:
                if isinstance(tc, dict) and tc.get("id") == tool_call_id:
                    return tc.get("function", {}).get("name")

        return None

    @staticmethod
    def format_message_for_summary(msg: Any) -> str:
        """Format a single message for inclusion in compaction summary generation.

        Ported from ImprovedSessionCompaction._format_messages_for_summary().
        """
        role = UnifiedMessageAdapter.get_role(msg)
        content = UnifiedMessageAdapter.get_content(msg)

        # Skip existing compaction summaries
        if UnifiedMessageAdapter.is_compaction_summary(msg):
            return ""

        # Flatten tool-call assistant messages
        tool_calls = UnifiedMessageAdapter.get_tool_calls(msg)
        if role == "assistant" and tool_calls:
            tc_descriptions = []
            for tc in (tool_calls if isinstance(tool_calls, list) else []):
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = func.get("name", "unknown_tool")
                args = func.get("arguments", "")
                if isinstance(args, str) and len(args) > 300:
                    args = args[:300] + "..."
                tc_descriptions.append(f"  - {name}({args})")
            tc_text = "\n".join(tc_descriptions)
            display = f"[assistant]: Called tools:\n{tc_text}"
            if content:
                display = f"[assistant]: {content}\nCalled tools:\n{tc_text}"
            return display

        # Flatten tool response messages
        tool_call_id = UnifiedMessageAdapter.get_tool_call_id(msg)
        if role == "tool" and tool_call_id:
            if len(content) > 1500:
                content = content[:1500] + "... [truncated]"
            return f"[tool result ({tool_call_id})]: {content}"

        # Regular messages
        if len(content) > 1500:
            content = content[:1500] + "... [truncated]"
        return f"[{role}]: {content}"
