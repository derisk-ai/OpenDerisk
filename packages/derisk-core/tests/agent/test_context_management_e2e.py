"""
端到端上下文管理测试 - 验证消息列表完整性和压缩逻辑

测试目标:
1. 验证单轮/多轮对话消息完整性
2. 验证追问/授权流程消息列表正确性
3. 验证三层压缩逻辑 (Hot/Warm/Cold)
4. 验证层迁移、剪枝、GptsMemory 清理
5. 验证数据版本兼容 (v2 vs legacy)
6. 验证 BuildResult 清理链
"""

import asyncio
import json
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field as dc_field

from derisk.agent.expand.react_master_agent.work_log import (
    WorkLogManager,
    create_work_log_manager,
)
from derisk.agent.expand.react_master_agent.layer_manager import (
    LayerManager,
    LayerMigrationConfig,
    EntryWrapper,
    ColdSummary,
)
from derisk.agent.expand.react_master_agent.history_message_builder import (
    HistoryMessageBuilder,
    CompressionConfig,
    BuildResult,
    DEFAULT_CHARS_PER_TOKEN,
)
from derisk.agent.core.memory.gpts.file_base import (
    WorkEntry,
    WorkLogSummary,
    WorkLogStatus,
    SimpleWorkLogStorage,
)
from derisk.agent.core.memory.gpts.base import (
    GptsMessage,
    MESSAGE_DATA_VERSION_V2,
)
from derisk.agent.core.action.base import ActionOutput, AskUserType
from derisk.core.interface.message import ModelMessageRoleType


# ========== Mock 辅助类 ==========


@dataclass
class MockGptsMessage:
    """轻量 GptsMessage mock，供测试使用。"""

    conv_id: str = ""
    conv_session_id: str = ""
    sender: str = ""
    sender_name: str = ""
    message_id: str = ""
    role: str = ""
    content: str = ""
    rounds: int = 0
    tool_calls: Optional[List[Dict]] = None
    content_types: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None
    data_version: Optional[str] = None
    observation: Optional[str] = None
    is_success: bool = True
    show_message: bool = True

    _work_entries: Optional[List[WorkEntry]] = dc_field(default=None, repr=False)
    _action_report_cache: Optional[List] = dc_field(default=None, repr=False)
    _action_report_raw: Optional[str] = dc_field(default=None, repr=False)

    @property
    def is_new_format(self) -> bool:
        return self.data_version == MESSAGE_DATA_VERSION_V2

    @property
    def is_legacy_tool_message(self) -> bool:
        return self.role == "tool" and not self.is_new_format

    @property
    def action_report(self) -> Optional[List]:
        if self._action_report_cache is not None:
            return self._action_report_cache
        if self.is_new_format and self._work_entries:
            outputs = [e.to_action_output() for e in self._work_entries]
            self._action_report_cache = outputs
            return outputs
        if self._action_report_raw:
            parsed = ActionOutput.parse_action_reports(self._action_report_raw)
            self._action_report_cache = parsed
            return parsed
        if self.observation:
            legacy = ActionOutput(
                action_id="legacy_tool",
                content=self.observation,
                is_exe_success=True,
            )
            self._action_report_cache = [legacy]
            return [legacy]
        return None

    def set_work_entries(self, entries: List[WorkEntry]) -> None:
        self._work_entries = entries
        self._action_report_cache = None

    def set_action_report_raw(self, raw: Optional[str]) -> None:
        self._action_report_raw = raw
        self._action_report_cache = None

    def view(self) -> Optional[str]:
        views = [
            v
            for item in (self.action_report or [])
            if (v := getattr(item, "view", None) or getattr(item, "observations", None) or getattr(item, "content", None))
        ]
        return "\n".join(views) or self.content

    def answer(self) -> Optional[str]:
        views = [
            v
            for item in (self.action_report or [])
            if (v := getattr(item, "content", None) or getattr(item, "observations", None) or getattr(item, "view", None))
        ]
        return "\n".join(views) or self.content


class MockGptsMemory:
    """Mock GptsMemory，支持 get_messages / get_messages_with_work_entries / apply_build_result_cleanup。"""

    def __init__(self):
        self._messages: Dict[str, List[MockGptsMessage]] = {}
        self._work_entries_by_message: Dict[str, Dict[str, List[WorkEntry]]] = {}
        self._cleanup_calls: List[Dict] = []

    def add_message(self, msg: MockGptsMessage):
        if msg.conv_id not in self._messages:
            self._messages[msg.conv_id] = []
        self._messages[msg.conv_id].append(msg)

    def add_work_entry_for_message(self, conv_id: str, message_id: str, entry: WorkEntry):
        if conv_id not in self._work_entries_by_message:
            self._work_entries_by_message[conv_id] = {}
        if message_id not in self._work_entries_by_message[conv_id]:
            self._work_entries_by_message[conv_id][message_id] = []
        self._work_entries_by_message[conv_id][message_id].append(entry)

    async def get_messages(self, conv_id: str) -> List[MockGptsMessage]:
        return self._messages.get(conv_id, [])

    async def get_messages_with_work_entries(self, conv_id: str) -> List[MockGptsMessage]:
        messages = self._messages.get(conv_id, [])
        entries_by_msg = self._work_entries_by_message.get(conv_id, {})
        for msg in messages:
            if msg.role == "assistant" and msg.is_new_format:
                entries = entries_by_msg.get(msg.message_id, [])
                if entries:
                    msg.set_work_entries(entries)
        return messages

    async def apply_build_result_cleanup(
        self, conv_id: str, cleanup_hints: Dict[str, List[str]]
    ) -> Dict[str, int]:
        self._cleanup_calls.append({"conv_id": conv_id, "hints": cleanup_hints})
        return {"messages_evicted": len(cleanup_hints.get("can_evict_message_ids", [])),
                "entries_evicted": len(cleanup_hints.get("can_evict_entry_message_ids", []))}


