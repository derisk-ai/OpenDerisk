"""PR 5: 权限 5 级链测试。

覆盖：
- Level 1: PermissionMode (auto/plan/manual) + is_write_category + 短路逻辑
- Level 5: PermissionCheckpointStore (save/load/replay/list/clear)
- hash_tool_input 稳定性
- 集成：InteractionAdapter.request_tool_permission 完整 5 级链
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.core.permission_checkpoint_store import (
    PermissionCheckpoint,
    PermissionCheckpointStore,
    hash_tool_input,
)
from derisk.agent.core.permission_mode import (
    PermissionMode,
    is_write_category,
    mode_short_circuits_to_allow,
    mode_short_circuits_to_ask,
    parse_permission_mode,
)
from derisk.agent.interaction.interaction_gateway import MemoryStateStore
from derisk.agent.tools.base import ToolCategory


# ---------------- Level 1: PermissionMode ----------------

class TestPermissionMode:
    def test_auto_mode_allows_all(self):
        assert mode_short_circuits_to_allow(PermissionMode.AUTO, ToolCategory.DATABASE) is True
        assert mode_short_circuits_to_allow(PermissionMode.AUTO, ToolCategory.SEARCH) is True
        assert mode_short_circuits_to_allow(PermissionMode.AUTO, None) is True

    def test_manual_mode_allows_none(self):
        assert mode_short_circuits_to_allow(PermissionMode.MANUAL, ToolCategory.DATABASE) is False
        assert mode_short_circuits_to_allow(PermissionMode.MANUAL, ToolCategory.SEARCH) is False
        assert mode_short_circuits_to_allow(PermissionMode.MANUAL, None) is False

    def test_plan_mode_allows_readonly(self):
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.SEARCH) is True
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.ANALYSIS) is True
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.UTILITY) is True
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.REASONING) is True

    def test_plan_mode_asks_write(self):
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.DATABASE) is False
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.FILE_SYSTEM) is False
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.SHELL) is False
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.CODE) is False
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, ToolCategory.NETWORK) is False

    def test_plan_mode_unknown_category_allowed(self):
        """未知分类保守放行（PLAN 模式下）。"""
        assert mode_short_circuits_to_allow(PermissionMode.PLAN, None) is True

    def test_none_mode_no_short_circuit(self):
        """None mode 不短路（向后兼容 V1 行为）。"""
        assert mode_short_circuits_to_allow(None, ToolCategory.DATABASE) is False
        assert mode_short_circuits_to_allow(None, None) is False


class TestModeShortCircuitsToAsk:
    def test_manual_asks_all(self):
        assert mode_short_circuits_to_ask(PermissionMode.MANUAL, ToolCategory.SEARCH) is True
        assert mode_short_circuits_to_ask(PermissionMode.MANUAL, ToolCategory.DATABASE) is True

    def test_plan_asks_write_only(self):
        assert mode_short_circuits_to_ask(PermissionMode.PLAN, ToolCategory.DATABASE) is True
        assert mode_short_circuits_to_ask(PermissionMode.PLAN, ToolCategory.SHELL) is True
        assert mode_short_circuits_to_ask(PermissionMode.PLAN, ToolCategory.SEARCH) is False

    def test_auto_never_asks(self):
        assert mode_short_circuits_to_ask(PermissionMode.AUTO, ToolCategory.DATABASE) is False

    def test_none_mode_never_asks(self):
        assert mode_short_circuits_to_ask(None, ToolCategory.DATABASE) is False


class TestIsWriteCategory:
    def test_write_categories(self):
        assert is_write_category(ToolCategory.FILE_SYSTEM) is True
        assert is_write_category(ToolCategory.SHELL) is True
        assert is_write_category(ToolCategory.DATABASE) is True
        assert is_write_category(ToolCategory.CODE) is True
        assert is_write_category(ToolCategory.NETWORK) is True

    def test_readonly_categories(self):
        assert is_write_category(ToolCategory.SEARCH) is False
        assert is_write_category(ToolCategory.ANALYSIS) is False
        assert is_write_category(ToolCategory.UTILITY) is False

    def test_none_is_not_write(self):
        assert is_write_category(None) is False


class TestParsePermissionMode:
    def test_string_value(self):
        assert parse_permission_mode("auto") == PermissionMode.AUTO
        assert parse_permission_mode("PLAN") == PermissionMode.PLAN
        assert parse_permission_mode("Manual") == PermissionMode.MANUAL

    def test_enum_passthrough(self):
        assert parse_permission_mode(PermissionMode.AUTO) == PermissionMode.AUTO

    def test_none_returns_none(self):
        assert parse_permission_mode(None) is None

    def test_empty_string_returns_none(self):
        assert parse_permission_mode("") is None

    def test_unknown_value_returns_none(self):
        assert parse_permission_mode("unknown") is None
        assert parse_permission_mode("foobar") is None

    def test_non_string_non_enum_returns_none(self):
        assert parse_permission_mode(123) is None
        assert parse_permission_mode([]) is None


# ---------------- hash_tool_input ----------------

class TestHashToolInput:
    def test_same_input_same_hash(self):
        h1 = hash_tool_input({"sql": "SELECT 1", "limit": 10})
        h2 = hash_tool_input({"sql": "SELECT 1", "limit": 10})
        assert h1 == h2

    def test_different_key_order_same_hash(self):
        """sorted keys 保证 key 顺序不影响 hash。"""
        h1 = hash_tool_input({"a": 1, "b": 2})
        h2 = hash_tool_input({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = hash_tool_input({"sql": "SELECT 1"})
        h2 = hash_tool_input({"sql": "SELECT 2"})
        assert h1 != h2

    def test_empty_input(self):
        assert hash_tool_input({}) == "empty"
        assert hash_tool_input(None) == "empty"

    def test_hash_is_hex_string(self):
        h = hash_tool_input({"a": 1})
        assert isinstance(h, str)
        assert all(c in "0123456789abcdef" for c in h)

    def test_non_serializable_falls_back_to_str(self):
        """不可 JSON 序列化的对象 fallback 到 str()。"""
        # set 不可 JSON 序列化
        h = hash_tool_input({"items": {1, 2, 3}})
        assert isinstance(h, str)
        assert h != "empty"


# ---------------- Level 5: PermissionCheckpointStore ----------------

class TestPermissionCheckpointStore:
    @pytest.mark.asyncio
    async def test_save_and_load(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint(
            conv_id="c1",
            tool_name="execute_sql",
            input_hash="abc123",
            decision="allow",
            reason="user approved",
        )
        cp = await store.load_checkpoint("c1", "execute_sql", "abc123")
        assert cp is not None
        assert cp.conv_id == "c1"
        assert cp.tool_name == "execute_sql"
        assert cp.input_hash == "abc123"
        assert cp.decision == "allow"
        assert cp.reason == "user approved"
        assert cp.timestamp > 0

    @pytest.mark.asyncio
    async def test_load_miss_returns_none(self):
        store = PermissionCheckpointStore()
        cp = await store.load_checkpoint("c1", "execute_sql", "not_exists")
        assert cp is None

    @pytest.mark.asyncio
    async def test_save_overwrites_same_key(self):
        """同 (conv_id, tool_name, input_hash) 覆盖。"""
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "t1", "h1", "deny")
        await store.save_checkpoint("c1", "t1", "h1", "allow")
        cp = await store.load_checkpoint("c1", "t1", "h1")
        assert cp.decision == "allow"

    @pytest.mark.asyncio
    async def test_different_conv_ids_isolated(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "t1", "h1", "allow")
        await store.save_checkpoint("c2", "t1", "h1", "deny")
        cp1 = await store.load_checkpoint("c1", "t1", "h1")
        cp2 = await store.load_checkpoint("c2", "t1", "h1")
        assert cp1.decision == "allow"
        assert cp2.decision == "deny"

    @pytest.mark.asyncio
    async def test_different_tools_isolated(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "t1", "h1", "allow")
        await store.save_checkpoint("c1", "t2", "h1", "deny")
        cp1 = await store.load_checkpoint("c1", "t1", "h1")
        cp2 = await store.load_checkpoint("c1", "t2", "h1")
        assert cp1.decision == "allow"
        assert cp2.decision == "deny"

    @pytest.mark.asyncio
    async def test_list_checkpoints(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "t1", "h1", "allow")
        await store.save_checkpoint("c1", "t2", "h2", "deny")
        cps = await store.list_checkpoints("c1")
        assert len(cps) == 2
        tool_names = {cp.tool_name for cp in cps}
        assert tool_names == {"t1", "t2"}

    @pytest.mark.asyncio
    async def test_list_empty_conv(self):
        store = PermissionCheckpointStore()
        cps = await store.list_checkpoints("nonexistent")
        assert cps == []

    @pytest.mark.asyncio
    async def test_clear_removes_all(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "t1", "h1", "allow")
        await store.save_checkpoint("c1", "t2", "h2", "deny")
        await store.clear("c1")
        cps = await store.list_checkpoints("c1")
        assert cps == []
        # 单独 load 也 miss
        assert await store.load_checkpoint("c1", "t1", "h1") is None
        assert await store.load_checkpoint("c1", "t2", "h2") is None

    @pytest.mark.asyncio
    async def test_clear_doesnt_affect_other_convs(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "t1", "h1", "allow")
        await store.save_checkpoint("c2", "t1", "h1", "deny")
        await store.clear("c1")
        assert await store.load_checkpoint("c1", "t1", "h1") is None
        assert (await store.load_checkpoint("c2", "t1", "h1")) is not None

    @pytest.mark.asyncio
    async def test_empty_conv_id_ignored(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("", "t1", "h1", "allow")
        assert await store.load_checkpoint("", "t1", "h1") is None

    @pytest.mark.asyncio
    async def test_empty_tool_name_ignored(self):
        store = PermissionCheckpointStore()
        await store.save_checkpoint("c1", "", "h1", "allow")
        assert await store.load_checkpoint("c1", "", "h1") is None


class TestPermissionCheckpointDataclass:
    def test_to_dict_and_from_dict_roundtrip(self):
        cp = PermissionCheckpoint(
            conv_id="c1",
            tool_name="t1",
            input_hash="h1",
            decision="allow",
            reason="ok",
            timestamp=12345.0,
        )
        d = cp.to_dict()
        cp2 = PermissionCheckpoint.from_dict(d)
        assert cp2 == cp

    def test_from_dict_missing_reason_defaults_none(self):
        d = {
            "conv_id": "c1",
            "tool_name": "t1",
            "input_hash": "h1",
            "decision": "deny",
        }
        cp = PermissionCheckpoint.from_dict(d)
        assert cp.reason is None
        assert cp.timestamp == 0.0


# ---------------- 集成：InteractionAdapter 5 级链 ----------------

class TestInteractionAdapter5LevelChain:
    """InteractionAdapter.request_tool_permission 完整 5 级链测试。

    由于 InteractionAdapter 依赖 InteractionGateway / RecoveryCoordinator，
    用 mock 构造轻量级测试，只验证 5 级链决策路径。
    """

    def _make_adapter(self, agent, checkpoint_store=None):
        from derisk.agent.core.interaction_adapter import InteractionAdapter
        gateway = MagicMock()
        recovery = MagicMock()
        return InteractionAdapter(
            agent=agent,
            gateway=gateway,
            recovery_coordinator=recovery,
            checkpoint_store=checkpoint_store,
        )

    def _make_agent(self, mode=None, conv_session_id="sess1"):
        """构造 mock agent，避免 pydantic 校验失败。"""
        agent = MagicMock()
        agent.name = "test_agent"  # 必须是 str，InteractionRequest 校验
        agent.agent_context = MagicMock()
        agent.agent_context.extra = {"permission_mode": mode} if mode else {}
        agent.agent_context.conv_session_id = conv_session_id
        agent.permission_ruleset = None
        return agent

    def _stub_ask_path(self, adapter, choice="allow_once"):
        """stub 掉 ASK 路径上的辅助方法。"""
        response = MagicMock()
        response.choice = choice
        adapter.gateway.send_and_wait = AsyncMock(return_value=response)
        adapter.recovery.create_interaction_checkpoint = AsyncMock()
        adapter._create_snapshot = AsyncMock(return_value=None)
        adapter._assess_risk_level = MagicMock(return_value="low")
        adapter._format_auth_message = MagicMock(return_value="msg")
        adapter._get_execution_id = MagicMock(return_value="exec1")
        adapter._get_current_step = MagicMock(return_value=1)

    @pytest.mark.asyncio
    async def test_auto_mode_short_circuits_before_ask(self):
        """AUTO 模式 → 直接放行，不调 gateway.send_and_wait。"""
        agent = self._make_agent(mode="auto")
        adapter = self._make_adapter(agent)
        adapter.gateway.send_and_wait = AsyncMock()

        result = await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})

        assert result is True
        adapter.gateway.send_and_wait.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plan_mode_allows_readonly_tool(self):
        """PLAN 模式 + SEARCH 工具（只读） → 放行。"""
        agent = self._make_agent(mode="plan")
        # 模拟 SEARCH 工具
        search_tool = MagicMock()
        search_tool.category = ToolCategory.SEARCH
        agent.tools = {"search_web": search_tool}

        adapter = self._make_adapter(agent)
        adapter.gateway.send_and_wait = AsyncMock()

        result = await adapter.request_tool_permission("search_web", {"q": "hello"})

        assert result is True
        adapter.gateway.send_and_wait.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plan_mode_asks_write_tool_via_checkpoint_replay(self):
        """PLAN 模式 + DATABASE 工具 → Mode 不短路 → checkpoint 命中 → 复用 allow。"""
        agent = self._make_agent(mode="plan")
        db_tool = MagicMock()
        db_tool.category = ToolCategory.DATABASE
        agent.tools = {"execute_sql": db_tool}

        store = PermissionCheckpointStore()
        # 预存 checkpoint
        await store.save_checkpoint(
            "sess1", "execute_sql", hash_tool_input({"sql": "SELECT 1"}),
            decision="allow",
        )

        adapter = self._make_adapter(agent, checkpoint_store=store)
        adapter.gateway.send_and_wait = AsyncMock()

        result = await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})

        assert result is True
        # checkpoint 命中，不调 gateway
        adapter.gateway.send_and_wait.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_session_cache_short_circuits(self):
        """同 session + 同 tool + 同 args 的 allow_session 决策被缓存。"""
        agent = self._make_agent()
        adapter = self._make_adapter(agent)
        self._stub_ask_path(adapter, choice="allow_session")

        # 第一次：ASK → allow_session → 缓存
        r1 = await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})
        assert r1 is True
        assert adapter.gateway.send_and_wait.await_count == 1

        # 第二次：缓存命中，不再 ASK
        r2 = await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})
        assert r2 is True
        assert adapter.gateway.send_and_wait.await_count == 1  # 仍是 1，没增加

    @pytest.mark.asyncio
    async def test_session_cache_isolated_per_session(self):
        """不同 session_id 的 cache 不串。"""
        agent = self._make_agent()
        adapter = self._make_adapter(agent)
        self._stub_ask_path(adapter, choice="allow_session")

        # session 1: allow_session 缓存
        agent.agent_context.conv_session_id = "sess1"
        await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})
        assert adapter.gateway.send_and_wait.await_count == 1

        # 切到 session 2: cache 不命中，重新 ASK
        agent.agent_context.conv_session_id = "sess2"
        await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})
        assert adapter.gateway.send_and_wait.await_count == 2  # 又 ASK 了一次

    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_ask(self):
        """ASK 决策后落 CheckpointStore。"""
        agent = self._make_agent()
        store = PermissionCheckpointStore()
        adapter = self._make_adapter(agent, checkpoint_store=store)
        self._stub_ask_path(adapter, choice="allow_once")  # allow_once 不入 session_cache

        await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})

        # 验证 checkpoint 已落
        cp = await store.load_checkpoint(
            "sess1", "execute_sql", hash_tool_input({"sql": "SELECT 1"})
        )
        assert cp is not None
        assert cp.decision == "allow"

    @pytest.mark.asyncio
    async def test_ruleset_deny_short_circuits(self):
        """Ruleset DENY → 直接拒绝，不查 checkpoint 也不 ASK。"""
        from derisk.agent.core.agent_info import (
            PermissionAction, PermissionRule, PermissionRuleset,
        )

        agent = self._make_agent()
        # 配 DENY rule
        ruleset = PermissionRuleset()
        ruleset.add_rule(PermissionRule(
            action=PermissionAction.DENY,
            pattern="execute_sql",
            permission="execute_sql",
        ))
        agent.permission_ruleset = ruleset

        adapter = self._make_adapter(agent)
        adapter.gateway.send_and_wait = AsyncMock()

        result = await adapter.request_tool_permission("execute_sql", {"sql": "SELECT 1"})

        assert result is False
        adapter.gateway.send_and_wait.assert_not_awaited()
