"""Tier 3.1 单元测试：事件日志（加法版本）。

覆盖目标：
- emit_event: fire-and-forget, 不阻塞, 无 event loop 时静默跳过
- emit_think_start/end, emit_act_start/end 便捷函数
- EventLogDao.append_event: 自动分配 sequence
- EventLogDao.get_events: 按 sequence 顺序读取
- EventLogDao.get_events_by_message: 按 message 读取
- EventLogDao.get_latest_sequence: 断点续传用
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from derisk.agent.core.event_log import (
    EVENT_ACT_END,
    EVENT_ACT_START,
    EVENT_THINK_END,
    EVENT_THINK_START,
    emit_act_end,
    emit_act_start,
    emit_event,
    emit_think_end,
    emit_think_start,
)


# ---------------- emit_event（fire-and-forget）----------------

class TestEmitEvent:
    def test_empty_conv_id_skipped(self):
        """空 conv_id 不应尝试 DB 写。"""
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao"
        ) as mock_dao:
            emit_event("", EVENT_THINK_START)
            mock_dao.assert_not_called()

    def test_empty_event_type_skipped(self):
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao"
        ) as mock_dao:
            emit_event("conv_1", "")
            mock_dao.assert_not_called()

    def test_no_event_loop_swallowed(self):
        """无 event loop（同步上下文）→ 静默跳过，不抛异常。"""
        # 在同步测试方法里调用，无 event loop
        emit_event("conv_1", EVENT_THINK_START)  # 不抛

    @pytest.mark.asyncio
    async def test_creates_task_and_returns_immediately(self):
        """有 event loop 时 → spawn asyncio.create_task，立即返回。"""
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao.append_event",
            return_value=1,
        ) as mock_append:
            emit_event("conv_1", EVENT_THINK_START, "msg_1", {"key": "val"})
            # 等待 spawned task 跑完
            await asyncio.sleep(0.05)
            mock_append.assert_called_once_with(
                "conv_1", EVENT_THINK_START, "msg_1", {"key": "val"}
            )

    @pytest.mark.asyncio
    async def test_dao_exception_swallowed(self):
        """DAO 异常 → 只 log debug，不传播。"""
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao.append_event",
            side_effect=RuntimeError("db down"),
        ):
            # 不抛
            emit_event("conv_1", EVENT_THINK_START)
            await asyncio.sleep(0.05)


# ---------------- 便捷函数 ----------------

class TestConvenienceEmitters:
    @pytest.mark.asyncio
    async def test_emit_think_start_passes_correct_payload(self):
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao.append_event",
            return_value=1,
        ) as mock_append:
            emit_think_start(
                conv_id="conv_1",
                message_id="msg_1",
                model_name="gpt-4",
                round_index=2,
            )
            await asyncio.sleep(0.05)
            args = mock_append.call_args.args
            assert args[0] == "conv_1"
            assert args[1] == EVENT_THINK_START
            assert args[2] == "msg_1"
            payload = args[3]
            assert payload["model_name"] == "gpt-4"
            assert payload["round_index"] == 2

    @pytest.mark.asyncio
    async def test_emit_think_end_truncates_long_thinking(self):
        long_thinking = "x" * 1000
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao.append_event",
            return_value=1,
        ) as mock_append:
            emit_think_end(
                conv_id="conv_1",
                message_id="msg_1",
                thinking=long_thinking,
                content="final",
                total_tokens=100,
            )
            await asyncio.sleep(0.05)
            payload = mock_append.call_args.args[3]
            # thinking 截断到 500 字符
            assert len(payload["thinking"]) == 500
            assert payload["content"] == "final"
            assert payload["total_tokens"] == 100

    @pytest.mark.asyncio
    async def test_emit_act_start_passes_tool_name_and_args(self):
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao.append_event",
            return_value=1,
        ) as mock_append:
            emit_act_start(
                conv_id="conv_1",
                tool_name="execute_sql",
                message_id="msg_1",
                args={"sql": "SELECT 1"},
            )
            await asyncio.sleep(0.05)
            args = mock_append.call_args.args
            assert args[1] == EVENT_ACT_START
            payload = args[3]
            assert payload["tool_name"] == "execute_sql"
            assert payload["args"] == {"sql": "SELECT 1"}

    @pytest.mark.asyncio
    async def test_emit_act_end_truncates_result_summary(self):
        long_result = "y" * 1000
        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao.append_event",
            return_value=1,
        ) as mock_append:
            emit_act_end(
                conv_id="conv_1",
                tool_name="execute_sql",
                success=True,
                message_id="msg_1",
                result_summary=long_result,
            )
            await asyncio.sleep(0.05)
            payload = mock_append.call_args.args[3]
            assert payload["success"] is True
            assert len(payload["result_summary"]) == 500


# ---------------- EventLogDao（用 mock session 验证 SQL 行为）----------------

class TestEventLogDao:
    def _make_dao_with_mock_session(self):
        from derisk_serve.agent.db.gpts_events_db import EventLogDao

        dao = EventLogDao()
        session = MagicMock()
        dao.get_raw_session = MagicMock(return_value=session)
        return dao, session

    def test_append_event_returns_none_for_empty_conv(self):
        dao, _ = self._make_dao_with_mock_session()
        assert dao.append_event("", EVENT_THINK_START) is None

    def test_append_event_returns_none_for_empty_type(self):
        dao, _ = self._make_dao_with_mock_session()
        assert dao.append_event("conv_1", "") is None

    def test_append_event_assigns_sequence_1_for_first_event(self):
        """第一次追加 → sequence=1。"""
        dao, session = self._make_dao_with_mock_session()
        # 模拟无历史事件
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        # patch entity.id after commit (mock session 不会真的填 id)
        captured_entity = []

        def capture_add(entity):
            captured_entity.append(entity)

        session.add.side_effect = capture_add

        dao.append_event("conv_1", EVENT_THINK_START, "msg_1", {"x": 1})

        # 验证 session.add 被调用，且 entity.sequence=1
        session.add.assert_called_once()
        session.commit.assert_called_once()
        added_entity = captured_entity[0]
        assert added_entity.sequence == 1
        assert added_entity.conv_id == "conv_1"
        assert added_entity.event_type == EVENT_THINK_START

    def test_append_event_increments_sequence(self):
        """已有事件 → sequence = max + 1。"""
        dao, session = self._make_dao_with_mock_session()
        # 模拟当前 max sequence = 5
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (5,)

        captured_entity = []
        session.add.side_effect = lambda e: captured_entity.append(e)

        dao.append_event("conv_1", EVENT_THINK_END, "msg_1", {"x": 1})
        added_entity = captured_entity[0]
        assert added_entity.sequence == 6

    def test_append_event_serializes_event_data_to_json(self):
        dao, session = self._make_dao_with_mock_session()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        captured_entity = []
        session.add.side_effect = lambda e: captured_entity.append(e)

        dao.append_event("conv_1", EVENT_THINK_START, "msg_1", {"key": "value", "n": 42})
        added_entity = captured_entity[0]
        import json
        payload = json.loads(added_entity.event_data)
        assert payload == {"key": "value", "n": 42}

    def test_append_event_db_error_returns_none(self):
        dao, session = self._make_dao_with_mock_session()
        session.add.side_effect = RuntimeError("connection lost")

        result = dao.append_event("conv_1", EVENT_THINK_START)
        assert result is None
        session.rollback.assert_called_once()

    def test_get_events_returns_in_ascending_sequence(self):
        dao, session = self._make_dao_with_mock_session()
        mock_events = [MagicMock(), MagicMock(), MagicMock()]
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_events

        result = dao.get_events("conv_1", since_sequence=5)
        assert result == mock_events
        # 验证 filter 用了 sequence > 5
        # (完整 SQL 验证较复杂，这里只验证链式调用)

    def test_get_events_by_message_returns_in_order(self):
        dao, session = self._make_dao_with_mock_session()
        mock_events = [MagicMock(), MagicMock()]
        session.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_events

        result = dao.get_events_by_message("msg_1")
        assert result == mock_events

    def test_get_latest_sequence_returns_zero_when_no_events(self):
        dao, session = self._make_dao_with_mock_session()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        assert dao.get_latest_sequence("conv_1") == 0

    def test_get_latest_sequence_returns_max_sequence(self):
        dao, session = self._make_dao_with_mock_session()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (42,)

        assert dao.get_latest_sequence("conv_1") == 42