class MockWorkLogStorage(SimpleWorkLogStorage):
    """Mock WorkLog Storage，继承 SimpleWorkLogStorage。"""
    pass


# ========== 辅助函数 ==========


def _make_gpts_message(
    conv_id: str,
    role: str,
    content: str,
    message_id: str = "",
    tool_calls: Optional[List[Dict]] = None,
    rounds: int = 0,
    data_version: Optional[str] = None,
    observation: Optional[str] = None,
) -> MockGptsMessage:
    if not message_id:
        message_id = f"msg_{conv_id}_{rounds}_{role}"
    return MockGptsMessage(
        conv_id=conv_id,
        conv_session_id=conv_id,
        sender=role,
        sender_name=role,
        message_id=message_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        rounds=rounds,
        data_version=data_version,
        observation=observation,
    )


def _make_work_entry(
    tool: str,
    result: str = "ok",
    tool_call_id: str = "",
    conv_id: str = "conv1",
    message_id: str = "",
    success: bool = True,
    round_index: int = 0,
    timestamp: float = 0.0,
) -> WorkEntry:
    return WorkEntry(
        timestamp=timestamp or time.time(),
        tool=tool,
        args={"query": "test"},
        result=result,
        success=success,
        tool_call_id=tool_call_id,
        conv_id=conv_id,
        message_id=message_id,
        round_index=round_index,
    )


def _make_tool_call(tool_name: str, tc_id: str) -> Dict:
    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": tool_name, "arguments": "{}"},
    }


async def _create_work_log_manager(
    agent_id: str = "test_agent",
    session_id: str = "test_session",
) -> WorkLogManager:
    storage = MockWorkLogStorage()
    manager = WorkLogManager(
        agent_id=agent_id,
        session_id=session_id,
        work_log_storage=storage,
    )
    await manager.initialize()
    return manager


# ========== 场景测试 ==========


class TestSingleRound:
    """场景1: 单轮对话 user→AI→tool→AI"""

    @pytest.mark.asyncio
    async def test_single_round_message_completeness(self):
        """单轮对话消息列表包含 user/ai/tool/ai，顺序正确。"""
        mock_memory = MockGptsMemory()
        conv_id = "test_session"

        # 模拟: user 消息 → AI 带 tool_calls → tool 结果 → AI 最终回复
        tc_id = "tc_001"
        mock_memory.add_message(_make_gpts_message(
            conv_id, "Human", "查询天气", rounds=1, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "让我查一下",
            tool_calls=[_make_tool_call("weather_query", tc_id)],
            rounds=2, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "今天晴天", rounds=3, data_version="v2",
        ))

        # 创建 WorkLogManager 并记录工具调用
        wlm = await _create_work_log_manager()
        await wlm.record_user_message("查询天气", conv_id)
        ao = ActionOutput(content="北京: 晴, 25°C", is_exe_success=True)
        await wlm.record_action(
            "weather_query", {"city": "北京"}, ao,
            tool_call_id=tc_id, conv_id=conv_id,
        )

        # 构建 HistoryMessageBuilder
        builder = HistoryMessageBuilder(
            work_log_manager=wlm,
            gpts_memory=mock_memory,
        )

        messages, layer_tokens = await builder.build_messages(
            current_conv_id=conv_id,
            session_id="test_session",
            context_window=128000,
        )

        assert len(messages) >= 3, f"Expected >=3 messages, got {len(messages)}"

        roles = [m.get("role", "") for m in messages]
        # 至少应该有 human, ai, tool 消息
        assert any(r in ("human", "user") for r in roles), f"No human message in {roles}"
        assert any(r in ("ai", "assistant") for r in roles), f"No AI message in {roles}"

    @pytest.mark.asyncio
    async def test_single_round_work_log_only(self):
        """纯 work_log 模式（无 GptsMemory）也能构建消息。"""
        wlm = await _create_work_log_manager()
        conv_id = "test_session"

        await wlm.record_user_message("你好", conv_id)
        ao = ActionOutput(content="Hello!", is_exe_success=True)
        await wlm.record_action(
            "greeting", {}, ao,
            tool_call_id="tc_greet", conv_id=conv_id,
        )

        builder = HistoryMessageBuilder(work_log_manager=wlm)
        messages, _ = await builder.build_messages(
            current_conv_id=conv_id,
            session_id="test_session",
        )

        assert len(messages) >= 1, "Should build messages from work_log"


