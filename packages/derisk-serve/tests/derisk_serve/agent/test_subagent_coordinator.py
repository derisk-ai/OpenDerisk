"""PR 2 / Tier 1.4 单元测试：SubagentCoordinator。

覆盖目标：
- register_subagent: 写入 pending_subagents 到 gpts_conversations.extra
- on_subagent_done: 单个子完成 → 不触发；全部完成 → 触发 main resume
- on_subagent_failed: 单个失败 → 不触发；全部完成（含失败）→ 触发 main resume
- _trigger_main_resume: 调 aggregation_chat with gpts_conversations=[entity]
- recover_main: 全部完成 → 触发 resume；未完成 → 不触发
- 全局单例 set/get_subagent_coordinator
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.core.subagent_handle import (
    SubAgentHandle,
    SubAgentMode,
    SubAgentStatus,
)
from derisk_serve.agent.subagent_coordinator import (
    SubagentCoordinator,
    get_subagent_coordinator,
    set_subagent_coordinator,
)


def _make_conv(extra: dict | None = None):
    """Mock gpts_conversations entity with extra JSON field."""
    conv = MagicMock()
    conv.extra = json.dumps(extra) if extra is not None else None
    conv.conv_id = "conv_main_1"
    conv.gpts_name = "test_app"
    conv.user_code = "u1"
    conv.sys_code = "s1"
    return conv


def _make_agent_chat(conv=None):
    """Mock AgentChat with gpts_conversations DAO."""
    agent_chat = MagicMock()
    agent_chat.gpts_conversations = MagicMock()
    agent_chat.gpts_conversations.get_by_conv_id = MagicMock(return_value=conv)
    session = MagicMock()
    agent_chat.gpts_conversations.get_raw_session = MagicMock(return_value=session)
    agent_chat.aggregation_chat = AsyncMock()
    return agent_chat


def _extract_extra_from_update_call(session):
    """从 mocked session.update 调用里取出 extra JSON 字符串。

    update 调用形如: session.query(...).filter(...).update({Column.extra: <json>}, ...)
    MagicMock 下 key 是 GptsConversationsEntity.extra column 对象，所以取第一个 value。
    """
    update_call = session.query.return_value.filter.return_value.update.call_args
    extra_dict = update_call.args[0]
    # 取 dict 的唯一 value（Column.extra → json 字符串）
    return next(iter(extra_dict.values()))


# ---------------- register_subagent ----------------

class TestRegisterSubagent:
    @pytest.mark.asyncio
    async def test_register_appends_to_pending_list(self):
        conv = _make_conv(extra={})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.register_subagent(
            main_conv_id="conv_main_1",
            sub_conv_id="sub_1",
            mode=SubAgentMode.ASYNC,
        )

        # 验证 session.update 被调用，extra 里写入了 pending_subagents
        session = agent_chat.gpts_conversations.get_raw_session.return_value
        assert session.query.called
        assert session.commit.called
        extra_json = _extract_extra_from_update_call(session)
        extra = json.loads(extra_json)
        assert len(extra["pending_subagents"]) == 1
        assert extra["pending_subagents"][0]["sub_conv_id"] == "sub_1"
        assert extra["pending_subagents"][0]["mode"] == "async"
        assert extra["pending_subagents"][0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_register_preserves_existing_pending(self):
        """已存在的 pending 不应被覆盖。"""
        existing = {
            "pending_subagents": [
                SubAgentHandle(
                    sub_conv_id="sub_0",
                    main_conv_id="conv_main_1",
                    mode=SubAgentMode.ASYNC,
                    status=SubAgentStatus.RUNNING,
                ).to_dict()
            ]
        }
        conv = _make_conv(extra=existing)
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.register_subagent(
            main_conv_id="conv_main_1",
            sub_conv_id="sub_1",
            mode=SubAgentMode.ASYNC,
        )

        session = agent_chat.gpts_conversations.get_raw_session.return_value
        extra_json = _extract_extra_from_update_call(session)
        extra = json.loads(extra_json)
        assert len(extra["pending_subagents"]) == 2
        assert extra["pending_subagents"][0]["sub_conv_id"] == "sub_0"
        assert extra["pending_subagents"][1]["sub_conv_id"] == "sub_1"

    @pytest.mark.asyncio
    async def test_register_no_conv_logs_warning(self):
        """main conv 不存在时只 log warning，不抛异常。"""
        agent_chat = MagicMock()
        agent_chat.gpts_conversations.get_by_conv_id = MagicMock(return_value=None)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        # 不抛
        await coord.register_subagent(
            main_conv_id="missing",
            sub_conv_id="sub_1",
            mode=SubAgentMode.ASYNC,
        )


# ---------------- on_subagent_done ----------------

class TestOnSubagentDone:
    @pytest.mark.asyncio
    async def test_single_done_does_not_trigger_resume(self):
        """只有一个子 agent 时，done 才触发 resume（即全部完成）。"""
        conv = _make_conv(extra={"pending_subagents": [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict()
        ]})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.on_subagent_done("conv_main_1", "sub_1", "result-1")

        # 单子 agent done = 全部 done → 触发 resume
        agent_chat.aggregation_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_partial_done_does_not_trigger_resume(self):
        """多个子 agent，部分 done 不触发 resume。"""
        handles = [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
            SubAgentHandle("sub_2", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.on_subagent_done("conv_main_1", "sub_1", "result-1")

        # 只完成 1/2，不触发
        agent_chat.aggregation_chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_all_done_triggers_resume(self):
        handles = [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
            SubAgentHandle("sub_2", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.DONE, result="already").to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.on_subagent_done("conv_main_1", "sub_1", "result-1")

        agent_chat.aggregation_chat.assert_awaited_once()
        call_kwargs = agent_chat.aggregation_chat.call_args.kwargs
        assert call_kwargs["conv_id"] == "conv_main_1"
        assert call_kwargs["agent_conv_id"] == "conv_main_1"
        assert "子 agent 全部完成" in call_kwargs["user_query"]
        assert "result-1" in call_kwargs["user_query"]
        assert "already" in call_kwargs["user_query"]


# ---------------- on_subagent_failed ----------------

class TestOnSubagentFailed:
    @pytest.mark.asyncio
    async def test_all_failed_triggers_resume_with_error(self):
        handles = [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.on_subagent_failed("conv_main_1", "sub_1", "boom")

        agent_chat.aggregation_chat.assert_awaited_once()
        call_kwargs = agent_chat.aggregation_chat.call_args.kwargs
        assert "boom" in call_kwargs["user_query"]

    @pytest.mark.asyncio
    async def test_mixed_done_failed_triggers_resume(self):
        handles = [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
            SubAgentHandle("sub_2", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.DONE, result="ok").to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.on_subagent_failed("conv_main_1", "sub_1", "crashed")

        agent_chat.aggregation_chat.assert_awaited_once()
        user_query = agent_chat.aggregation_chat.call_args.kwargs["user_query"]
        assert "crashed" in user_query
        assert "ok" in user_query


# ---------------- recover_main ----------------

class TestRecoverMain:
    @pytest.mark.asyncio
    async def test_recover_no_pending_is_noop(self):
        conv = _make_conv(extra={})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.recover_main("conv_main_1")
        agent_chat.aggregation_chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_recover_all_done_triggers_resume(self):
        handles = [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.DONE, result="r1").to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.recover_main("conv_main_1")
        agent_chat.aggregation_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recover_with_pending_running_does_not_trigger(self):
        """有未完成子 agent 时不触发 resume（等子 done 时回调）。"""
        handles = [
            SubAgentHandle("sub_1", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        await coord.recover_main("conv_main_1")
        agent_chat.aggregation_chat.assert_not_awaited()


# ---------------- _rebuild_subagent_transcript (Tier 3.3) ----------------

class TestRebuildTranscript:
    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self):
        agent_chat = _make_agent_chat(_make_conv(extra={}))
        coord = SubagentCoordinator(agent_chat=agent_chat)
        with patch(
            "derisk_serve.agent.db.gpts_messages_db.GptsMessagesDao.get_by_conv_id",
            new=AsyncMock(return_value=[]),
        ):
            result = await coord._rebuild_subagent_transcript("sub_1")
        assert result == ""

    @pytest.mark.asyncio
    async def test_messages_with_thinking_extracted(self):
        """有 thinking 的消息 → 提取 thinking 摘要。"""
        msg1 = MagicMock()
        msg1.sender_name = "sub_agent"
        msg1.thinking = "I should call tool X to do Y"
        msg1.content = ""
        msg1.action_report = None

        msg2 = MagicMock()
        msg2.sender_name = "sub_agent"
        msg2.thinking = "Tool X returned result Z, now I need to summarize"
        msg2.content = "final summary"
        msg2.action_report = None

        agent_chat = _make_agent_chat(_make_conv(extra={}))
        coord = SubagentCoordinator(agent_chat=agent_chat)
        with patch(
            "derisk_serve.agent.db.gpts_messages_db.GptsMessagesDao.get_by_conv_id",
            new=AsyncMock(return_value=[msg1, msg2]),
        ):
            result = await coord._rebuild_subagent_transcript("sub_1")

        assert "I should call tool X" in result
        assert "Tool X returned result Z" in result

    @pytest.mark.asyncio
    async def test_action_report_extracted_as_tool_calls(self):
        """action_report JSON → 提取 tool 调用记录。"""
        msg = MagicMock()
        msg.sender_name = "sub_agent"
        msg.thinking = None
        msg.content = ""
        msg.action_report = json.dumps([
            {"name": "execute_sql", "is_exe_success": True, "content": "rows=42"},
            {"name": "write_file", "is_exe_success": False, "content": "permission denied"},
        ])

        agent_chat = _make_agent_chat(_make_conv(extra={}))
        coord = SubagentCoordinator(agent_chat=agent_chat)
        with patch(
            "derisk_serve.agent.db.gpts_messages_db.GptsMessagesDao.get_by_conv_id",
            new=AsyncMock(return_value=[msg]),
        ):
            result = await coord._rebuild_subagent_transcript("sub_1")

        assert "execute_sql" in result
        assert "write_file" in result
        # 成功用 ✓，失败用 ✗
        assert "✓" in result
        assert "✗" in result

    @pytest.mark.asyncio
    async def test_long_thinking_truncated(self):
        """长 thinking 截断到 200 字符。"""
        long_thinking = "x" * 500
        msg = MagicMock()
        msg.sender_name = "sub_agent"
        msg.thinking = long_thinking
        msg.content = ""
        msg.action_report = None

        agent_chat = _make_agent_chat(_make_conv(extra={}))
        coord = SubagentCoordinator(agent_chat=agent_chat)
        with patch(
            "derisk_serve.agent.db.gpts_messages_db.GptsMessagesDao.get_by_conv_id",
            new=AsyncMock(return_value=[msg]),
        ):
            result = await coord._rebuild_subagent_transcript("sub_1")

        # 200 字符 thinking 应被截断
        assert "x" * 200 in result
        assert "x" * 201 not in result

    @pytest.mark.asyncio
    async def test_dao_error_returns_empty(self):
        """DAO 异常 → 返回空字符串，不抛。"""
        agent_chat = _make_agent_chat(_make_conv(extra={}))
        coord = SubagentCoordinator(agent_chat=agent_chat)
        with patch(
            "derisk_serve.agent.db.gpts_messages_db.GptsMessagesDao.get_by_conv_id",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            result = await coord._rebuild_subagent_transcript("sub_1")
        assert result == ""

    @pytest.mark.asyncio
    async def test_failed_subagent_in_resume_uses_transcript(self):
        """_trigger_main_resume 对 FAILED 子 agent 调 transcript 重建。"""
        handles = [
            SubAgentHandle("sub_crashed", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.FAILED, error="crashed").to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        # mock transcript 重建返回非空
        with patch.object(
            coord, "_rebuild_subagent_transcript", new=AsyncMock(return_value="[sub think] partial work")
        ):
            await coord._trigger_main_resume("conv_main_1", [
                SubAgentHandle.from_dict(h) for h in handles
            ])

        # 验证 aggregation_chat 被调用，user_query 包含 transcript
        agent_chat.aggregation_chat.assert_awaited_once()
        user_query = agent_chat.aggregation_chat.call_args.kwargs["user_query"]
        assert "崩溃前部分进展" in user_query
        assert "[sub think] partial work" in user_query
        assert "crashed" in user_query


# ---------------- recover_main with lease check (Tier 3.2/3.3) ----------------

class TestRecoverMainWithLease:
    @pytest.mark.asyncio
    async def test_running_subagent_with_expired_lease_marked_failed(self):
        """recover_main 时 RUNNING 子 agent lease 过期 → 标记 FAILED → 触发 resume。"""
        handles = [
            SubAgentHandle("sub_running", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        # mock lease check: sub 的 lease 已过期
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_lease_holder",
            return_value=("worker_A", datetime.utcnow() - timedelta(seconds=10)),
        ), patch.object(
            coord, "_rebuild_subagent_transcript", new=AsyncMock(return_value="")
        ):
            await coord.recover_main("conv_main_1")

        # 验证标记 FAILED 后触发了 resume
        agent_chat.aggregation_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_running_subagent_with_valid_lease_waits(self):
        """recover_main 时 RUNNING 子 agent lease 仍新鲜 → 不触发 resume，等子完成。"""
        handles = [
            SubAgentHandle("sub_running", "conv_main_1", SubAgentMode.ASYNC,
                           SubAgentStatus.RUNNING).to_dict(),
        ]
        conv = _make_conv(extra={"pending_subagents": handles})
        agent_chat = _make_agent_chat(conv)
        coord = SubagentCoordinator(agent_chat=agent_chat)

        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_lease_holder",
            return_value=("worker_B", datetime.utcnow() + timedelta(seconds=60)),
        ):
            await coord.recover_main("conv_main_1")

        # 不应触发 resume（等子 agent 在另一进程完成）
        agent_chat.aggregation_chat.assert_not_awaited()


# ---------------- 全局单例 ----------------

class TestGlobalCoordinator:
    def test_set_and_get(self):
        original = get_subagent_coordinator()
        try:
            mock_coord = MagicMock()
            set_subagent_coordinator(mock_coord)
            assert get_subagent_coordinator() is mock_coord
        finally:
            set_subagent_coordinator(original)

    def test_set_none_clears(self):
        original = get_subagent_coordinator()
        try:
            set_subagent_coordinator(None)
            assert get_subagent_coordinator() is None
        finally:
            set_subagent_coordinator(original)
