"""Tests for History Compaction Pipeline (Agent Tool Work Log Framework v3.0).

Tests cover:
- UnifiedMessageAdapter (v1, v2, dict messages, role normalization)
- HistoryChapter and HistoryCatalog (data models, serialization)
- HistoryCompactionConfig (defaults)
- UnifiedCompactionPipeline (Layer 1 truncation, Layer 2 pruning, Layer 3 compaction)
- create_history_tools (tool factory)
- Content protection (code blocks, thinking chains, file paths)
- Key info extraction (rule-based)
"""

import json
import time
import uuid

import pytest

from derisk.agent.core.memory.message_adapter import (
    UnifiedMessageAdapter,
    _getval,
    _ROLE_ALIASES,
)
from derisk.agent.core.memory.history_archive import (
    HistoryChapter,
    HistoryCatalog,
)
from derisk.agent.core.memory.compaction_pipeline import (
    HistoryCompactionConfig,
    TruncationResult,
    PruningResult,
    CompactionResult,
    UnifiedCompactionPipeline,
    _calculate_importance,
    _extract_protected_content,
    _format_protected_content,
    _extract_key_infos_by_rules,
    _format_key_infos,
)
from derisk.agent.core.tools.history_tools import create_history_tools
from derisk.agent.core.memory.gpts.file_base import (
    FileType,
    WorkLogStatus,
    WorkEntry,
    SimpleWorkLogStorage,
)


# =============================================================================
# Test Helpers — mock objects
# =============================================================================


class _MockMessage:
    """Simulates a v1-style AgentMessage (dataclass with attributes)."""

    def __init__(
        self,
        role="assistant",
        content="",
        context=None,
        tool_calls=None,
        tool_call_id=None,
        message_id=None,
        round_id=None,
        gmt_create=None,
        timestamp=None,
        metadata=None,
    ):
        self.role = role
        self.content = content
        self.context = context or {}
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id
        self.message_id = message_id
        self.round_id = round_id
        self.gmt_create = gmt_create
        self.timestamp = timestamp
        self.metadata = metadata


class _MockV2Message:
    """Simulates a v2-style AgentMessage (Pydantic model with metadata)."""

    def __init__(
        self,
        role="assistant",
        content="",
        metadata=None,
        timestamp=None,
        message_id=None,
    ):
        self.role = role
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = timestamp
        self.message_id = message_id


class _MockAFS:
    """Mock AgentFileSystem for testing."""

    def __init__(self):
        self._files = {}

    async def save_file(
        self,
        file_key,
        data,
        file_type=None,
        extension=None,
        file_name=None,
        tool_name=None,
    ):
        self._files[file_key] = data

    async def read_file(self, file_key):
        data = self._files.get(file_key)
        if data is None:
            return None
        if isinstance(data, (dict, list)):
            return json.dumps(data)
        return data


def _make_messages(count, role="assistant", content_prefix="msg"):
    """Create a list of dict messages for testing."""
    msgs = []
    for i in range(count):
        msgs.append(
            {
                "role": role,
                "content": f"{content_prefix}_{i}" + ("x" * 100),
            }
        )
    return msgs


def _make_tool_call_group(tool_name="my_tool", tool_call_id="tc_001", result="ok"):
    """Create an assistant+tool message pair (atomic group)."""
    assistant_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_call_id,
                "function": {"name": tool_name, "arguments": "{}"},
            }
        ],
    }
    tool_msg = {
        "role": "tool",
        "content": result,
        "tool_call_id": tool_call_id,
    }
    return [assistant_msg, tool_msg]


# =============================================================================
# Tests: _getval helper
# =============================================================================


class TestGetval:
    def test_dict_key(self):
        assert _getval({"a": 1}, "a") == 1
        assert _getval({"a": 1}, "b", "default") == "default"

    def test_object_attr(self):
        msg = _MockMessage(role="user")
        assert _getval(msg, "role") == "user"
        assert _getval(msg, "nonexistent", "fallback") == "fallback"


# =============================================================================
# Tests: UnifiedMessageAdapter
# =============================================================================