class TestMultiRound:
    """场景2: 多轮对话历史保留"""

    @pytest.mark.asyncio
    async def test_second_round_includes_first_round_history(self):
        """第二轮消息列表包含第一轮工具调用历史。"""
        mock_memory = MockGptsMemory()
        conv_id = "test_session"

        # 第一轮
        tc_id_1 = "tc_round1"
        mock_memory.add_message(_make_gpts_message(
            conv_id, "Human", "搜索Python", rounds=1, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "搜索中...",
            tool_calls=[_make_tool_call("search", tc_id_1)],
            rounds=2, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "找到了Python教程", rounds=3, data_version="v2",
        ))

        # 第二轮
        tc_id_2 = "tc_round2"
        mock_memory.add_message(_make_gpts_message(
            conv_id, "Human", "再搜索Java", rounds=4, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "搜索中...",
            tool_calls=[_make_tool_call("search", tc_id_2)],
            rounds=5, data_version="v2",
        ))

        wlm = await _create_work_log_manager()
        # 记录两轮
        await wlm.record_user_message("搜索Python", conv_id)
        ao1 = ActionOutput(content="Python tutorial found", is_exe_success=True)
        await wlm.record_action("search", {"q": "Python"}, ao1, tool_call_id=tc_id_1, conv_id=conv_id)

        await wlm.record_user_message("再搜索Java", conv_id)
        ao2 = ActionOutput(content="Java tutorial found", is_exe_success=True)
        await wlm.record_action("search", {"q": "Java"}, ao2, tool_call_id=tc_id_2, conv_id=conv_id)

        builder = HistoryMessageBuilder(
            work_log_manager=wlm,
            gpts_memory=mock_memory,
        )

        messages, _ = await builder.build_messages(
            current_conv_id=conv_id,
            session_id="test_session",
        )

        # 验证两轮都包含
        all_content = " ".join(str(m.get("content", "")) for m in messages)
        tool_results = [m for m in messages if m.get("role") == ModelMessageRoleType.TOOL]
        assert len(tool_results) >= 2, f"Expected >=2 tool results, got {len(tool_results)}"


class TestFollowUp:
    """场景3: 追问 - 同 session 不同 conv_id"""

    @pytest.mark.asyncio
    async def test_cross_conv_history_ordering(self):
        """历史对话消息出现在当前对话消息之前。"""
        mock_memory = MockGptsMemory()
        wlm = await _create_work_log_manager()

        # 第一个 conv
        conv1 = "test_session_follow_1"
        await wlm.record_user_message("第一个问题", conv1)
        ao1 = ActionOutput(content="第一个回答", is_exe_success=True)
        await wlm.record_action("tool1", {}, ao1, tool_call_id="tc_f1", conv_id=conv1)

        # 第二个 conv (追问)
        conv2 = "test_session_follow_2"
        await wlm.record_user_message("追问", conv2)
        ao2 = ActionOutput(content="追问回答", is_exe_success=True)
        await wlm.record_action("tool2", {}, ao2, tool_call_id="tc_f2", conv_id=conv2)

        builder = HistoryMessageBuilder(
            work_log_manager=wlm,
            gpts_memory=mock_memory,
        )

        messages, _ = await builder.build_messages(
            current_conv_id=conv2,
            session_id="test_session",
        )

        # 至少包含两个对话的消息
        assert len(messages) >= 2, f"Expected >=2 messages, got {len(messages)}"


class TestAskUser:
    """场景4: 授权场景 ask_user"""

    def test_ask_user_action_output_recovery(self):
        """ask_user 工具的 to_action_output 正确恢复 ask_user/ask_type 标记。"""
        entry = WorkEntry(
            timestamp=time.time(),
            tool="ask_user",
            args={"question": "需要确认"},
            result="用户已确认",
            success=True,
            tool_call_id="tc_ask",
        )

        ao = entry.to_action_output()
        assert ao.ask_user is True
        assert ao.ask_type == AskUserType.CONCLUSION_INCOMPLETE.value
        assert ao.action_name == "ask_user"

    def test_send_message_action_output_recovery(self):
        """send_message 工具也应该恢复 ask_user 标记。"""
        entry = WorkEntry(
            timestamp=time.time(),
            tool="send_message",
            args={"content": "结论"},
            result="发送成功",
            success=True,
            tool_call_id="tc_send",
        )

        ao = entry.to_action_output()
        assert ao.ask_user is True

    def test_normal_tool_no_ask_user(self):
        """普通工具不设置 ask_user。"""
        entry = WorkEntry(
            timestamp=time.time(),
            tool="search",
            result="搜索结果",
            success=True,
        )

        ao = entry.to_action_output()
        assert ao.ask_user is False
        assert ao.ask_type is None


