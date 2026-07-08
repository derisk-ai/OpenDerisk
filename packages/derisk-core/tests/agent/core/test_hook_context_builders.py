"""PR 6: Hook context builders 单元测试。

覆盖：
- 4 个 builder 返回正确字段
- 字段类型 / None 处理
- extra 字段合并
- bool 强转（success / interrupted）
- tool_input dict 浅拷贝（修改原 dict 不影响 ctx）
- 回归：V1 现有 hook 调用点改用 builder 后字段不变
"""
from __future__ import annotations

import pytest

from derisk.agent.core.hook_context_builders import (
    build_conversation_complete_context,
    build_post_tool_use_context,
    build_pre_tool_use_context,
    build_turn_complete_context,
)


# ---------------- build_pre_tool_use_context ----------------

class TestBuildPreToolUseContext:
    def test_returns_all_fields(self):
        ctx = build_pre_tool_use_context(
            tool_name="execute_sql",
            tool_input={"sql": "SELECT 1"},
            agent_name="dba",
            agent_role="engineer",
            session_id="sess-1",
            app_code="app-1",
        )
        assert ctx == {
            "tool_name": "execute_sql",
            "tool_input": {"sql": "SELECT 1"},
            "agent_name": "dba",
            "agent_role": "engineer",
            "session_id": "sess-1",
            "app_code": "app-1",
        }

    def test_none_tool_input_becomes_empty_dict(self):
        ctx = build_pre_tool_use_context(
            tool_name="t",
            tool_input=None,
            agent_name=None,
            agent_role=None,
            session_id=None,
            app_code=None,
        )
        assert ctx["tool_input"] == {}
        assert ctx["agent_name"] is None
        assert ctx["agent_role"] is None
        assert ctx["session_id"] is None
        assert ctx["app_code"] is None

    def test_tool_input_copied(self):
        """builder 内部 dict(tool_input or {})，修改原 dict 不影响 ctx。"""
        original = {"a": 1}
        ctx = build_pre_tool_use_context(
            tool_name="t",
            tool_input=original,
            agent_name=None,
            agent_role=None,
            session_id=None,
            app_code=None,
        )
        original["a"] = 999
        assert ctx["tool_input"] == {"a": 1}


# ---------------- build_post_tool_use_context ----------------

class TestBuildPostToolUseContext:
    def test_returns_all_fields(self):
        ctx = build_post_tool_use_context(
            tool_name="execute_sql",
            tool_input={"sql": "SELECT 1"},
            tool_response="rows: 0",
            success=True,
            agent_name="dba",
            agent_role="engineer",
            session_id="sess-1",
            app_code="app-1",
        )
        assert ctx == {
            "tool_name": "execute_sql",
            "tool_input": {"sql": "SELECT 1"},
            "tool_response": "rows: 0",
            "success": True,
            "agent_name": "dba",
            "agent_role": "engineer",
            "session_id": "sess-1",
            "app_code": "app-1",
        }

    def test_success_bool_coerced(self):
        """success 用 bool() 强转，避免 truthy/falsy 误传。"""
        ctx_truthy = build_post_tool_use_context(
            tool_name="t",
            tool_input={},
            tool_response=None,
            success=1,
            agent_name=None,
            agent_role=None,
            session_id=None,
            app_code=None,
        )
        assert ctx_truthy["success"] is True

        ctx_falsy = build_post_tool_use_context(
            tool_name="t",
            tool_input={},
            tool_response=None,
            success=0,
            agent_name=None,
            agent_role=None,
            session_id=None,
            app_code=None,
        )
        assert ctx_falsy["success"] is False

    def test_tool_response_can_be_any_type(self):
        """tool_response 不强转，保留原类型（dict / list / str / None）。"""
        for resp in [{"k": 1}, [1, 2], "string", 42, None]:
            ctx = build_post_tool_use_context(
                tool_name="t",
                tool_input={},
                tool_response=resp,
                success=True,
                agent_name=None,
                agent_role=None,
                session_id=None,
                app_code=None,
            )
            assert ctx["tool_response"] is resp


# ---------------- build_turn_complete_context ----------------

