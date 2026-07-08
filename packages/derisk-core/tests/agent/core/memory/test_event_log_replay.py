"""Tier 3.1 + Gap #181: 事件日志 replay 测试。

覆盖：
- load_persistent_memory(replay_events=True) 把 gpts_events 加载到 cache.events
- load_event_log 公开接口按 sequence 升序返回事件
- derisk_serve 不可用时 graceful degrade（返回 []）
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLoadEventLog:
    """load_event_log 公开接口。"""

    @pytest.mark.asyncio
    async def test_load_event_log_returns_events_in_order(self):
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = MagicMock()

        mock_events = [MagicMock(sequence=1), MagicMock(sequence=2), MagicMock(sequence=3)]

        with patch(
            "derisk_serve.agent.db.gpts_events_db.EventLogDao"
        ) as mock_dao_cls:
            mock_dao = MagicMock()
            mock_dao.get_events = MagicMock(return_value=mock_events)
            mock_dao_cls.return_value = mock_dao

            # blocking_func_to_async 调用 executor.submit，直接 patch 它
            with patch(
                "derisk.agent.core.memory.gpts.gpts_memory.blocking_func_to_async",
                new=AsyncMock(return_value=mock_events),
            ):
                result = await memory.load_event_log("conv_1", since_sequence=0)

            assert result == mock_events

    @pytest.mark.asyncio
    async def test_load_event_log_returns_empty_when_derisk_serve_unavailable(self):
        """derisk_serve import 失败 → 返回 []（不抛错）。"""
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = MagicMock()

        # 模拟 import 失败
        import sys
        original_module = sys.modules.get("derisk_serve.agent.db.gpts_events_db")
        sys.modules["derisk_serve.agent.db.gpts_events_db"] = None  # type: ignore

        try:
            result = await memory.load_event_log("conv_1")
            assert result == []
        finally:
            if original_module is not None:
                sys.modules["derisk_serve.agent.db.gpts_events_db"] = original_module
            else:
                del sys.modules["derisk_serve.agent.db.gpts_events_db"]


class TestLoadPersistentMemoryWithEvents:
    """load_persistent_memory(replay_events=True) 把事件加载到 cache.events。"""

    @pytest.mark.asyncio
    async def test_load_persistent_memory_loads_events_when_replay_true(self):
        """replay_events=True → cache.events 被填充。"""
        from derisk.agent.core.memory.gpts.gpts_memory import (
            ConversationCache,
            GptsMemory,
        )

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = MagicMock()

        # mock cache
        vis = MagicMock()
        cache = ConversationCache(conv_id="conv_1", vis_converter=vis)
        # 让所有"已加载"判断为 False，触发加载分支
        cache.message_ids = []
        cache.plans = {}
        cache.work_logs = []
        cache.events = []

        async def mock_get_cache(conv_id):
            return cache

        memory._get_cache = mock_get_cache

        # mock 所有加载方法
        memory._message_memory = MagicMock()
        memory._message_memory.get_by_conv_id = AsyncMock(return_value=[])

        memory._plans_memory = MagicMock()
        memory._plans_memory.get_by_conv_id = AsyncMock(return_value=[])

        memory._load_work_entries_for_session = AsyncMock(return_value=[])

        # mock _load_event_log 返回 3 个事件
        mock_events = [MagicMock(sequence=1), MagicMock(sequence=2), MagicMock(sequence=3)]
        memory._load_event_log = AsyncMock(return_value=mock_events)

        # mock lock
        class _MockLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        async def mock_get_lock(conv_id):
            return _MockLock()

        memory._get_conv_lock = mock_get_lock
        memory._cache_messages = AsyncMock()

        await memory.load_persistent_memory("conv_1", replay_events=True)

        assert cache.events == mock_events

    @pytest.mark.asyncio
    async def test_load_persistent_memory_skips_events_when_replay_false(self):
        """replay_events=False（默认）→ cache.events 不被加载。"""
        from derisk.agent.core.memory.gpts.gpts_memory import (
            ConversationCache,
            GptsMemory,
        )

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = MagicMock()

        vis = MagicMock()
        cache = ConversationCache(conv_id="conv_2", vis_converter=vis)
        cache.message_ids = ["existing_msg"]  # 已有消息，跳过 messages 加载
        cache.plans = {"existing_plan": MagicMock()}  # 跳过 plans
        cache.work_logs = []  # 进入 work_log 加载分支
        cache.events = []

        async def mock_get_cache(conv_id):
            return cache

        memory._get_cache = mock_get_cache
        memory._load_work_entries_for_session = AsyncMock(return_value=[])
        memory._load_event_log = AsyncMock(return_value=[MagicMock()])

        class _MockLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        async def mock_get_lock(conv_id):
            return _MockLock()

        memory._get_conv_lock = mock_get_lock

        await memory.load_persistent_memory("conv_2", replay_events=False)

        # events 不应被加载
        assert cache.events == []
        memory._load_event_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_load_persistent_memory_event_load_failure_does_not_raise(self):
        """事件加载抛异常 → 只 log warning，不影响主流程。"""
        from derisk.agent.core.memory.gpts.gpts_memory import (
            ConversationCache,
            GptsMemory,
        )

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = MagicMock()

        vis = MagicMock()
        cache = ConversationCache(conv_id="conv_3", vis_converter=vis)
        cache.message_ids = ["x"]  # 跳过 messages
        cache.plans = {"x": MagicMock()}  # 跳过 plans
        cache.work_logs = [MagicMock()]  # 跳过 work_log
        cache.events = []

        async def mock_get_cache(conv_id):
            return cache

        memory._get_cache = mock_get_cache
        memory._load_event_log = AsyncMock(side_effect=RuntimeError("db down"))

        class _MockLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        async def mock_get_lock(conv_id):
            return _MockLock()

        memory._get_conv_lock = mock_get_lock

        # 不抛
        await memory.load_persistent_memory("conv_3", replay_events=True)
        # events 仍为空
        assert cache.events == []


class TestConversationCacheEventsField:
    """ConversationCache.events 字段。"""

    def test_events_initialized_empty(self):
        from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache

        cache = ConversationCache(conv_id="c", vis_converter=MagicMock())
        assert cache.events == []

    def test_clear_empties_events(self):
        from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache

        cache = ConversationCache(conv_id="c", vis_converter=MagicMock())
        cache.events.append(MagicMock())
        cache.events.append(MagicMock())
        assert len(cache.events) == 2

        cache.clear()
        assert cache.events == []