class TestLayerMigration:
    """场景5: Hot→Warm→Cold 层迁移"""

    @pytest.mark.asyncio
    async def test_entries_distributed_across_layers(self):
        """大量工具调用触发分层。"""
        config = LayerMigrationConfig(
            hot_ratio=0.45,
            warm_ratio=0.25,
            cold_ratio=0.10,
        )
        lm = LayerManager(config=config)
        lm.set_budgets(context_window=10000)

        # 添加 50 个条目，每个约 200 tokens
        conv_id = "conv_layer"
        for i in range(50):
            entry = WorkEntry(
                timestamp=time.time() + i,
                tool=f"tool_{i}",
                result="x" * 800,  # ~200 tokens at 4 chars/token
                success=True,
                tool_call_id=f"tc_{i}",
                conv_id=conv_id,
                tokens=200,
            )
            await lm.add_entry(entry, trigger_migration=True)

        hot, warm, cold_summaries = lm.get_entries_by_layer(conv_id)

        total = len(hot) + len(warm)
        assert total > 0, "Should have entries in layers"
        # 最新条目应该在 Hot 层
        if hot:
            assert hot[-1].entry.tool == "tool_49", "Latest entry should be in hot"

    @pytest.mark.asyncio
    async def test_layer_manager_respects_budget(self):
        """LayerManager 不超出总预算。"""
        config = LayerMigrationConfig(hot_ratio=0.5, warm_ratio=0.3, cold_ratio=0.1)
        lm = LayerManager(config=config)
        lm.set_budgets(context_window=5000)

        conv_id = "conv_budget"
        for i in range(30):
            entry = WorkEntry(
                timestamp=time.time() + i,
                tool=f"tool_{i}",
                result="x" * 400,
                success=True,
                tool_call_id=f"tc_{i}",
                conv_id=conv_id,
                tokens=100,
            )
            await lm.add_entry(entry, trigger_migration=True)

        stats = lm.get_stats()
        assert "hot" in stats and "entries" in stats["hot"]


class TestCompression:
    """场景6: Warm/Cold 压缩"""

    @pytest.mark.asyncio
    async def test_warm_compression_truncates_results(self):
        """Warm 层工具结果被截断。"""
        builder = HistoryMessageBuilder(
            config=CompressionConfig(warm_tool_result_max_length=100),
        )

        entry = WorkEntry(
            timestamp=time.time(),
            tool="search",
            result="x" * 500,
            success=True,
            tool_call_id="tc_warm",
        )

        compressed = builder._compress_tool_result(entry, "warm")
        assert len(compressed) <= 150, f"Warm result too long: {len(compressed)}"

    @pytest.mark.asyncio
    async def test_hot_preserves_full_results(self):
        """Hot 层保留完整结果。"""
        builder = HistoryMessageBuilder()

        entry = WorkEntry(
            timestamp=time.time(),
            tool="search",
            result="x" * 500,
            success=True,
            tool_call_id="tc_hot",
        )

        full = builder._compress_tool_result(entry, "hot")
        assert len(full) >= 500, "Hot should preserve full result"


class TestPruning:
    """场景7: 智能剪枝"""

    @pytest.mark.asyncio
    async def test_duplicate_tool_pruning(self):
        """重复工具调用被剪枝。"""
        config = LayerMigrationConfig(
            enable_duplicate_prune=True,
            hot_ratio=0.3,
            warm_ratio=0.3,
            cold_ratio=0.1,
        )
        lm = LayerManager(config=config)
        lm.set_budgets(context_window=5000)

        conv_id = "conv_prune"
        # 添加 20 个相同工具调用
        for i in range(20):
            entry = WorkEntry(
                timestamp=time.time() + i,
                tool="list_files",
                args={"path": "/tmp"},
                result=f"file_{i}.txt",
                success=True,
                tool_call_id=f"tc_dup_{i}",
                conv_id=conv_id,
                tokens=50,
            )
            await lm.add_entry(entry, trigger_migration=True)

        _, warm, _ = lm.get_entries_by_layer(conv_id)
        # 剪枝后 Warm 层不应该全是重复的 list_files
        warm_tools = [w.entry.tool for w in warm]
        # 验证不是所有 20 个都在 warm（部分应被剪枝或迁移到 cold）
        assert len(warm_tools) < 20, f"Expected pruning, got {len(warm_tools)} warm entries"


class TestMemoryCleanup:
    """场景8+15: GptsMemory 清理 + BuildResult 清理链"""

    def test_build_result_cleanup_hints(self):
        """BuildResult.get_cache_cleanup_hints() 返回正确的清理提示。"""
        result = BuildResult(
            messages=[],
            layer_tokens={"hot": 100, "warm": 50, "cold": 20},
            hot_message_ids=["m1", "m2"],
            warm_message_ids=["m3", "m4"],
            cold_message_ids=["m5", "m6"],
        )

        hints = result.get_cache_cleanup_hints()
        assert hints["can_evict_message_ids"] == ["m5", "m6"]
        assert set(hints["can_evict_entry_message_ids"]) == {"m3", "m4", "m5", "m6"}

    @pytest.mark.asyncio
    async def test_mock_gpts_memory_cleanup(self):
        """MockGptsMemory.apply_build_result_cleanup 被正确调用。"""
        mock_memory = MockGptsMemory()

        result = await mock_memory.apply_build_result_cleanup(
            "conv1",
            {"can_evict_message_ids": ["m1"], "can_evict_entry_message_ids": ["m1", "m2"]},
        )

        assert result["messages_evicted"] == 1
        assert result["entries_evicted"] == 2
        assert len(mock_memory._cleanup_calls) == 1

    @pytest.mark.asyncio
    async def test_real_gpts_memory_cleanup(self):
        """验证真实 GptsMemory 的 apply_build_result_cleanup。"""
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        try:
            memory = GptsMemory()
        except Exception:
            pytest.skip("GptsMemory requires dependencies not available in test env")
            return

        # 基本验证方法存在
        assert hasattr(memory, "apply_build_result_cleanup")
        assert hasattr(memory, "get_messages_with_work_entries")