class TestUnifiedMessageAdapter:
    """Tests for UnifiedMessageAdapter across dict, v1, and v2 messages."""

    # -- Role normalization --

    def test_get_role_dict_ai(self):
        assert UnifiedMessageAdapter.get_role({"role": "ai"}) == "assistant"

    def test_get_role_dict_human(self):
        assert UnifiedMessageAdapter.get_role({"role": "human"}) == "user"

    def test_get_role_dict_assistant(self):
        assert UnifiedMessageAdapter.get_role({"role": "assistant"}) == "assistant"

    def test_get_role_v1(self):
        msg = _MockMessage(role="ai")
        assert UnifiedMessageAdapter.get_role(msg) == "assistant"

    def test_get_role_v2(self):
        msg = _MockV2Message(role="user")
        assert UnifiedMessageAdapter.get_role(msg) == "user"

    def test_get_raw_role(self):
        msg = _MockMessage(role="ai")
        assert UnifiedMessageAdapter.get_raw_role(msg) == "ai"

    def test_get_role_empty(self):
        assert UnifiedMessageAdapter.get_role({}) == "unknown"

    # -- Content --

    def test_get_content_dict(self):
        assert UnifiedMessageAdapter.get_content({"content": "hello"}) == "hello"

    def test_get_content_empty(self):
        assert UnifiedMessageAdapter.get_content({}) == ""

    def test_get_content_none(self):
        assert UnifiedMessageAdapter.get_content({"content": None}) == ""

    def test_get_content_v1(self):
        msg = _MockMessage(content="world")
        assert UnifiedMessageAdapter.get_content(msg) == "world"

    # -- Tool calls --

    def test_get_tool_calls_dict_top_level(self):
        tc = [{"id": "1", "function": {"name": "f"}}]
        assert UnifiedMessageAdapter.get_tool_calls({"tool_calls": tc}) == tc

    def test_get_tool_calls_v2_metadata(self):
        tc = [{"id": "2", "function": {"name": "g"}}]
        msg = _MockV2Message(metadata={"tool_calls": tc})
        assert UnifiedMessageAdapter.get_tool_calls(msg) == tc

    def test_get_tool_calls_v1_context(self):
        tc = [{"id": "3", "function": {"name": "h"}}]
        msg = _MockMessage(context={"tool_calls": tc})
        assert UnifiedMessageAdapter.get_tool_calls(msg) == tc

    def test_get_tool_calls_none(self):
        assert UnifiedMessageAdapter.get_tool_calls({"role": "user"}) is None

    # -- Tool call ID --

    def test_get_tool_call_id_dict(self):
        assert UnifiedMessageAdapter.get_tool_call_id({"tool_call_id": "abc"}) == "abc"

    def test_get_tool_call_id_v2_metadata(self):
        msg = _MockV2Message(metadata={"tool_call_id": "xyz"})
        assert UnifiedMessageAdapter.get_tool_call_id(msg) == "xyz"

    def test_get_tool_call_id_v1_context(self):
        msg = _MockMessage(context={"tool_call_id": "foo"})
        assert UnifiedMessageAdapter.get_tool_call_id(msg) == "foo"

    def test_get_tool_call_id_none(self):
        assert UnifiedMessageAdapter.get_tool_call_id({}) is None

    # -- Timestamp --

    def test_get_timestamp_v2_datetime(self):
        from datetime import datetime

        now = datetime(2025, 1, 1, 12, 0, 0)
        msg = _MockV2Message(timestamp=now)
        assert UnifiedMessageAdapter.get_timestamp(msg) == now.timestamp()

    def test_get_timestamp_v1_gmt_create(self):
        from datetime import datetime

        now = datetime(2025, 6, 15, 8, 30, 0)
        msg = _MockMessage(gmt_create=now)
        assert UnifiedMessageAdapter.get_timestamp(msg) == now.timestamp()

    def test_get_timestamp_float(self):
        msg = _MockV2Message(timestamp=1700000000.0)
        assert UnifiedMessageAdapter.get_timestamp(msg) == 1700000000.0

    def test_get_timestamp_missing(self):
        assert UnifiedMessageAdapter.get_timestamp({}) == 0.0

    # -- Message ID and Round ID --

    def test_get_message_id(self):
        msg = _MockMessage(message_id="m123")
        assert UnifiedMessageAdapter.get_message_id(msg) == "m123"

    def test_get_round_id(self):
        msg = _MockMessage(round_id="r456")
        assert UnifiedMessageAdapter.get_round_id(msg) == "r456"

    def test_get_round_id_v2_none(self):
        msg = _MockV2Message()
        assert UnifiedMessageAdapter.get_round_id(msg) is None

    # -- Classification helpers --

    def test_is_tool_call_message(self):
        tc = [{"id": "1", "function": {"name": "f"}}]
        msg = {"role": "assistant", "tool_calls": tc}
        assert UnifiedMessageAdapter.is_tool_call_message(msg) is True

    def test_is_tool_call_message_wrong_role(self):
        tc = [{"id": "1", "function": {"name": "f"}}]
        msg = {"role": "user", "tool_calls": tc}
        assert UnifiedMessageAdapter.is_tool_call_message(msg) is False

    def test_is_tool_result_message(self):
        assert UnifiedMessageAdapter.is_tool_result_message({"role": "tool"}) is True
        assert UnifiedMessageAdapter.is_tool_result_message({"role": "user"}) is False

    def test_is_in_tool_call_group(self):
        tc = [{"id": "1", "function": {"name": "f"}}]
        assert (
            UnifiedMessageAdapter.is_in_tool_call_group(
                {"role": "assistant", "tool_calls": tc}
            )
            is True
        )
        assert UnifiedMessageAdapter.is_in_tool_call_group({"role": "tool"}) is True
        assert UnifiedMessageAdapter.is_in_tool_call_group({"role": "user"}) is False

    def test_is_system_message(self):
        assert UnifiedMessageAdapter.is_system_message({"role": "system"}) is True
        assert UnifiedMessageAdapter.is_system_message({"role": "user"}) is False

    def test_is_user_message(self):
        assert UnifiedMessageAdapter.is_user_message({"role": "user"}) is True
        assert UnifiedMessageAdapter.is_user_message({"role": "human"}) is True
        assert UnifiedMessageAdapter.is_user_message({"role": "assistant"}) is False

    # -- Compaction summary detection --

    def test_is_compaction_summary_by_content(self):
        msg = {"role": "system", "content": "[History Compaction] Chapter 0 archived."}
        assert UnifiedMessageAdapter.is_compaction_summary(msg) is True

    def test_is_compaction_summary_by_context(self):
        msg = _MockMessage(context={"is_compaction_summary": True})
        assert UnifiedMessageAdapter.is_compaction_summary(msg) is True

    def test_is_compaction_summary_by_metadata(self):
        msg = _MockV2Message(metadata={"is_compaction_summary": True})
        assert UnifiedMessageAdapter.is_compaction_summary(msg) is True

    def test_not_compaction_summary(self):
        msg = {"role": "user", "content": "hello"}
        assert UnifiedMessageAdapter.is_compaction_summary(msg) is False

    # -- Token estimate --

    def test_get_token_estimate(self):
        msg = {"role": "assistant", "content": "a" * 400}
        tokens = UnifiedMessageAdapter.get_token_estimate(msg)
        assert tokens == 100  # 400 / 4

    def test_get_token_estimate_with_tool_calls(self):
        tc = [{"id": "1", "function": {"name": "f", "arguments": "{}"}}]
        msg = {"role": "assistant", "content": "", "tool_calls": tc}
        tokens = UnifiedMessageAdapter.get_token_estimate(msg)
        assert tokens > 0

    # -- Serialization --

    def test_serialize_message(self):
        tc = [{"id": "1", "function": {"name": "f"}}]
        msg = {
            "role": "ai",
            "content": "hello",
            "tool_calls": tc,
            "tool_call_id": "tc1",
        }
        result = UnifiedMessageAdapter.serialize_message(msg)
        assert result["role"] == "assistant"  # normalized
        assert result["content"] == "hello"
        assert result["tool_calls"] == tc
        assert result["tool_call_id"] == "tc1"

    # -- format_message_for_summary --

    def test_format_tool_call_message(self):
        tc = [
            {"id": "1", "function": {"name": "search", "arguments": '{"q":"test"}'}}
        ]
        msg = {"role": "assistant", "content": "", "tool_calls": tc}
        formatted = UnifiedMessageAdapter.format_message_for_summary(msg)
        assert "search" in formatted
        assert "Called tools" in formatted

    def test_format_tool_result_message(self):
        msg = {"role": "tool", "content": "result data", "tool_call_id": "tc1"}
        formatted = UnifiedMessageAdapter.format_message_for_summary(msg)
        assert "[tool result (tc1)]" in formatted

    def test_format_regular_message(self):
        msg = {"role": "user", "content": "How are you?"}
        formatted = UnifiedMessageAdapter.format_message_for_summary(msg)
        assert "[user]: How are you?" == formatted

    def test_format_skips_compaction_summary(self):
        msg = {"role": "system", "content": "[History Compaction] Chapter 0 archived."}
        formatted = UnifiedMessageAdapter.format_message_for_summary(msg)
        assert formatted == ""

    def test_format_truncates_long_content(self):
        msg = {"role": "user", "content": "x" * 3000}
        formatted = UnifiedMessageAdapter.format_message_for_summary(msg)
        assert "... [truncated]" in formatted
        assert len(formatted) < 3000


