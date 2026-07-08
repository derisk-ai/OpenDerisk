"""PR 4 单元测试：心跳 + 自动恢复。

覆盖目标：
- heartbeat_hook: register / touch / reset / fire-and-forget 容错
- heartbeat.is_stale: None / 新鲜 / 陈旧 / 阈值边界
- heartbeat.touch_heartbeat: 非 event loop 安全降级
- RecoveryDaemon.scan_and_recover:
  - 无 RUNNING → no-op
  - RUNNING + 心跳新鲜 → 跳过
  - RUNNING + 心跳陈旧 + 无 pending_subagents → 触发 main retry
  - RUNNING + 心跳陈旧 + 有 pending_subagents → 调 coordinator.recover_main
  - DB 异常 → stats.errors +1
- RecoveryDaemon._has_pending_subagents: extra 字段解析
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.core.heartbeat_hook import (
    register_heartbeat_callback,
    reset_heartbeat_callback,
    touch_heartbeat,
)
from derisk_serve.agent.heartbeat import (
    STALE_THRESHOLD_SECONDS,
    _update_heartbeat_safe,
    is_stale,
    touch_heartbeat as serve_touch_heartbeat,
)
from derisk_serve.agent.recovery_daemon import RecoveryDaemon


# ---------------- heartbeat_hook ----------------

class TestHeartbeatHook:
    def test_no_callback_is_noop(self):
        reset_heartbeat_callback()
        # 不抛异常
        touch_heartbeat("conv1")
        touch_heartbeat("")

    def test_callback_invoked(self):
        calls = []
        register_heartbeat_callback(lambda cid: calls.append(cid))
        touch_heartbeat("conv1")
        assert calls == ["conv1"]

    def test_empty_conv_id_skipped(self):
        calls = []
        register_heartbeat_callback(lambda cid: calls.append(cid))
        touch_heartbeat("")
        assert calls == []

    def test_callback_exception_swallowed(self):
        """callback 抛异常时 fire-and-forget，不传播。"""
        def err_cb(cid):
            raise RuntimeError("db down")
        register_heartbeat_callback(err_cb)
        # 不抛
        touch_heartbeat("conv1")

    def test_reset_clears_callback(self):
        calls = []
        register_heartbeat_callback(lambda cid: calls.append(cid))
        reset_heartbeat_callback()
        touch_heartbeat("conv1")
        assert calls == []


# ---------------- heartbeat.is_stale ----------------

class TestIsStale:
    def test_none_is_stale(self):
        assert is_stale(None) is True

    def test_recent_not_stale(self):
        assert is_stale(datetime.utcnow()) is False

    def test_old_is_stale(self):
        old = datetime.utcnow() - timedelta(seconds=STALE_THRESHOLD_SECONDS + 10)
        assert is_stale(old) is True

    def test_boundary_just_under_threshold_not_stale(self):
        recent = datetime.utcnow() - timedelta(seconds=STALE_THRESHOLD_SECONDS - 5)
        assert is_stale(recent) is False

    def test_boundary_just_over_threshold_stale(self):
        recent = datetime.utcnow() - timedelta(seconds=STALE_THRESHOLD_SECONDS + 1)
        assert is_stale(recent) is True

    def test_custom_threshold(self):
        recent = datetime.utcnow() - timedelta(seconds=30)
        # 默认阈值（90s）下不陈旧
        assert is_stale(recent) is False
        # 自定义阈值 10s 下陈旧
        assert is_stale(recent, threshold_seconds=10) is True


# ---------------- heartbeat._update_heartbeat_safe ----------------

class TestUpdateHeartbeatSafe:
    @pytest.mark.asyncio
    async def test_dao_exception_swallowed(self):
        """_update_heartbeat_safe 捕获异常，不传播（fire-and-forget）。"""
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update_heartbeat",
            side_effect=RuntimeError("db error"),
        ), patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.renew_lease",
            return_value=False,
        ):
            # 不抛异常
            await _update_heartbeat_safe("conv1")

    @pytest.mark.asyncio
    async def test_dao_called_with_conv_id(self):
        """renew_lease 返回 False（未持有 lease）→ 退化为 update_heartbeat。"""
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update_heartbeat"
        ) as mock_update, patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.renew_lease",
            return_value=False,
        ):
            await _update_heartbeat_safe("conv1")
            mock_update.assert_called_once_with("conv1")

    @pytest.mark.asyncio
    async def test_renew_lease_success_skips_update_heartbeat(self):
        """renew_lease 成功 → 不再调用 update_heartbeat（lease 续租已包含心跳更新）。"""
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update_heartbeat"
        ) as mock_update, patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.renew_lease",
            return_value=True,
        ) as mock_renew:
            await _update_heartbeat_safe("conv1")
            mock_renew.assert_called_once()
            mock_update.assert_not_called()


# ---------------- RecoveryDaemon._has_pending_subagents ----------------

class TestHasPendingSubagents:
    def test_no_extra_returns_false(self):
        conv = MagicMock()
        conv.extra = None
        assert RecoveryDaemon._has_pending_subagents(conv) is False

    def test_empty_pending_returns_false(self):
        conv = MagicMock()
        conv.extra = json.dumps({"pending_subagents": []})
        assert RecoveryDaemon._has_pending_subagents(conv) is False

    def test_non_empty_pending_returns_true(self):
        conv = MagicMock()
        conv.extra = json.dumps({
            "pending_subagents": [{"sub_conv_id": "sub1", "mode": "async"}]
        })
        assert RecoveryDaemon._has_pending_subagents(conv) is True

    def test_dict_extra_supported(self):
        conv = MagicMock()
        conv.extra = {"pending_subagents": [{"sub_conv_id": "sub1"}]}
        assert RecoveryDaemon._has_pending_subagents(conv) is True

    def test_invalid_json_returns_false(self):
        conv = MagicMock()
        conv.extra = "not valid json {"
        assert RecoveryDaemon._has_pending_subagents(conv) is False


# ---------------- RecoveryDaemon.scan_and_recover ----------------

class TestScanAndRecover:
    @pytest.mark.asyncio
    async def test_no_running_convs_returns_zero_stats(self):
        daemon = RecoveryDaemon(agent_chat=None)
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
            return_value=[],
        ):
            stats = await daemon.scan_and_recover()
        assert stats["scanned"] == 0
        assert stats["fresh_skipped"] == 0
        assert stats["stale_recovered"] == 0
        assert stats["lease_lost"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_fresh_heartbeat_skipped(self):
        """心跳新鲜 + lease 有效 → 跳过（多进程部署场景）。"""
        daemon = RecoveryDaemon(agent_chat=None)
        conv = MagicMock()
        conv.conv_id = "conv_fresh"
        conv.last_heartbeat = datetime.utcnow()  # 新鲜
        conv.lease_expires_at = datetime.utcnow() + timedelta(seconds=60)  # 未过期
        conv.extra = None

        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
            return_value=[conv],
        ):
            stats = await daemon.scan_and_recover()

        assert stats["scanned"] == 1
        assert stats["fresh_skipped"] == 1
        assert stats["stale_recovered"] == 0

    @pytest.mark.asyncio
    async def test_stale_no_pending_triggers_main_retry(self):
        """心跳陈旧 + 无 pending_subagents + lease 抢占成功 → 触发 main retry。"""
        mock_agent_chat = MagicMock()
        mock_agent_chat.aggregation_chat = AsyncMock()
        daemon = RecoveryDaemon(agent_chat=mock_agent_chat)

        conv = MagicMock()
        conv.conv_id = "conv_stale"
        conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=200)  # 陈旧
        conv.lease_expires_at = None
        conv.extra = None

        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
            return_value=[conv],
        ), patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update"
        ), patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=True),
        ):
            stats = await daemon.scan_and_recover()

        assert stats["scanned"] == 1
        assert stats["stale_recovered"] == 1
        assert stats["fresh_skipped"] == 0
        # aggregation_chat 被调用，is_retry_chat=True
        mock_agent_chat.aggregation_chat.assert_awaited_once()
        call_kwargs = mock_agent_chat.aggregation_chat.call_args.kwargs
        assert call_kwargs["conv_id"] == "conv_stale"
        assert call_kwargs["is_retry_chat"] is True

    @pytest.mark.asyncio
    async def test_stale_with_pending_calls_coordinator_recover(self):
        """心跳陈旧 + 有 pending_subagents + lease 抢占成功 → 调 coordinator.recover_main。"""
        mock_agent_chat = MagicMock()
        mock_agent_chat.aggregation_chat = AsyncMock()
        daemon = RecoveryDaemon(agent_chat=mock_agent_chat)

        # patch coordinator.recover_main
        with patch.object(
            daemon._coordinator, "recover_main", new=AsyncMock()
        ) as mock_recover:
            conv = MagicMock()
            conv.conv_id = "conv_pending"
            conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=200)
            conv.lease_expires_at = None
            conv.extra = json.dumps({
                "pending_subagents": [{"sub_conv_id": "sub1"}]
            })

            with patch(
                "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
                return_value=[conv],
            ), patch(
                "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update"
            ), patch(
                "derisk_serve.agent.recovery_daemon.acquire_lease",
                new=AsyncMock(return_value=True),
            ):
                stats = await daemon.scan_and_recover()

        assert stats["stale_recovered"] == 1
        mock_recover.assert_awaited_once_with("conv_pending")
        # aggregation_chat 不应被调用（走 coordinator 路径）
        mock_agent_chat.aggregation_chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_query_error_counted(self):
        """get_running_convs 抛异常 → stats.errors +1。"""
        daemon = RecoveryDaemon(agent_chat=None)
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
            side_effect=RuntimeError("db down"),
        ):
            stats = await daemon.scan_and_recover()
        assert stats["errors"] == 1
        assert stats["scanned"] == 0

    @pytest.mark.asyncio
    async def test_per_conv_exception_counted(self):
        """单个 conv 处理抛异常 → stats.errors +1，继续处理其他。"""
        daemon = RecoveryDaemon(agent_chat=None)
        conv_ok = MagicMock()
        conv_ok.conv_id = "conv_ok"
        conv_ok.last_heartbeat = datetime.utcnow()  # 新鲜，正常路径
        conv_ok.lease_expires_at = datetime.utcnow() + timedelta(seconds=60)
        conv_ok.extra = None

        conv_bad = MagicMock()
        conv_bad.conv_id = "conv_bad"
        conv_bad.last_heartbeat = datetime.utcnow()
        conv_bad.lease_expires_at = datetime.utcnow() + timedelta(seconds=60)
        conv_bad.extra = None

        # 让第一个 conv 抛异常（patch is_stale 抛错），第二个正常
        call_count = [0]
        def patched_is_stale(ts, threshold_seconds=STALE_THRESHOLD_SECONDS):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("forced error")
            return False  # 第二个新鲜

        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
            return_value=[conv_bad, conv_ok],
        ), patch(
            "derisk_serve.agent.recovery_daemon.is_stale",
            side_effect=patched_is_stale,
        ):
            stats = await daemon.scan_and_recover()

        assert stats["scanned"] == 2
        assert stats["errors"] == 1
        assert stats["fresh_skipped"] == 1

    @pytest.mark.asyncio
    async def test_dry_run_no_agent_chat(self):
        """无 agent_chat（dry-run 模式）：陈旧会话只 log，不调 aggregation_chat。"""
        daemon = RecoveryDaemon(agent_chat=None)
        conv = MagicMock()
        conv.conv_id = "conv_dry"
        conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=200)
        conv.lease_expires_at = None
        conv.extra = None

        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.get_running_convs",
            return_value=[conv],
        ), patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update"
        ), patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=True),
        ):
            stats = await daemon.scan_and_recover()

        # dry-run 模式下 stale_recovered 仍计 1（_trigger_main_retry 走 dry-run 分支）
        assert stats["stale_recovered"] == 1