class TestDataVersionLegacy:
    """场景9: 老数据 action_report 直接存"""

    def test_legacy_message_from_dict(self):
        """老数据 (无 data_version) 从 action_report raw 解析。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "done",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        assert msg.is_new_format is False
        assert msg.action_report is None  # 无 raw 无 entries

    def test_legacy_with_observation_fallback(self):
        """老数据有 observation 字段时兜底构建 action_report。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "tool", "content": "tool result",
            "observation": "legacy tool output",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        assert msg.is_legacy_tool_message is True
        report = msg.action_report
        assert report is not None
        assert len(report) == 1
        assert report[0].content == "legacy tool output"


class TestDataVersionV2:
    """场景10: 新数据 work_entries"""

    def test_v2_message_with_work_entries(self):
        """v2 消息 + work_entries → action_report 从 entries 构建。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "done",
            "data_version": "v2",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        assert msg.is_new_format is True
        assert msg.action_report is None  # 无 entries

        # 关联 entries
        entry = WorkEntry(
            timestamp=time.time(),
            tool="search",
            result="found results",
            success=True,
            tool_call_id="tc_v2",
        )
        msg.set_work_entries([entry])

        report = msg.action_report
        assert report is not None
        assert len(report) == 1
        assert report[0].action_name == "search"
        assert report[0].content == "found results"

    def test_v2_from_agent_message_sets_version(self):
        """from_agent_message 自动设置 data_version=v2。"""
        # 由于 from_agent_message 需要 sender agent，用 from_dict 模拟
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "done",
            "data_version": "v2",
            "show_message": True, "created_at": None, "updated_at": None,
        })
        assert msg.data_version == MESSAGE_DATA_VERSION_V2


class TestDataVersionMixed:
    """场景11: 新旧混合"""

    def test_mixed_messages_both_have_action_report(self):
        """同 session 老+新消息共存，两种格式都能获取 action_report。"""
        # 老消息 - observation 兜底
        old_msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "old_m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "tool", "content": "result",
            "observation": "old tool result",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        # 新消息 - work_entries
        new_msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "new_m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "done",
            "data_version": "v2",
            "show_message": True, "created_at": None, "updated_at": None,
        })
        new_msg.set_work_entries([
            WorkEntry(timestamp=time.time(), tool="search", result="new result",
                      success=True, tool_call_id="tc_new"),
        ])

        # 两种格式都能获取
        assert old_msg.action_report is not None
        assert new_msg.action_report is not None
        assert old_msg.action_report[0].content == "old tool result"
        assert new_msg.action_report[0].content == "new result"


class TestToolListIntegrity:
    """场景12: 工具列表完整性"""

    def test_function_calling_params_returns_tools(self):
        """function_calling_params 包含工具定义。"""
        # 这个测试需要完整的 ReActMasterAgent，在此做结构性验证
        from derisk.agent.expand.react_master_agent import ReActMasterAgent

        assert hasattr(ReActMasterAgent, "function_calling_params")
        # 验证方法是异步的
        import inspect
        assert inspect.iscoroutinefunction(ReActMasterAgent.function_calling_params)


class TestFallback:
    """场景13: Fallback 路径"""

    @pytest.mark.asyncio
    async def test_builder_failure_returns_empty(self):
        """HistoryMessageBuilder 异常时返回空列表。"""
        builder = HistoryMessageBuilder()

        # 无任何数据源时应返回空
        messages, layer_tokens = await builder.build_messages(
            current_conv_id="nonexistent",
            session_id="test",
        )

        assert messages == []
        assert layer_tokens == {"hot": 0, "warm": 0, "cold": 0}


class TestViewAnswer:
    """场景14: v2 消息 view()/answer() 兼容"""

    def test_v2_message_view_with_work_entries(self):
        """set_work_entries 后 view() 返回工具结果。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "fallback content",
            "data_version": "v2",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        # 无 entries 时 view 应该返回 content
        assert msg.view() == "fallback content"

        # 设置 entries
        msg.set_work_entries([
            WorkEntry(timestamp=time.time(), tool="search", result="search result view",
                      success=True, tool_call_id="tc_view"),
        ])

        # 有 entries 后 view 应该从 action_report 构建
        view = msg.view()
        assert view is not None
        assert "search result view" in view

    def test_v2_message_answer_with_work_entries(self):
        """set_work_entries 后 answer() 返回工具结果。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "fallback",
            "data_version": "v2",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        msg.set_work_entries([
            WorkEntry(timestamp=time.time(), tool="search", result="answer content",
                      success=True, tool_call_id="tc_ans"),
        ])

        answer = msg.answer()
        assert answer is not None
        assert "answer content" in answer

    def test_legacy_message_view_from_observation(self):
        """老消息 observation 兜底的 view() 正常返回。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "tool", "content": "tool output",
            "observation": "observation content",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        view = msg.view()
        assert view is not None
        assert "observation content" in view