class TestBuildTurnCompleteContext:
    def test_returns_all_fields(self):
        ctx = build_turn_complete_context(
            agent_name="dba",
            agent_role="engineer",
            session_id="sess-1",
            app_code="app-1",
            user_id="u1",
            user_name="alice",
            round_index=3,
            user_prompt="hello",
            final_answer="world",
            interrupted=False,
        )
        assert ctx == {
            "agent_name": "dba",
            "agent_role": "engineer",
            "session_id": "sess-1",
            "app_code": "app-1",
            "user_id": "u1",
            "user_name": "alice",
            "round": 3,
            "user_prompt": "hello",
            "final_answer": "world",
            "interrupted": False,
        }

    def test_round_index_key_is_round_not_round_index(self):
        """V1 字段名是 `round`（不是 `round_index`），保持向后兼容。"""
        ctx = build_turn_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            user_id=None,
            user_name=None,
            round_index=5,
            user_prompt=None,
            final_answer=None,
        )
        assert ctx["round"] == 5
        assert "round_index" not in ctx

    def test_interrupted_default_false(self):
        ctx = build_turn_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            user_id=None,
            user_name=None,
            round_index=1,
            user_prompt=None,
            final_answer=None,
        )
        assert ctx["interrupted"] is False

    def test_extra_merged_at_top_level(self):
        """extra 字段合并到顶层（不是嵌套在 extra 里）。"""
        ctx = build_turn_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            user_id=None,
            user_name=None,
            round_index=1,
            user_prompt=None,
            final_answer=None,
            extra={"success": True, "custom_field": "x"},
        )
        assert ctx["success"] is True
        assert ctx["custom_field"] == "x"

    def test_extra_can_override_standard_field(self):
        """extra 优先级高于默认值（ctx.update(extra) 在默认字段之后）。"""
        ctx = build_turn_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            user_id=None,
            user_name=None,
            round_index=1,
            user_prompt=None,
            final_answer=None,
            extra={"interrupted": True},  # 覆盖默认 False
        )
        assert ctx["interrupted"] is True

    def test_extra_none_skipped(self):
        ctx = build_turn_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            user_id=None,
            user_name=None,
            round_index=1,
            user_prompt=None,
            final_answer=None,
            extra=None,
        )
        assert "success" not in ctx


# ---------------- build_conversation_complete_context ----------------

class TestBuildConversationCompleteContext:
    def test_returns_all_fields(self):
        ctx = build_conversation_complete_context(
            agent_name="dba",
            agent_role="engineer",
            session_id="sess-1",
            app_code="app-1",
            final_answer="done",
            success=True,
        )
        assert ctx == {
            "agent_name": "dba",
            "agent_role": "engineer",
            "session_id": "sess-1",
            "app_code": "app-1",
            "final_answer": "done",
            "success": True,
        }

    def test_success_bool_coerced(self):
        ctx = build_conversation_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            final_answer=None,
            success=1,
        )
        assert ctx["success"] is True

    def test_extra_merged(self):
        ctx = build_conversation_complete_context(
            agent_name="a",
            agent_role=None,
            session_id=None,
            app_code=None,
            final_answer=None,
            success=True,
            extra={"total_tokens": 12345, "total_turns": 5},
        )
        assert ctx["total_tokens"] == 12345
        assert ctx["total_turns"] == 5


# ---------------- 回归：字段名与 V1 内联保持一致 ----------------

class TestV1FieldCompatibility:
    """V1 现有 hook 消费者（HookManager / tier0/1/2/3 dispatcher）依赖的字段名
    不能因 builder 抽取而改变。这些测试锁定字段名。
    """

    def test_pre_tool_use_field_names(self):
        ctx = build_pre_tool_use_context(
            tool_name="t",
            tool_input={},
            agent_name="a",
            agent_role="r",
            session_id="s",
            app_code="ac",
        )
        # V1 inline code (tool_action.py:1334-1341) 用的字段名
        assert set(ctx.keys()) == {
            "tool_name",
            "tool_input",
            "agent_name",
            "agent_role",
            "session_id",
            "app_code",
        }

    def test_post_tool_use_field_names(self):
        ctx = build_post_tool_use_context(
            tool_name="t",
            tool_input={},
            tool_response="r",
            success=True,
            agent_name="a",
            agent_role="r",
            session_id="s",
            app_code="ac",
        )
        # V1 inline code (tool_action.py:1365-1374) 用的字段名
        assert set(ctx.keys()) == {
            "tool_name",
            "tool_input",
            "tool_response",
            "success",
            "agent_name",
            "agent_role",
            "session_id",
            "app_code",
        }

    def test_turn_complete_field_names_with_extra_success(self):
        """V1 inline 把 success 放顶层，builder 通过 extra= 注入保持兼容。"""
        ctx = build_turn_complete_context(
            agent_name="a",
            agent_role="r",
            session_id="s",
            app_code="ac",
            user_id="u",
            user_name="un",
            round_index=1,
            user_prompt="q",
            final_answer="a",
            interrupted=False,
            extra={"success": True},
        )
        # V1 inline code (base_agent.py:1290-1318) 用的字段名
        assert set(ctx.keys()) == {
            "agent_name",
            "agent_role",
            "session_id",
            "app_code",
            "user_id",
            "user_name",
            "round",
            "user_prompt",
            "final_answer",
            "interrupted",
            "success",
        }

    def test_conversation_complete_field_names(self):
        ctx = build_conversation_complete_context(
            agent_name="a",
            agent_role="r",
            session_id="s",
            app_code="ac",
            final_answer="fa",
            success=True,
        )
        # V1 inline code (react_master_agent.py:2428-2449) 用的字段名
        assert set(ctx.keys()) == {
            "agent_name",
            "agent_role",
            "session_id",
            "app_code",
            "final_answer",
            "success",
        }