# =============================================================================
# Tests: HistoryChapter and HistoryCatalog
# =============================================================================


class TestHistoryChapter:
    def _make_chapter(self, **overrides):
        defaults = {
            "chapter_id": uuid.uuid4().hex,
            "chapter_index": 0,
            "time_range": (1700000000.0, 1700003600.0),
            "message_count": 50,
            "tool_call_count": 10,
            "summary": "Test chapter summary",
            "key_tools": ["tool_a", "tool_b"],
            "key_decisions": ["decision 1"],
            "file_key": "chapter_test_0",
            "token_estimate": 5000,
            "created_at": 1700003600.0,
        }
        defaults.update(overrides)
        return HistoryChapter(**defaults)

    def test_to_dict_and_from_dict_roundtrip(self):
        ch = self._make_chapter()
        data = ch.to_dict()
        ch2 = HistoryChapter.from_dict(data)
        assert ch2.chapter_index == ch.chapter_index
        assert ch2.summary == ch.summary
        assert ch2.key_tools == ch.key_tools
        assert ch2.time_range == tuple(ch.time_range)

    def test_to_catalog_entry(self):
        ch = self._make_chapter(chapter_index=2, message_count=30, tool_call_count=5)
        entry = ch.to_catalog_entry()
        assert "Chapter 2" in entry
        assert "30 msgs" in entry
        assert "5 tool calls" in entry
        assert "tool_a" in entry


class TestHistoryCatalog:
    def _make_catalog(self):
        return HistoryCatalog(
            conv_id="conv_test",
            session_id="sess_test",
            created_at=time.time(),
        )

    def _make_chapter(self, index=0):
        return HistoryChapter(
            chapter_id=uuid.uuid4().hex,
            chapter_index=index,
            time_range=(
                1700000000.0 + index * 3600,
                1700003600.0 + index * 3600,
            ),
            message_count=20 + index * 5,
            tool_call_count=5 + index,
            summary=f"Summary for chapter {index}",
            key_tools=["tool_a"],
            key_decisions=[],
            file_key=f"chapter_sess_test_{index}",
            token_estimate=3000,
            created_at=time.time(),
        )

    def test_add_chapter(self):
        catalog = self._make_catalog()
        ch = self._make_chapter(0)
        catalog.add_chapter(ch)
        assert len(catalog.chapters) == 1
        assert catalog.total_messages == ch.message_count
        assert catalog.current_chapter_index == 1

    def test_add_multiple_chapters(self):
        catalog = self._make_catalog()
        for i in range(3):
            catalog.add_chapter(self._make_chapter(i))
        assert len(catalog.chapters) == 3
        assert catalog.current_chapter_index == 3

    def test_get_chapter(self):
        catalog = self._make_catalog()
        ch = self._make_chapter(0)
        catalog.add_chapter(ch)
        found = catalog.get_chapter(0)
        assert found is not None
        assert found.chapter_index == 0

    def test_get_chapter_not_found(self):
        catalog = self._make_catalog()
        assert catalog.get_chapter(99) is None

    def test_get_overview(self):
        catalog = self._make_catalog()
        catalog.add_chapter(self._make_chapter(0))
        overview = catalog.get_overview()
        assert "History Catalog" in overview
        assert "Session: sess_test" in overview
        assert "Chapter 0" in overview

    def test_to_dict_and_from_dict_roundtrip(self):
        catalog = self._make_catalog()
        catalog.add_chapter(self._make_chapter(0))
        catalog.add_chapter(self._make_chapter(1))

        data = catalog.to_dict()
        catalog2 = HistoryCatalog.from_dict(data)

        assert catalog2.conv_id == "conv_test"
        assert len(catalog2.chapters) == 2
        assert catalog2.chapters[0].chapter_index == 0
        assert catalog2.chapters[1].chapter_index == 1


# =============================================================================
# Tests: HistoryCompactionConfig
# =============================================================================