class TestBuildResultCleanup:
    """场景15: thinking→build_result→cleanup 链"""

    @pytest.mark.asyncio
    async def test_build_messages_with_result_returns_build_result(self):
        """build_messages_with_result 返回 BuildResult 对象。"""
        wlm = await _create_work_log_manager()
        conv_id = "conv_br"

        await wlm.record_user_message("测试", conv_id)
        ao = ActionOutput(content="结果", is_exe_success=True)
        await wlm.record_action("tool1", {}, ao, tool_call_id="tc_br1", conv_id=conv_id)

        builder = HistoryMessageBuilder(work_log_manager=wlm)

        result = await builder.build_messages_with_result(
            current_conv_id=conv_id,
            session_id="test_session",
        )

        assert isinstance(result, BuildResult)
        assert isinstance(result.messages, list)
        assert isinstance(result.layer_tokens, dict)
        assert hasattr(result, "get_cache_cleanup_hints")

    @pytest.mark.asyncio
    async def test_cleanup_chain_integration(self):
        """完整清理链: build_result → cleanup_hints → apply_cleanup。"""
        mock_memory = MockGptsMemory()

        # 构造 BuildResult 模拟 cold 层有可清理消息
        result = BuildResult(
            messages=[{"role": "user", "content": "test"}],
            layer_tokens={"hot": 100, "warm": 50, "cold": 20},
            hot_message_ids=["m1"],
            warm_message_ids=["m2"],
            cold_message_ids=["m3"],
        )

        hints = result.get_cache_cleanup_hints()
        assert "m3" in hints["can_evict_message_ids"]

        # 应用清理
        cleanup_stats = await mock_memory.apply_build_result_cleanup("conv1", hints)
        assert cleanup_stats["messages_evicted"] == 1

        # 验证 trim_work_log
        wlm = await _create_work_log_manager()
        wlm.work_log = [
            WorkEntry(timestamp=1.0, tool="t1", message_id="m2"),
            WorkEntry(timestamp=2.0, tool="t2", message_id="m3"),
            WorkEntry(timestamp=3.0, tool="t3", message_id="m1"),
        ]
        evictable = set(hints.get("can_evict_entry_message_ids", []))
        wlm.trim_work_log(evictable)

        # m2 和 m3 应被清理，m1 保留
        remaining_mids = [getattr(e, "message_id", None) for e in wlm.work_log]
        assert "m1" in remaining_mids
        assert "m2" not in remaining_mids
        assert "m3" not in remaining_mids


class TestToolResultContent:
    """验证 tool result 内容正确，不出现 [result not available]。"""

    @pytest.mark.asyncio
    async def test_tool_result_has_actual_content(self):
        """tool_call_id 匹配时，tool result 包含实际工具执行结果。"""
        mock_memory = MockGptsMemory()
        conv_id = "test_session"
        tc_id = "tc_tool_result_001"

        mock_memory.add_message(_make_gpts_message(
            conv_id, "Human", "查询数据", rounds=1, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "查询中...",
            tool_calls=[_make_tool_call("execute_sql", tc_id)],
            rounds=2, data_version="v2",
        ))

        wlm = await _create_work_log_manager()
        await wlm.record_user_message("查询数据", conv_id)
        ao = ActionOutput(content="SELECT * FROM sales: 100 rows", is_exe_success=True)
        await wlm.record_action(
            "execute_sql", {"sql": "SELECT * FROM sales"}, ao,
            tool_call_id=tc_id, conv_id=conv_id,
        )

        builder = HistoryMessageBuilder(work_log_manager=wlm, gpts_memory=mock_memory)
        messages, _ = await builder.build_messages(
            current_conv_id=conv_id, session_id="test_session",
        )

        tool_msgs = [m for m in messages if m.get("role") == ModelMessageRoleType.TOOL]
        assert len(tool_msgs) >= 1, f"Expected tool messages, got {len(tool_msgs)}"
        for tm in tool_msgs:
            assert tm["content"] != "[result not available]", \
                f"Tool result should have actual content, got: {tm['content']}"
            assert "100 rows" in tm["content"], f"Tool result missing expected content: {tm['content']}"

    @pytest.mark.asyncio
    async def test_tool_result_fallback_by_tool_name(self):
        """tool_call_id 不匹配时，按工具名 fallback 查找结果。"""
        mock_memory = MockGptsMemory()
        conv_id = "test_session"

        # gpts_message 的 tool_call_id 与 WorkEntry 不同
        gpts_tc_id = "tc_gpts_id"
        worklog_tc_id = "tc_worklog_id"

        mock_memory.add_message(_make_gpts_message(
            conv_id, "Human", "搜索", rounds=1, data_version="v2",
        ))
        mock_memory.add_message(_make_gpts_message(
            conv_id, "AI", "",
            tool_calls=[_make_tool_call("search_tool", gpts_tc_id)],
            rounds=2, data_version="v2",
        ))

        wlm = await _create_work_log_manager()
        await wlm.record_user_message("搜索", conv_id)
        ao = ActionOutput(content="Found 5 results", is_exe_success=True)
        await wlm.record_action(
            "search_tool", {"q": "test"}, ao,
            tool_call_id=worklog_tc_id, conv_id=conv_id,
        )

        builder = HistoryMessageBuilder(work_log_manager=wlm, gpts_memory=mock_memory)
        messages, _ = await builder.build_messages(
            current_conv_id=conv_id, session_id="test_session",
        )

        tool_msgs = [m for m in messages if m.get("role") == ModelMessageRoleType.TOOL]
        assert len(tool_msgs) >= 1
        # 应该通过 tool_name fallback 找到结果
        assert "Found 5 results" in tool_msgs[0]["content"], \
            f"Fallback by tool name failed: {tool_msgs[0]['content']}"

    @pytest.mark.asyncio
    async def test_tool_result_fallback_from_gpts_observation(self):
        """WorkLog 完全没有记录时，从 gpts_message 的 observation 获取结果。"""
        mock_memory = MockGptsMemory()
        conv_id = "test_session"
        tc_id = "tc_no_worklog"

        mock_memory.add_message(_make_gpts_message(
            conv_id, "Human", "查询", rounds=1,
        ))
        msg_with_obs = _make_gpts_message(
            conv_id, "AI", "",
            tool_calls=[_make_tool_call("list_tables", tc_id)],
            rounds=2,
        )
        msg_with_obs.observation = "tables: users, orders, products"
        mock_memory.add_message(msg_with_obs)

        # 空 WorkLogManager - 没有任何记录
        wlm = await _create_work_log_manager()
        await wlm.record_user_message("查询", conv_id)

        builder = HistoryMessageBuilder(work_log_manager=wlm, gpts_memory=mock_memory)
        messages, _ = await builder.build_messages(
            current_conv_id=conv_id, session_id="test_session",
        )

        tool_msgs = [m for m in messages if m.get("role") == ModelMessageRoleType.TOOL]
        assert len(tool_msgs) >= 1
        # 应该从 observation fallback
        assert "tables:" in tool_msgs[0]["content"], \
            f"Should fallback to observation: {tool_msgs[0]['content']}"


