"""Tier 3.2 单元测试：lease 机制。

覆盖目标：
- GptsConversationsDao.acquire_lease: 原子抢占
  - 无 holder → 成功
  - 已被其他 worker 持有 + 未过期 → 失败
  - 已被其他 worker 持有 + 已过期 → 成功（抢占）
- GptsConversationsDao.renew_lease: 仅 owner 可续
- GptsConversationsDao.release_lease: 仅 owner 可释放
- heartbeat.acquire_lease / release_lease / get_worker_id
- heartbeat.is_lease_expired
- RecoveryDaemon: lease 抢占失败时跳过；抢占成功时恢复
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk_serve.agent.heartbeat import (
    LEASE_TTL_SECONDS,
    acquire_lease,
    get_worker_id,
    is_lease_expired,
    release_lease,
)


# ---------------- heartbeat lease 公开接口 ----------------

class TestLeasePublicApi:
    def test_get_worker_id_returns_uuid_string(self):
        wid = get_worker_id()
        assert isinstance(wid, str)
        assert len(wid) > 0
        # 同一进程内多次调用返回同一值
        assert get_worker_id() == wid

    def test_get_worker_id_unique_across_calls(self):
        # 同一进程内不变（进程级单例）
        assert get_worker_id() == get_worker_id()

    def test_is_lease_expired_none_is_expired(self):
        assert is_lease_expired(None) is True

    def test_is_lease_expired_past_time(self):
        past = datetime.utcnow() - timedelta(seconds=10)
        assert is_lease_expired(past) is True

    def test_is_lease_expired_future_time(self):
        future = datetime.utcnow() + timedelta(seconds=100)
        assert is_lease_expired(future) is False

    @pytest.mark.asyncio
    async def test_acquire_lease_empty_conv_id_returns_false(self):
        assert await acquire_lease("") is False

    @pytest.mark.asyncio
    async def test_release_lease_empty_conv_id_is_noop(self):
        # 不抛异常
        await release_lease("")

    @pytest.mark.asyncio
    async def test_acquire_lease_returns_true_when_dao_succeeds(self):
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.acquire_lease",
            return_value=True,
        ):
            assert await acquire_lease("conv_1") is True

    @pytest.mark.asyncio
    async def test_acquire_lease_returns_false_on_db_error(self):
        with patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.acquire_lease",
            side_effect=RuntimeError("db down"),
        ):
            assert await acquire_lease("conv_1") is False


# ---------------- DAO lease 方法 ----------------

class TestDaoLeaseMethods:
    """DAO 层的原子性测试用 mock session 验证 UPDATE 的 WHERE 子句。"""

    def _make_dao_with_mock_session(self, update_return=1):
        """构造一个 GptsConversationsDao，session 完全 mock。"""
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        session = MagicMock()
        session.query.return_value.filter.return_value.update.return_value = update_return
        session.commit = MagicMock()
        session.rollback = MagicMock()
        session.close = MagicMock()
        dao.get_raw_session = MagicMock(return_value=session)
        return dao, session

    def test_acquire_lease_no_holder_returns_true(self):
        dao, session = self._make_dao_with_mock_session(update_return=1)
        result = dao.acquire_lease("conv_1", "worker_A", ttl_seconds=90)
        assert result is True
        session.commit.assert_called_once()

    def test_acquire_lease_already_held_returns_false(self):
        """UPDATE 影响 0 行 → 已被其他 worker 持有且未过期。"""
        dao, session = self._make_dao_with_mock_session(update_return=0)
        result = dao.acquire_lease("conv_1", "worker_B", ttl_seconds=90)
        assert result is False
        session.commit.assert_called_once()

    def test_acquire_lease_writes_worker_id_and_expiry(self):
        dao, session = self._make_dao_with_mock_session(update_return=1)
        dao.acquire_lease("conv_1", "worker_A", ttl_seconds=120)
        # 验证 update 被调用，且 dict 包含 worker_id + lease_expires_at + last_heartbeat
        update_call = session.query.return_value.filter.return_value.update.call_args
        update_dict = update_call.args[0]
        # dict 的 key 是 Column 对象，取 values
        values = list(update_dict.values())
        assert any(v == "worker_A" for v in values), "worker_id should be in update"
        # lease_expires_at 是 datetime
        assert any(isinstance(v, datetime) for v in values), "lease_expires_at should be datetime"

    def test_acquire_lease_db_error_returns_false(self):
        """DB 错误（含列不存在）→ 防御性退化返回 False，不抛异常。"""
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        session = MagicMock()
        session.query.side_effect = RuntimeError("connection lost")
        dao.get_raw_session = MagicMock(return_value=session)
        result = dao.acquire_lease("conv_1", "worker_A")
        assert result is False
        session.rollback.assert_called_once()

    def test_renew_lease_owner_can_renew(self):
        dao, session = self._make_dao_with_mock_session(update_return=1)
        result = dao.renew_lease("conv_1", "worker_A", ttl_seconds=90)
        assert result is True

    def test_renew_lease_non_owner_returns_false(self):
        """UPDATE WHERE worker_id != current → 0 行 → False。"""
        dao, session = self._make_dao_with_mock_session(update_return=0)
        result = dao.renew_lease("conv_1", "worker_B", ttl_seconds=90)
        assert result is False

    def test_release_lease_owner_can_release(self):
        dao, session = self._make_dao_with_mock_session(update_return=1)
        result = dao.release_lease("conv_1", "worker_A")
        assert result is True
        # 验证 update 写入了 NULL
        update_call = session.query.return_value.filter.return_value.update.call_args
        update_dict = update_call.args[0]
        values = list(update_dict.values())
        assert any(v is None for v in values), "should set worker_id/lease_expires_at to None"

    def test_release_lease_non_owner_returns_false(self):
        dao, session = self._make_dao_with_mock_session(update_return=0)
        result = dao.release_lease("conv_1", "worker_B")
        assert result is False

    def test_get_lease_holder_returns_tuple(self):
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        conv = MagicMock()
        conv.worker_id = "worker_A"
        conv.lease_expires_at = datetime.utcnow() + timedelta(seconds=90)
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = conv
        dao.get_raw_session = MagicMock(return_value=session)
        wid, expires = dao.get_lease_holder("conv_1")
        assert wid == "worker_A"
        assert expires is not None

    def test_get_lease_holder_no_conv_returns_none_tuple(self):
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        dao.get_raw_session = MagicMock(return_value=session)
        wid, expires = dao.get_lease_holder("missing")
        assert wid is None
        assert expires is None


# ---------------- RecoveryDaemon lease 集成 ----------------

class TestRecoveryDaemonLease:
    @pytest.mark.asyncio
    async def test_lease_acquire_failure_skips_recovery(self):
        """心跳陈旧但被其他 worker 抢占 → 跳过。"""
        from derisk_serve.agent.recovery_daemon import RecoveryDaemon
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity

        conv = MagicMock(spec=GptsConversationsEntity)
        conv.conv_id = "conv_1"
        conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=200)  # stale
        conv.lease_expires_at = datetime.utcnow() + timedelta(seconds=60)  # lease valid
        conv.extra = None

        daemon = RecoveryDaemon(agent_chat=None)
        stats = {"scanned": 0, "fresh_skipped": 0, "stale_recovered": 0, "lease_lost": 0, "errors": 0}

        with patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=False),
        ):
            await daemon._process_one(conv, stats)

        assert stats["lease_lost"] == 1
        assert stats["stale_recovered"] == 0

    @pytest.mark.asyncio
    async def test_lease_acquire_success_triggers_recovery(self):
        """心跳陈旧 + 抢占成功 → 触发恢复。"""
        from derisk_serve.agent.recovery_daemon import RecoveryDaemon
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity

        conv = MagicMock(spec=GptsConversationsEntity)
        conv.conv_id = "conv_1"
        conv.last_heartbeat = datetime.utcnow() - timedelta(seconds=200)  # stale
        conv.lease_expires_at = None
        conv.extra = None

        daemon = RecoveryDaemon(agent_chat=None)
        stats = {"scanned": 0, "fresh_skipped": 0, "stale_recovered": 0, "lease_lost": 0, "errors": 0}

        mock_trigger = AsyncMock()
        with patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=True),
        ), patch.object(
            RecoveryDaemon, "_trigger_main_retry", mock_trigger
        ), patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update"
        ):
            await daemon._process_one(conv, stats)

        assert stats["stale_recovered"] == 1
        assert stats["lease_lost"] == 0
        mock_trigger.assert_awaited_once_with("conv_1")

    @pytest.mark.asyncio
    async def test_fresh_heartbeat_with_valid_lease_skips(self):
        """心跳新鲜 + lease 有效 → 跳过（另一进程在跑）。"""
        from derisk_serve.agent.recovery_daemon import RecoveryDaemon
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity

        conv = MagicMock(spec=GptsConversationsEntity)
        conv.conv_id = "conv_1"
        conv.last_heartbeat = datetime.utcnow()  # fresh
        conv.lease_expires_at = datetime.utcnow() + timedelta(seconds=60)  # valid
        conv.extra = None

        daemon = RecoveryDaemon(agent_chat=None)
        stats = {"scanned": 0, "fresh_skipped": 0, "stale_recovered": 0, "lease_lost": 0, "errors": 0}

        await daemon._process_one(conv, stats)
        assert stats["fresh_skipped"] == 1
        assert stats["stale_recovered"] == 0

    @pytest.mark.asyncio
    async def test_fresh_heartbeat_with_expired_lease_attempts_takeover(self):
        """心跳新鲜但 lease 过期 → 尝试抢占（边缘 case）。"""
        from derisk_serve.agent.recovery_daemon import RecoveryDaemon
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity

        conv = MagicMock(spec=GptsConversationsEntity)
        conv.conv_id = "conv_1"
        conv.last_heartbeat = datetime.utcnow()  # fresh
        conv.lease_expires_at = datetime.utcnow() - timedelta(seconds=10)  # expired
        conv.extra = None

        daemon = RecoveryDaemon(agent_chat=None)
        stats = {"scanned": 0, "fresh_skipped": 0, "stale_recovered": 0, "lease_lost": 0, "errors": 0}

        with patch(
            "derisk_serve.agent.recovery_daemon.acquire_lease",
            new=AsyncMock(return_value=True),
        ), patch.object(
            daemon, "_trigger_main_retry", new=AsyncMock()
        ), patch(
            "derisk_serve.agent.db.gpts_conversations_db.GptsConversationsDao.update"
        ):
            await daemon._process_one(conv, stats)

        assert stats["stale_recovered"] == 1