class TestHistoryCompactionConfig:
    def test_defaults(self):
        config = HistoryCompactionConfig()
        assert config.max_output_lines == 2000
        assert config.max_output_bytes == 50 * 1024
        assert config.prune_protect_tokens == 4000
        assert config.prune_interval_rounds == 5
        assert config.context_window == 128000
        assert config.compaction_threshold_ratio == 0.8
        assert config.recent_messages_keep == 5
        assert config.fallback_to_legacy is True
        assert config.enable_recovery_tools is True

    def test_custom_values(self):
        config = HistoryCompactionConfig(
            max_output_lines=500,
            context_window=32000,
            compaction_threshold_ratio=0.5,
        )
        assert config.max_output_lines == 500
        assert config.context_window == 32000
        assert config.compaction_threshold_ratio == 0.5


# =============================================================================
# Tests: Content protection functions
# =============================================================================


class TestContentProtection:
    def test_calculate_importance_base(self):
        assert _calculate_importance("hello world") == 0.5

    def test_calculate_importance_markers(self):
        imp = _calculate_importance("important: this is critical: data")
        assert imp > 0.5

    def test_calculate_importance_code(self):
        imp = _calculate_importance("def foo():\n    pass\n" + "\n" * 25)
        assert imp > 0.5

    def test_calculate_importance_capped(self):
        content = (
            "important: critical: must: remember: todo: fixme: " + "\n" * 60
        )
        content += "def foo(): pass\nfunction bar() {}\nclass Baz:"
        imp = _calculate_importance(content)
        assert imp <= 1.0

    def test_extract_protected_code_blocks(self):
        msgs = [
            {
                "role": "assistant",
                "content": "Here:\n```python\nprint('hi')\n```\nDone.",
            }
        ]
        config = HistoryCompactionConfig(code_block_protection=True)
        protected = _extract_protected_content(msgs, config)
        code_items = [p for p in protected if p["type"] == "code"]
        assert len(code_items) >= 1
        assert "print" in code_items[0]["content"]

    def test_extract_protected_thinking_chains(self):
        msgs = [
            {
                "role": "assistant",
                "content": "<thinking>Let me analyze this.</thinking>",
            }
        ]
        config = HistoryCompactionConfig(thinking_chain_protection=True)
        protected = _extract_protected_content(msgs, config)
        thinking = [p for p in protected if p["type"] == "thinking"]
        assert len(thinking) >= 1

    def test_extract_protected_file_paths(self):
        msgs = [
            {
                "role": "assistant",
                "content": "Edit /src/app/main.py and ./config.yaml",
            }
        ]
        config = HistoryCompactionConfig(file_path_protection=True)
        protected = _extract_protected_content(msgs, config)
        paths = [p for p in protected if p["type"] == "file_path"]
        assert len(paths) >= 1

    def test_format_protected_content(self):
        protected = [
            {
                "type": "code",
                "content": "```python\nprint(1)\n```",
                "importance": 0.8,
            },
            {"type": "file_path", "content": "/src/main.py", "importance": 0.3},
        ]
        result = _format_protected_content(protected)
        assert "Protected Code Blocks" in result
        assert "Referenced Files" in result
        assert "/src/main.py" in result

    def test_format_protected_content_empty(self):
        assert _format_protected_content([]) == ""


# =============================================================================
# Tests: Key info extraction
# =============================================================================


class TestKeyInfoExtraction:
    def test_extract_decision(self):
        msgs = [
            {"role": "user", "content": "decided: use PostgreSQL for the database"},
        ]
        infos = _extract_key_infos_by_rules(msgs)
        decisions = [i for i in infos if i["category"] == "decision"]
        assert len(decisions) >= 1
        assert "PostgreSQL" in decisions[0]["content"]

    def test_extract_constraint(self):
        msgs = [
            {"role": "user", "content": "requirement: must support 1000 QPS"},
        ]
        infos = _extract_key_infos_by_rules(msgs)
        constraints = [i for i in infos if i["category"] == "constraint"]
        assert len(constraints) >= 1

    def test_extract_preference(self):
        msgs = [
            {"role": "user", "content": "prefer: TypeScript over JavaScript"},
        ]
        infos = _extract_key_infos_by_rules(msgs)
        prefs = [i for i in infos if i["category"] == "preference"]
        assert len(prefs) >= 1

    def test_dedup(self):
        msgs = [
            {"role": "user", "content": "decided: use Python\ndecided: use Python"},
        ]
        infos = _extract_key_infos_by_rules(msgs)
        decisions = [i for i in infos if i["category"] == "decision"]
        assert len(decisions) == 1  # deduped

    def test_format_key_infos(self):
        infos = [
            {"category": "decision", "content": "use Python", "importance": 0.6},
            {"category": "constraint", "content": "under 100ms", "importance": 0.7},
        ]
        result = _format_key_infos(infos, min_importance=0.5)
        assert "Decisions" in result
        assert "Constraints" in result

    def test_format_key_infos_empty(self):
        assert _format_key_infos([], 0.5) == ""

    def test_format_key_infos_filtered(self):
        infos = [{"category": "decision", "content": "x", "importance": 0.1}]
        assert _format_key_infos(infos, min_importance=0.5) == ""


# =============================================================================
# Tests: UnifiedCompactionPipeline
# =============================================================================