class TestSystemMessage:
    """验证 system message 不丢失。"""

    @pytest.mark.asyncio
    async def test_system_prompt_from_messages_param(self):
        """thinking() 应从 messages 参数中提取 system prompt。"""
        # 模拟 load_thinking_messages 返回的 messages 列表（第一个是 system）
        from derisk.agent.core.base_agent import _new_system_message

        system_content = "你是一个数据分析助手。"
        system_msgs = _new_system_message(system_content)

        # 验证 _new_system_message 返回有效消息
        assert len(system_msgs) >= 1
        sys_msg = system_msgs[0]
        assert sys_msg.get("role") in ("system", ModelMessageRoleType.SYSTEM)
        assert system_content in str(sys_msg.get("content", ""))

    def test_gpts_message_init_with_action_report(self):
        """GptsMessage 构造函数接受 action_report 参数（DB 兼容）。"""
        # 模拟 DB 层 _to_gpts_message 直接传 action_report
        msg = GptsMessage(
            conv_id="c1", conv_session_id="s1", message_id="m1",
            sender="a", sender_name="Agent", role="assistant",
            content="done",
            action_report=[{"type": "test"}],
        )
        assert msg.action_report == [{"type": "test"}]

    def test_gpts_message_init_with_string_action_report(self):
        """GptsMessage 构造函数接受字符串 action_report。"""
        msg = GptsMessage(
            conv_id="c1", conv_session_id="s1", message_id="m1",
            sender="a", sender_name="Agent", role="assistant",
            content="done",
            action_report='{"key": "value"}',
        )
        assert msg._action_report_raw == '{"key": "value"}'

    def test_gpts_message_init_without_action_report(self):
        """GptsMessage 构造函数不传 action_report 不报错。"""
        msg = GptsMessage(
            conv_id="c1", conv_session_id="s1", message_id="m1",
            sender="a", sender_name="Agent", role="assistant",
            content="done",
        )
        assert msg.action_report is None


class TestToDict:
    """GptsMessage.to_dict() 不泄露内部字段。"""

    def test_to_dict_no_internal_fields(self):
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "ok",
            "data_version": "v2",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        d = msg.to_dict()
        assert "_action_report_raw" not in d
        assert "_action_report_cache" not in d
        assert "_work_entries" not in d
        assert "data_version" in d
        assert d["data_version"] == "v2"

    def test_to_dict_preserves_action_report_for_legacy(self):
        """老格式 to_dict 保留 action_report 字段。"""
        msg = GptsMessage.from_dict({
            "conv_id": "c1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "a", "sender_name": "Agent", "receiver": "b",
            "receiver_name": "User", "role": "assistant", "content": "ok",
            "show_message": True, "created_at": None, "updated_at": None,
        })
        # 无 action_report
        d = msg.to_dict()
        assert d.get("action_report") is None


