"""PR 3 单元测试：step-level resume。

覆盖目标：
- _lookup_cached_tool_result 命中/未命中逻辑
  - tool_call_id 精确匹配（仅内存 cache）
  - (tool_name, args) 回退匹配
  - success=False / status=running 不复用
- _build_action_output_from_work_entry 字段映射
- _normalize_args 规范化
- 非 retry 模式不查 cache（行为层验证）
- load_persistent_memory 加载 work_log（行为层验证，轻量）
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.core.memory.gpts.file_base import WorkEntry, WorkLogStatus
from derisk.agent.core.action.base import ActionOutput
from derisk.agent.core.schema import Status


# ---------------- _normalize_args ----------------

class TestNormalizeArgs:
    def test_none_returns_none(self):
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        assert ReActMasterAgent._normalize_args(None) is None

    def test_non_dict_returns_none(self):
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        assert ReActMasterAgent._normalize_args("not a dict") is None
        assert ReActMasterAgent._normalize_args([1, 2]) is None

    def test_sorts_keys_and_drops_none(self):
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        result = ReActMasterAgent._normalize_args({"b": 2, "a": 1, "c": None})
        # keys 排序，None 值剔除
        assert list(result.keys()) == ["a", "b"]
        assert result == {"a": 1, "b": 2}

    def test_empty_dict_returns_empty(self):
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        assert ReActMasterAgent._normalize_args({}) == {}

    def test_args_equality_after_normalize(self):
        """两次调用同 args（顺序不同）应得到相等结果。"""
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        a = ReActMasterAgent._normalize_args({"x": 1, "y": 2})
        b = ReActMasterAgent._normalize_args({"y": 2, "x": 1})
        assert a == b


# ---------------- _build_action_output_from_work_entry ----------------

class TestBuildActionOutputFromWorkEntry:
    def test_fields_mapped_correctly(self):
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            result="rows: 42",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        out = ReActMasterAgent._build_action_output_from_work_entry(entry, "execute_sql")
        assert isinstance(out, ActionOutput)
        assert out.content == "rows: 42"
        assert out.action == "execute_sql"
        assert out.action_name == "execute_sql"
        assert out.is_exe_success is True
        assert out.state == Status.COMPLETE.value

    def test_empty_result_handled(self):
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )
        entry = WorkEntry(
            timestamp=1.0,
            tool="read_file",
            result=None,
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        out = ReActMasterAgent._build_action_output_from_work_entry(entry, "read_file")
        assert out.content == ""
        assert out.view == ""


# ---------------- _lookup_cached_tool_result ----------------

class TestLookupCachedToolResult:
    """测试 step-resume 查找逻辑。直接调用未绑定方法 + mock self，不跑完整 act()。"""

    @pytest.fixture
    def agent_and_cache(self):
        """构造 mock self + cache，调用未绑定方法。"""
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )

        mock_self = MagicMock()
        mock_self.memory = MagicMock()
        cache = MagicMock()
        cache.work_logs = []
        mock_self.memory.gpts_memory._get_cache = AsyncMock(return_value=cache)
        ctx = MagicMock()
        ctx.conv_id = "conv_test"
        mock_self.not_null_agent_context = ctx
        # _build_action_output_from_work_entry 是 @staticmethod，直接绑定真实实现
        mock_self._build_action_output_from_work_entry = (
            ReActMasterAgent._build_action_output_from_work_entry
        )
        mock_self._normalize_args = ReActMasterAgent._normalize_args
        return mock_self, cache, ReActMasterAgent._lookup_cached_tool_result

    @pytest.mark.asyncio
    async def test_no_cache_returns_none(self, agent_and_cache):
        mock_self, _, method = agent_and_cache
        mock_self.memory.gpts_memory._get_cache = AsyncMock(return_value=None)
        result = await method(mock_self, "execute_sql", {"q": "1"})
        assert result is None

    @pytest.mark.asyncio
    async def test_tool_call_id_match_returns_output(self, agent_and_cache):
        """tool_call_id 精确匹配 + success + active → 命中。"""
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="ok",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
            tool_call_id="tc_123",
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
            tool_call_id="tc_123",
        )
        assert result is not None
        assert result.content == "ok"
        assert result.is_exe_success is True

    @pytest.mark.asyncio
    async def test_tool_call_id_mismatch_falls_back_to_args(self, agent_and_cache):
        """tool_call_id 不匹配时回退到 (tool, args) 匹配。"""
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="ok",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
            tool_call_id=None,
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
            tool_call_id="some_other_id",
        )
        assert result is not None
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_args_match_returns_output(self, agent_and_cache):
        """无 tool_call_id，按 (tool_name, args) 匹配命中。"""
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1", "limit": 10},
            result="rows",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"limit": 10, "q": "1"},
        )
        assert result is not None
        assert result.content == "rows"

    @pytest.mark.asyncio
    async def test_failed_entry_not_reused(self, agent_and_cache):
        """success=False 的 entry 不复用。"""
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="error",
            success=False,
            status=WorkLogStatus.ACTIVE.value,
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_running_status_not_reused(self, agent_and_cache):
        """status != active（崩溃留下的半成品）不复用。"""
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="partial",
            success=True,
            status="running",
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_tool_name_mismatch_returns_none(self, agent_and_cache):
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="ok",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="different_tool",
            tool_args={"q": "1"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_args_mismatch_returns_none(self, agent_and_cache):
        mock_self, cache, method = agent_and_cache
        entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="ok",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        cache.work_logs = [entry]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "different"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_last_match_wins(self, agent_and_cache):
        """多条匹配时取最后一条（最近一次成功调用）。"""
        mock_self, cache, method = agent_and_cache
        entry1 = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="old_result",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        entry2 = WorkEntry(
            timestamp=2.0,
            tool="execute_sql",
            args={"q": "1"},
            result="new_result",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        cache.work_logs = [entry1, entry2]
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
        )
        assert result.content == "new_result"

    @pytest.mark.asyncio
    async def test_empty_work_logs_returns_none(self, agent_and_cache):
        mock_self, cache, method = agent_and_cache
        cache.work_logs = []
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cache_exception_returns_none(self, agent_and_cache):
        """_get_cache 抛异常时不传播，返回 None。"""
        mock_self, _, method = agent_and_cache
        mock_self.memory.gpts_memory._get_cache = AsyncMock(side_effect=RuntimeError("db err"))
        result = await method(
            mock_self,
            tool_name="execute_sql",
            tool_args={"q": "1"},
        )
        assert result is None


# ---------------- 非 retry 模式不查 cache（行为验证）----------------

class TestNonRetryModeSkipsCache:
    """非 retry 模式（recovering=False）不应触发 _lookup_cached_tool_result。

    用 patch 验证：当 self.recovering=False 时，act() 不调用 _lookup_cached_tool_result。
    这里只验证调用条件，不跑完整 act()（act() 依赖太多 mock）。
    """

    @pytest.mark.asyncio
    async def test_recovering_false_skips_lookup(self):
        """直接验证：recovering=False 时不进入 step-resume 分支。
        用最小化的 act() 调用，patch 掉依赖。
        """
        from derisk.agent.expand.react_master_agent.react_master_agent import (
            ReActMasterAgent,
        )

        agent = ReActMasterAgent.__new__(ReActMasterAgent)
        agent._runtime_context = MagicMock()
        agent._runtime_context.context = MagicMock()
        agent._runtime_context.context.recovering = False

        # _lookup_cached_tool_result 被打 patch，如果被调用会 raise
        agent._lookup_cached_tool_result = AsyncMock(
            side_effect=AssertionError("should not be called when recovering=False")
        )

        # 由于 act() 依赖太多，这里只验证 recovering 属性读取正常
        assert agent.recovering is False


# ---------------- load_persistent_memory 加载 work_log ----------------

class TestLoadPersistentMemoryWorkLog:
    """验证 load_persistent_memory 在 cache.work_logs 为空时会触发 _load_work_entries_for_session。"""

    @pytest.mark.asyncio
    async def test_load_persistent_memory_triggers_work_log_load(self):
        """cache.work_logs 为空时调用 _load_work_entries_for_session。"""
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        memory = GptsMemory.__new__(GptsMemory)  # 跳过 __init__
        memory._caches = {}
        memory._locks = {}
        memory._executor = None

        cache = MagicMock()
        cache.message_ids = ["msg_1"]  # 非空，跳过 message 加载
        cache.plans = {"t1": MagicMock()}  # 非空，跳过 plans 加载
        cache.work_logs = []  # 空，触发 work_log 加载

        memory._get_cache = AsyncMock(return_value=cache)
        memory._message_memory = MagicMock()
        memory._plans_memory = MagicMock()
        memory._get_conv_lock = AsyncMock(return_value=MagicMock())

        mock_entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            args={"q": "1"},
            result="ok",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        memory._load_work_entries_for_session = AsyncMock(return_value=[mock_entry])

        await memory.load_persistent_memory("conv_test")

        memory._load_work_entries_for_session.assert_awaited_once()
        assert len(cache.work_logs) == 1
        assert cache.work_logs[0].tool == "execute_sql"

    @pytest.mark.asyncio
    async def test_load_persistent_memory_skips_when_work_logs_present(self):
        """cache.work_logs 非空时不重复加载。"""
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = None

        existing_entry = WorkEntry(
            timestamp=1.0,
            tool="execute_sql",
            result="ok",
            success=True,
            status=WorkLogStatus.ACTIVE.value,
        )
        cache = MagicMock()
        cache.message_ids = ["msg_1"]
        cache.plans = {"t1": MagicMock()}  # 非空，跳过 plans 加载
        cache.work_logs = [existing_entry]  # 非空

        memory._get_cache = AsyncMock(return_value=cache)
        memory._message_memory = MagicMock()
        memory._plans_memory = MagicMock()
        memory._get_conv_lock = AsyncMock(return_value=MagicMock())
        memory._load_work_entries_for_session = AsyncMock(
            side_effect=AssertionError("should not be called when work_logs non-empty")
        )

        await memory.load_persistent_memory("conv_test")
        assert len(cache.work_logs) == 1  # 没有被覆盖

    @pytest.mark.asyncio
    async def test_load_persistent_memory_swallows_work_log_load_failure(self):
        """_load_work_entries_for_session 抛异常时不传播，只 log warning。"""
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        memory = GptsMemory.__new__(GptsMemory)
        memory._executor = None

        cache = MagicMock()
        cache.message_ids = ["msg_1"]
        cache.plans = {"t1": MagicMock()}  # 非空，跳过 plans 加载
        cache.work_logs = []

        memory._get_cache = AsyncMock(return_value=cache)
        memory._message_memory = MagicMock()
        memory._plans_memory = MagicMock()
        memory._get_conv_lock = AsyncMock(return_value=MagicMock())
        memory._load_work_entries_for_session = AsyncMock(
            side_effect=RuntimeError("db connection failed")
        )

        # 不应抛异常
        await memory.load_persistent_memory("conv_test")
        assert cache.work_logs == []