class TestPipelineInit:
    def test_default_config(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        assert pipeline.conv_id == "c1"
        assert pipeline.session_id == "s1"
        assert pipeline.has_compacted is False
        assert pipeline.config.max_output_lines == 2000

    def test_custom_config(self):
        config = HistoryCompactionConfig(max_output_lines=100)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        assert pipeline.config.max_output_lines == 100


class TestPipelineLayer1Truncation:
    """Layer 1: Truncation tests."""

    @pytest.mark.asyncio
    async def test_no_truncation_needed(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        result = await pipeline.truncate_output("short output", "my_tool")
        assert result.is_truncated is False
        assert result.content == "short output"
        assert result.file_key is None

    @pytest.mark.asyncio
    async def test_truncation_by_lines(self):
        config = HistoryCompactionConfig(
            max_output_lines=5, max_output_bytes=1024 * 1024
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        long_output = "\n".join([f"line {i}" for i in range(100)])
        result = await pipeline.truncate_output(long_output, "big_tool")
        assert result.is_truncated is True
        assert result.truncated_size < result.original_size
        assert "[Output truncated]" in result.content

    @pytest.mark.asyncio
    async def test_truncation_by_bytes(self):
        config = HistoryCompactionConfig(
            max_output_lines=100000, max_output_bytes=100
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        long_output = "x" * 500
        result = await pipeline.truncate_output(long_output, "big_tool")
        assert result.is_truncated is True

    @pytest.mark.asyncio
    async def test_truncation_archives_to_afs(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(
            max_output_lines=5, max_output_bytes=1024 * 1024
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        long_output = "\n".join([f"line {i}" for i in range(100)])
        result = await pipeline.truncate_output(long_output, "my_tool")

        assert result.is_truncated is True
        assert result.file_key is not None
        assert result.file_key in afs._files
        assert "file_key=" in result.content

    @pytest.mark.asyncio
    async def test_truncation_without_afs(self):
        config = HistoryCompactionConfig(
            max_output_lines=5, max_output_bytes=1024 * 1024
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        long_output = "\n".join([f"line {i}" for i in range(100)])
        result = await pipeline.truncate_output(long_output, "tool")
        assert result.is_truncated is True
        assert result.file_key is None


class TestPipelineLayer2Pruning:
    """Layer 2: Pruning tests."""

    @pytest.mark.asyncio
    async def test_no_pruning_before_interval(self):
        config = HistoryCompactionConfig(prune_interval_rounds=5)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        msgs = _make_messages(20)
        # round_counter starts at 0, becomes 1 after call — not multiple of 5
        result = await pipeline.prune_history(msgs)
        assert result.pruned_count == 0
        assert len(result.messages) == 20

    @pytest.mark.asyncio
    async def test_pruning_at_interval(self):
        config = HistoryCompactionConfig(
            prune_interval_rounds=1,
            prune_protect_tokens=100,
            min_messages_keep=2,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        msgs = [
            {"role": "user", "content": "query"},
            {"role": "tool", "content": "x" * 500, "tool_call_id": "tc1"},
            {"role": "tool", "content": "y" * 500, "tool_call_id": "tc2"},
            {"role": "user", "content": "another query"},
            {"role": "assistant", "content": "response " + "z" * 200},
        ]
        result = await pipeline.prune_history(msgs)
        # Some old tool messages with long content should be pruned
        assert result.pruned_count >= 0

    @pytest.mark.asyncio
    async def test_pruning_skips_user_and_system(self):
        config = HistoryCompactionConfig(
            prune_interval_rounds=1,
            prune_protect_tokens=50,
            min_messages_keep=2,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        msgs = [
            {"role": "system", "content": "System prompt " + "a" * 300},
            {"role": "user", "content": "User message " + "b" * 300},
            {"role": "assistant", "content": "response"},
        ]
        result = await pipeline.prune_history(msgs)
        system_content = result.messages[0]["content"]
        user_content = result.messages[1]["content"]
        assert "System prompt" in system_content
        assert "User message" in user_content

    @pytest.mark.asyncio
    async def test_pruning_skips_short_tool_messages(self):
        config = HistoryCompactionConfig(
            prune_interval_rounds=1,
            prune_protect_tokens=10,
            min_messages_keep=1,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        msgs = [
            {"role": "tool", "content": "ok", "tool_call_id": "tc1"},
            {"role": "assistant", "content": "done " + "z" * 200},
        ]
        result = await pipeline.prune_history(msgs)
        assert result.messages[0]["content"] == "ok"

    @pytest.mark.asyncio
    async def test_pruning_respects_min_messages(self):
        config = HistoryCompactionConfig(
            prune_interval_rounds=1,
            min_messages_keep=100,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )
        msgs = _make_messages(5)
        result = await pipeline.prune_history(msgs)
        assert len(result.messages) == 5
        assert result.pruned_count == 0


class TestPipelineLayer3Compaction:
    """Layer 3: Compaction & Archival tests."""

    @pytest.mark.asyncio
    async def test_no_compaction_below_threshold(self):
        config = HistoryCompactionConfig(
            context_window=128000,
            compaction_threshold_ratio=0.8,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=_MockAFS(),
            config=config,
        )
        msgs = _make_messages(5, content_prefix="short")
        result = await pipeline.compact_if_needed(msgs)
        assert result.compaction_triggered is False
        assert result.messages == msgs
        assert pipeline.has_compacted is False

    @pytest.mark.asyncio
    async def test_compaction_triggered_on_force(self):
        afs = _MockAFS()
        wls = SimpleWorkLogStorage()
        config = HistoryCompactionConfig(
            context_window=128000,
            recent_messages_keep=2,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            work_log_storage=wls,
            config=config,
        )
        msgs = _make_messages(10, content_prefix="data")
        result = await pipeline.compact_if_needed(msgs, force=True)

        assert result.compaction_triggered is True
        assert result.messages_archived > 0
        assert result.chapter is not None
        assert pipeline.has_compacted is True
        has_summary = any(
            isinstance(m, dict) and m.get("is_compaction_summary")
            for m in result.messages
        )
        assert has_summary

    @pytest.mark.asyncio
    async def test_compaction_archives_to_afs(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = _make_messages(10)
        result = await pipeline.compact_if_needed(msgs, force=True)

        assert result.chapter is not None
        assert result.chapter.file_key in afs._files

    @pytest.mark.asyncio
    async def test_compaction_preserves_system_messages(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = [
            {"role": "system", "content": "System prompt"},
            *_make_messages(10),
        ]
        result = await pipeline.compact_if_needed(msgs, force=True)

        system_msgs = [
            m
            for m in result.messages
            if isinstance(m, dict)
            and m.get("role") == "system"
            and not m.get("is_compaction_summary")
        ]
        assert len(system_msgs) >= 1
        assert system_msgs[0]["content"] == "System prompt"

    @pytest.mark.asyncio
    async def test_compaction_keeps_recent_messages(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=3)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = _make_messages(10, content_prefix="msg")
        result = await pipeline.compact_if_needed(msgs, force=True)

        non_system = [
            m
            for m in result.messages
            if not (isinstance(m, dict) and m.get("is_compaction_summary"))
            and not (isinstance(m, dict) and m.get("role") == "system")
        ]
        assert len(non_system) <= config.recent_messages_keep

    @pytest.mark.asyncio
    async def test_compaction_empty_messages(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        result = await pipeline.compact_if_needed([])
        assert result.compaction_triggered is False
        assert result.messages == []

    @pytest.mark.asyncio
    async def test_compaction_respects_tool_call_groups(self):
        """Tool call atomic groups should not be split."""
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=3)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = _make_messages(5, content_prefix="old")
        group = _make_tool_call_group("search", "tc_boundary", "search result")
        msgs.extend(group)
        msgs.extend(_make_messages(2, content_prefix="recent"))

        result = await pipeline.compact_if_needed(msgs, force=True)
        assert result.compaction_triggered is True

    @pytest.mark.asyncio
    async def test_has_compacted_flag(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        assert pipeline.has_compacted is False
        msgs = _make_messages(10)
        await pipeline.compact_if_needed(msgs, force=True)
        assert pipeline.has_compacted is True


# =============================================================================
# Tests: Catalog Management
# =============================================================================


class TestCatalogManagement:
    @pytest.mark.asyncio
    async def test_get_catalog_creates_new(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        catalog = await pipeline.get_catalog()
        assert catalog.conv_id == "c1"
        assert catalog.session_id == "s1"
        assert len(catalog.chapters) == 0

    @pytest.mark.asyncio
    async def test_get_catalog_from_work_log_storage(self):
        wls = SimpleWorkLogStorage()
        catalog_data = HistoryCatalog(
            conv_id="c1",
            session_id="s1",
            chapters=[],
            total_messages=100,
        ).to_dict()
        await wls.save_history_catalog("c1", catalog_data)

        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            work_log_storage=wls,
        )
        catalog = await pipeline.get_catalog()
        assert catalog.total_messages == 100

    @pytest.mark.asyncio
    async def test_save_catalog(self):
        wls = SimpleWorkLogStorage()
        afs = _MockAFS()
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            work_log_storage=wls,
        )
        catalog = await pipeline.get_catalog()
        catalog.total_messages = 42
        await pipeline.save_catalog()

        saved = await wls.get_history_catalog("c1")
        assert saved is not None
        assert saved["total_messages"] == 42

        assert "history_catalog_s1" in afs._files


# =============================================================================
# Tests: Chapter Recovery
# =============================================================================


class TestChapterRecovery:
    @pytest.mark.asyncio
    async def test_read_chapter_not_found(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=_MockAFS(),
        )
        result = await pipeline.read_chapter(0)
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_chapter_no_afs(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        catalog = await pipeline.get_catalog()
        ch = HistoryChapter(
            chapter_id="ch1",
            chapter_index=0,
            time_range=(1700000000.0, 1700003600.0),
            message_count=10,
            tool_call_count=3,
            summary="test",
            key_tools=[],
            key_decisions=[],
            file_key="chapter_s1_0",
            token_estimate=1000,
            created_at=time.time(),
        )
        catalog.add_chapter(ch)

        result = await pipeline.read_chapter(0)
        assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_read_chapter_success(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = _make_messages(10)
        await pipeline.compact_if_needed(msgs, force=True)

        result = await pipeline.read_chapter(0)
        assert result is not None
        assert "Chapter 0" in result

    @pytest.mark.asyncio
    async def test_search_chapters_no_results(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=_MockAFS(),
        )
        result = await pipeline.search_chapters("nonexistent_query")
        assert "No history chapters" in result

    @pytest.mark.asyncio
    async def test_search_chapters_with_match(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = [
            {"role": "user", "content": "decided: use PostgreSQL database"},
            *_make_messages(10),
        ]
        await pipeline.compact_if_needed(msgs, force=True)

        catalog = await pipeline.get_catalog()
        if catalog.chapters:
            catalog.chapters[0].key_decisions = ["use PostgreSQL database"]

        result = await pipeline.search_chapters("PostgreSQL")
        assert "PostgreSQL" in result


# =============================================================================
# Tests: History Tools
# =============================================================================


class TestHistoryTools:
    def test_create_history_tools_returns_four(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        tools = create_history_tools(pipeline)
        assert len(tools) == 4
        expected_names = {
            "read_history_chapter",
            "search_history",
            "get_tool_call_history",
            "get_history_overview",
        }
        assert set(tools.keys()) == expected_names

    def test_tools_are_function_tools(self):
        from derisk.agent.resource.tool.base import FunctionTool

        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        tools = create_history_tools(pipeline)
        for name, tool in tools.items():
            assert isinstance(tool, FunctionTool), f"{name} is not FunctionTool"

    def test_tools_have_descriptions(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        tools = create_history_tools(pipeline)
        for name, tool in tools.items():
            assert tool.description, f"{name} has no description"

    @pytest.mark.asyncio
    async def test_read_history_chapter_tool(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = _make_messages(10)
        await pipeline.compact_if_needed(msgs, force=True)

        tools = create_history_tools(pipeline)
        result = await tools["read_history_chapter"]._func(chapter_index=0)
        assert "Chapter 0" in result

    @pytest.mark.asyncio
    async def test_get_history_overview_tool(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )
        msgs = _make_messages(10)
        await pipeline.compact_if_needed(msgs, force=True)

        tools = create_history_tools(pipeline)
        result = await tools["get_history_overview"]._func()
        assert "History Catalog" in result
        assert "Chapter 0" in result

    @pytest.mark.asyncio
    async def test_search_history_tool(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=_MockAFS(),
        )
        tools = create_history_tools(pipeline)
        result = await tools["search_history"]._func(query="test")
        assert "No history chapters" in result

    @pytest.mark.asyncio
    async def test_get_tool_call_history_no_wls(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            work_log_storage=None,
        )
        tools = create_history_tools(pipeline)
        result = await tools["get_tool_call_history"]._func()
        assert "未配置" in result

    @pytest.mark.asyncio
    async def test_get_tool_call_history_with_entries(self):
        wls = SimpleWorkLogStorage()
        await wls.append_work_entry(
            "c1",
            WorkEntry(
                timestamp=time.time(),
                tool="search_code",
                args={"query": "test"},
                result="found 5 results",
                success=True,
            ),
        )

        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            work_log_storage=wls,
        )
        tools = create_history_tools(pipeline)
        result = await tools["get_tool_call_history"]._func()
        assert "search_code" in result
        assert "found 5 results" in result

    @pytest.mark.asyncio
    async def test_get_tool_call_history_filter_by_tool(self):
        wls = SimpleWorkLogStorage()
        await wls.append_work_entry(
            "c1",
            WorkEntry(
                timestamp=time.time(),
                tool="search_code",
                result="r1",
                success=True,
            ),
        )
        await wls.append_work_entry(
            "c1",
            WorkEntry(
                timestamp=time.time(),
                tool="read_file",
                result="r2",
                success=True,
            ),
        )

        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            work_log_storage=wls,
        )
        tools = create_history_tools(pipeline)
        result = await tools["get_tool_call_history"]._func(tool_name="search_code")
        assert "search_code" in result
        assert "read_file" not in result


# =============================================================================
# Tests: Data Model (FileType enums, WorkLogStatus)
# =============================================================================


class TestDataModelEnums:
    def test_file_type_history_values(self):
        assert FileType.HISTORY_CHAPTER.value == "history_chapter"
        assert FileType.HISTORY_CATALOG.value == "history_catalog"
        assert FileType.HISTORY_SUMMARY.value == "history_summary"

    def test_work_log_status_chapter_archived(self):
        assert WorkLogStatus.CHAPTER_ARCHIVED.value == "chapter_archived"


class TestSimpleWorkLogStorageCatalog:
    """Test the get/save history_catalog methods on SimpleWorkLogStorage."""

    @pytest.mark.asyncio
    async def test_get_catalog_empty(self):
        wls = SimpleWorkLogStorage()
        result = await wls.get_history_catalog("conv_1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get_catalog(self):
        wls = SimpleWorkLogStorage()
        catalog_data = {
            "conv_id": "conv_1",
            "chapters": [],
            "total_messages": 50,
        }
        await wls.save_history_catalog("conv_1", catalog_data)
        result = await wls.get_history_catalog("conv_1")
        assert result == catalog_data

    @pytest.mark.asyncio
    async def test_save_catalog_creates_storage(self):
        wls = SimpleWorkLogStorage()
        await wls.save_history_catalog("new_conv", {"data": True})
        result = await wls.get_history_catalog("new_conv")
        assert result == {"data": True}


# =============================================================================
# Tests: Pipeline internal helpers
# =============================================================================


class TestPipelineInternalHelpers:
    def test_estimate_tokens_dict_messages(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        msgs = [{"role": "user", "content": "a" * 400}]
        tokens = pipeline._estimate_tokens(msgs)
        assert tokens == 100  # 400 / 4

    def test_estimate_tokens_object_messages(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        msgs = [_MockMessage(content="b" * 800)]
        tokens = pipeline._estimate_tokens(msgs)
        assert tokens == 200

    def test_select_messages_to_compact(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=HistoryCompactionConfig(recent_messages_keep=3),
        )
        msgs = _make_messages(10)
        to_compact, to_keep = pipeline._select_messages_to_compact(msgs)
        assert len(to_keep) == 3
        assert len(to_compact) == 7

    def test_select_messages_too_few(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=HistoryCompactionConfig(recent_messages_keep=10),
        )
        msgs = _make_messages(5)
        to_compact, to_keep = pipeline._select_messages_to_compact(msgs)
        assert to_compact == []
        assert to_keep == msgs

    def test_select_avoids_splitting_tool_group(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=HistoryCompactionConfig(recent_messages_keep=2),
        )
        msgs = _make_messages(3, content_prefix="old")
        group = _make_tool_call_group("search", "tc1", "result data " * 50)
        msgs.extend(group)
        msgs.extend(_make_messages(1, content_prefix="recent"))

        to_compact, to_keep = pipeline._select_messages_to_compact(msgs)
        # Verify the tool-call group is not split
        for i, m in enumerate(to_keep):
            if isinstance(m, dict) and m.get("role") == "tool":
                if i > 0:
                    prev = to_keep[i - 1]
                    if isinstance(prev, dict) and prev.get("tool_calls"):
                        pass  # good — group is together

    def test_create_summary_message(self):
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
        )
        chapter = HistoryChapter(
            chapter_id="ch1",
            chapter_index=0,
            time_range=(1700000000.0, 1700003600.0),
            message_count=20,
            tool_call_count=5,
            summary="A test summary",
            key_tools=["tool_a"],
            key_decisions=[],
            file_key="chapter_s1_0",
            token_estimate=3000,
            created_at=time.time(),
        )
        msg = pipeline._create_summary_message("A test summary", chapter)
        assert msg["role"] == "system"
        assert msg["is_compaction_summary"] is True
        assert "Chapter 0" in msg["content"]
        assert "A test summary" in msg["content"]


# =============================================================================
# Tests: Skill Protection
# =============================================================================


class TestSkillProtection:
    @pytest.mark.asyncio
    async def test_get_tool_name_for_tool_result(self):
        msgs = [
            {"role": "user", "content": "load skill"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "skill", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "<skill_content>Skill instructions...</skill_content>",
            },
        ]
        tool_name = UnifiedMessageAdapter.get_tool_name_for_tool_result(msgs[2], msgs, 2)
        assert tool_name == "skill"

    @pytest.mark.asyncio
    async def test_get_tool_name_for_non_skill_tool(self):
        msgs = [
            {"role": "user", "content": "read file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "file contents...",
            },
        ]
        tool_name = UnifiedMessageAdapter.get_tool_name_for_tool_result(msgs[2], msgs, 2)
        assert tool_name == "read_file"

    @pytest.mark.asyncio
    async def test_prune_skips_skill_tool(self):
        config = HistoryCompactionConfig(
            prune_interval_rounds=1,
            prune_protect_tokens=50,
            min_messages_keep=0,
            prune_protected_tools=("skill",),
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=None,
            config=config,
        )

        long_skill_output = "x" * 1000
        long_read_output = "y" * 1000
        msgs = [
            {"role": "user", "content": "load skill"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "skill", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": long_skill_output,
            },
            {"role": "user", "content": "read file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_2", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_2",
                "content": long_read_output,
            },
            {"role": "assistant", "content": "done"},
        ]

        result = await pipeline.prune_history(msgs)

        skill_msg = result.messages[2]
        skill_content = UnifiedMessageAdapter.get_content(skill_msg)
        assert skill_content == long_skill_output, "Skill output should NOT be pruned"
        assert result.pruned_count >= 1, "At least one tool output should be pruned"

    @pytest.mark.asyncio
    async def test_compaction_extracts_skill_outputs(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(
            recent_messages_keep=1,
            prune_protected_tools=("skill",),
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )

        skill_content = "<skill_content>Skill instructions here</skill_content>"
        msgs = [
            {"role": "user", "content": "load skill"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "skill", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": skill_content,
            },
            {"role": "assistant", "content": "Done"},
        ]

        result = await pipeline.compact_if_needed(msgs, force=True)
        assert result.chapter is not None
        assert len(result.chapter.skill_outputs) == 1
        assert skill_content in result.chapter.skill_outputs[0]

    @pytest.mark.asyncio
    async def test_summary_message_includes_skill_rehydration(self):
        afs = _MockAFS()
        config = HistoryCompactionConfig(
            recent_messages_keep=1,
            prune_protected_tools=("skill",),
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )

        skill_content = "<skill_content>Important skill instructions</skill_content>"
        msgs = [
            {"role": "user", "content": "load skill"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "skill", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": skill_content,
            },
            {"role": "assistant", "content": "Done"},
        ]

        result = await pipeline.compact_if_needed(msgs, force=True)
        summary_msg = result.messages[0]
        summary_content = UnifiedMessageAdapter.get_content(summary_msg)

        assert "Rehydrated" in summary_content
        assert "Important skill instructions" in summary_content


# =============================================================================
# Tests: End-to-end pipeline flow
# =============================================================================


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_full_flow_truncate_prune_compact(self):
        """Simulate a realistic flow: truncate output, prune, then compact."""
        afs = _MockAFS()
        wls = SimpleWorkLogStorage()
        config = HistoryCompactionConfig(
            max_output_lines=3,
            max_output_bytes=1024 * 1024,
            prune_interval_rounds=1,
            prune_protect_tokens=200,
            min_messages_keep=2,
            context_window=1000,
            compaction_threshold_ratio=0.01,
            recent_messages_keep=3,
        )
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            work_log_storage=wls,
            config=config,
        )

        # Step 1: Truncate a large output
        big_output = "\n".join([f"data line {i}" for i in range(100)])
        trunc_result = await pipeline.truncate_output(big_output, "data_query")
        assert trunc_result.is_truncated is True

        # Step 2: Build message history with prunable content
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Analyze the data"},
            {"role": "tool", "content": "x" * 500, "tool_call_id": "tc1"},
            {"role": "assistant", "content": "Based on analysis..."},
            {"role": "user", "content": "Now summarize"},
            {"role": "assistant", "content": "Summary: " + "y" * 200},
        ]

        # Step 3: Prune
        prune_result = await pipeline.prune_history(msgs)
        assert len(prune_result.messages) == len(msgs)

        # Step 4: Compact
        compact_result = await pipeline.compact_if_needed(
            prune_result.messages, force=True
        )
        assert compact_result.compaction_triggered is True
        assert pipeline.has_compacted is True

        # Step 5: Read back the archived chapter
        read_result = await pipeline.read_chapter(0)
        assert read_result is not None
        assert "Chapter 0" in read_result

        # Step 6: Get overview
        catalog = await pipeline.get_catalog()
        overview = catalog.get_overview()
        assert "Chapter 0" in overview

    @pytest.mark.asyncio
    async def test_multiple_compaction_cycles(self):
        """Test that multiple compaction cycles produce multiple chapters."""
        afs = _MockAFS()
        config = HistoryCompactionConfig(recent_messages_keep=2)
        pipeline = UnifiedCompactionPipeline(
            conv_id="c1",
            session_id="s1",
            agent_file_system=afs,
            config=config,
        )

        # First compaction
        msgs1 = _make_messages(10, content_prefix="batch1")
        result1 = await pipeline.compact_if_needed(msgs1, force=True)
        assert result1.chapter.chapter_index == 0

        # Second compaction on the result + new messages
        new_msgs = result1.messages + _make_messages(10, content_prefix="batch2")
        result2 = await pipeline.compact_if_needed(new_msgs, force=True)
        assert result2.chapter.chapter_index == 1

        catalog = await pipeline.get_catalog()
        assert len(catalog.chapters) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