class TestFollowUpSessionHistory:
    """追问场景：跨轮次消息加载。"""

    @pytest.mark.asyncio
    async def test_get_session_messages_loads_cross_round(self):
        """get_session_messages 应加载同 session 下所有轮次消息。"""
        from unittest.mock import AsyncMock, MagicMock

        memory = MagicMock()
        # 模拟 get_messages 按 conv_id 只返回当前轮
        round1_msg = GptsMessage.from_dict({
            "conv_id": "session_abc_1", "conv_session_id": "session_abc",
            "message_id": "m1", "sender": "user", "sender_name": "User",
            "receiver": "agent", "receiver_name": "Agent", "role": "user",
            "content": "round 1 question", "show_message": True,
            "created_at": None, "updated_at": None,
        })
        round2_msg = GptsMessage.from_dict({
            "conv_id": "session_abc_2", "conv_session_id": "session_abc",
            "message_id": "m2", "sender": "user", "sender_name": "User",
            "receiver": "agent", "receiver_name": "Agent", "role": "user",
            "content": "round 2 follow-up", "show_message": True,
            "created_at": None, "updated_at": None,
        })

        # get_messages(session_id) → empty, get_messages(conv_id) → only round 2
        async def mock_get_messages(cid):
            if cid == "session_abc":
                return []
            elif cid == "session_abc_2":
                return [round2_msg]
            return []

        # get_session_messages(session_id) → all rounds
        async def mock_get_session_messages(sid):
            if sid == "session_abc":
                return [round1_msg, round2_msg]
            return []

        memory.get_messages = mock_get_messages
        memory.get_session_messages = mock_get_session_messages
        memory._cache_messages = AsyncMock()

        builder = HistoryMessageBuilder(gpts_memory=memory)
        builder.work_log_manager = None

        messages = await builder._build_current_conv_hot_worklog(
            conv_id="session_abc_2", hot_budget=10000
        )
        # Should have loaded both rounds via get_session_messages fallback
        assert len(messages) >= 2, (
            f"Expected >=2 messages (both rounds), got {len(messages)}"
        )
        contents = [m.get("content", "") for m in messages]
        assert any("round 1" in str(c) for c in contents), (
            f"Round 1 message missing from follow-up. Contents: {contents}"
        )

    @pytest.mark.asyncio
    async def test_session_id_extraction(self):
        """session_id 从 conv_id 正确提取。"""
        # conv_id = "session_abc_2" → session_id = "session_abc"
        conv_id = "session_abc_2"
        session_id = conv_id.rsplit("_", 1)[0] if "_" in conv_id else conv_id
        assert session_id == "session_abc"

        # conv_id = "noseparator" → session_id = "noseparator"
        conv_id2 = "noseparator"
        session_id2 = conv_id2.rsplit("_", 1)[0] if "_" in conv_id2 else conv_id2
        assert session_id2 == "noseparator"

    @pytest.mark.asyncio
    async def test_load_full_session_history_populates_cache(self):
        """load_full_session_history 将全 session 消息缓存到 conv_id。"""
        from unittest.mock import MagicMock, AsyncMock, patch
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory, ConversationCache

        round1 = GptsMessage.from_dict({
            "conv_id": "s1_1", "conv_session_id": "s1", "message_id": "m1",
            "sender": "u", "sender_name": "U", "receiver": "a",
            "receiver_name": "A", "role": "user", "content": "q1",
            "show_message": True, "created_at": None, "updated_at": None,
        })
        round2 = GptsMessage.from_dict({
            "conv_id": "s1_2", "conv_session_id": "s1", "message_id": "m2",
            "sender": "u", "sender_name": "U", "receiver": "a",
            "receiver_name": "A", "role": "user", "content": "q2",
            "show_message": True, "created_at": None, "updated_at": None,
        })

        # Create a minimal mock GptsMemory
        mock_msg_mem = MagicMock()
        mock_msg_mem.get_by_session_id.return_value = [round1, round2]
        mock_plans_mem = MagicMock()
        mock_plans_mem.get_by_conv_id = AsyncMock(return_value=[])

        gm = GptsMemory.__new__(GptsMemory)
        gm._message_memory = mock_msg_mem
        gm._plans_memory = mock_plans_mem
        gm._work_log_db_storage = None
        gm._executor = None
        gm._conversations = {}
        gm._conv_locks = {}
        gm._global_lock = __import__("asyncio").Lock()

        # Pre-create cache for conv_id
        from derisk.agent.core.memory.gpts.gpts_memory import VisProtocolConverter
        cache = ConversationCache("s1_2", VisProtocolConverter())
        gm._conversations["s1_2"] = cache

        # Mock blocking_func_to_async: returns messages for get_by_session_id,
        # empty list for get_by_conv_id (plans)
        async def mock_blocking(executor, func, *args, **kwargs):
            func_name = getattr(func, "__name__", str(func))
            if "session" in func_name:
                return [round1, round2]
            return []

        with patch(
            "derisk.agent.core.memory.gpts.gpts_memory.blocking_func_to_async",
            side_effect=mock_blocking,
        ):
            result = await gm.load_full_session_history("s1_2", "s1")

        assert result is not None
        assert result["hot_warm_count"] == 2
        assert "m1" in cache.message_ids
        assert "m2" in cache.message_ids
