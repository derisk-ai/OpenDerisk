"""PR 7: ToolFailureTracker 单元测试。

覆盖：
- 连续失败计数 + 阈值熔断
- cooldown 过期后自动解除
- record_success 清空失败计数
- 不同工具独立计数
- FailureRecord 字段
- snapshot / reset
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from derisk.agent.core.tool_failure_tracker import (
    FailureRecord,
    ToolFailureTracker,
)


class TestRecordFailure:
    def test_single_failure_not_blocked(self):
        tracker = ToolFailureTracker(conv_id="c1", max_consecutive_failures=5)
        tracker.record_failure("execute_sql", "timeout")
        assert tracker.is_disabled("execute_sql") is False
        assert tracker.get_failure_count("execute_sql") == 1

    def test_below_threshold_not_blocked(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=5
        )
        for i in range(4):
            tracker.record_failure("execute_sql", f"err-{i}")
        assert tracker.is_disabled("execute_sql") is False
        assert tracker.get_failure_count("execute_sql") == 4

    def test_at_threshold_blocked(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=5
        )
        for i in range(5):
            tracker.record_failure("execute_sql", f"err-{i}")
        assert tracker.is_disabled("execute_sql") is True
        assert tracker.get_failure_count("execute_sql") == 5

    def test_above_threshold_blocked(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=5
        )
        for i in range(7):
            tracker.record_failure("execute_sql", f"err-{i}")
        assert tracker.is_disabled("execute_sql") is True

    def test_empty_tool_name_ignored(self):
        tracker = ToolFailureTracker(conv_id="c1")
        tracker.record_failure("", "err")
        assert tracker.get_failure_count("") == 0


class TestCooldownExpiry:
    def test_blocked_during_cooldown(self):
        tracker = ToolFailureTracker(
            conv_id="c1",
            max_consecutive_failures=3,
            cooldown_seconds=300,
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        assert tracker.is_disabled("t1") is True

    def test_block_lifted_after_cooldown(self):
        """cooldown 过期后 is_disabled 返回 False 并 lazy 清理。"""
        tracker = ToolFailureTracker(
            conv_id="c1",
            max_consecutive_failures=3,
            cooldown_seconds=300,
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        assert tracker.is_disabled("t1") is True

        # 推进时间到 cooldown 之后
        with patch(
            "derisk.agent.core.tool_failure_tracker.time.monotonic",
            return_value=time.monotonic() + 400,
        ):
            assert tracker.is_disabled("t1") is False
        # lazy 清理：失败记录被清空
        assert tracker.get_failure_count("t1") == 0

    def test_block_still_active_mid_cooldown(self):
        """cooldown 未过期时 is_disabled 仍返回 True。"""
        tracker = ToolFailureTracker(
            conv_id="c1",
            max_consecutive_failures=3,
            cooldown_seconds=300,
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        with patch(
            "derisk.agent.core.tool_failure_tracker.time.monotonic",
            return_value=time.monotonic() + 100,
        ):
            assert tracker.is_disabled("t1") is True


class TestRecordSuccess:
    def test_success_clears_failure_count(self):
        tracker = ToolFailureTracker(conv_id="c1", max_consecutive_failures=5)
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        assert tracker.get_failure_count("t1") == 3

        tracker.record_success("t1")
        assert tracker.get_failure_count("t1") == 0
        assert tracker.is_disabled("t1") is False

    def test_success_lifts_block(self):
        """成功后熔断解除（即使未到 cooldown 过期时间）。"""
        tracker = ToolFailureTracker(
            conv_id="c1",
            max_consecutive_failures=3,
            cooldown_seconds=300,
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        assert tracker.is_disabled("t1") is True

        tracker.record_success("t1")
        assert tracker.is_disabled("t1") is False

    def test_success_no_prior_failures_is_noop(self):
        tracker = ToolFailureTracker(conv_id="c1")
        tracker.record_success("t1")  # 不抛
        assert tracker.get_failure_count("t1") == 0

    def test_success_doesnt_touch_other_tools(self):
        tracker = ToolFailureTracker(conv_id="c1", max_consecutive_failures=3)
        for i in range(2):
            tracker.record_failure("t1", f"err-{i}")
            tracker.record_failure("t2", f"err-{i}")
        tracker.record_success("t1")
        assert tracker.get_failure_count("t1") == 0
        assert tracker.get_failure_count("t2") == 2


class TestIndependentTools:
    def test_different_tools_independent(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=3
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        # t1 熔断，t2 没事
        assert tracker.is_disabled("t1") is True
        assert tracker.is_disabled("t2") is False
        assert tracker.get_failure_count("t2") == 0

        tracker.record_failure("t2", "err")
        assert tracker.is_disabled("t2") is False
        assert tracker.get_failure_count("t2") == 1

    def test_get_disabled_tools_lists_all(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=2
        )
        for i in range(2):
            tracker.record_failure("t1", f"err-{i}")
            tracker.record_failure("t2", f"err-{i}")
        disabled = set(tracker.get_disabled_tools())
        assert disabled == {"t1", "t2"}

    def test_get_disabled_tools_excludes_expired(self):
        tracker = ToolFailureTracker(
            conv_id="c1",
            max_consecutive_failures=2,
            cooldown_seconds=100,
        )
        for i in range(2):
            tracker.record_failure("t1", f"err-{i}")
        for i in range(2):
            tracker.record_failure("t2", f"err-{i}")
        # 推进 t1 的 cooldown 过期
        with patch(
            "derisk.agent.core.tool_failure_tracker.time.monotonic",
            return_value=time.monotonic() + 200,
        ):
            disabled = set(tracker.get_disabled_tools())
        assert disabled == set()  # 两个都过期了


class TestFailureRecord:
    def test_record_has_timestamp_and_error(self):
        tracker = ToolFailureTracker(conv_id="c1")
        tracker.record_failure("t1", "timeout")
        last = tracker.get_last_failure("t1")
        assert last is not None
        assert isinstance(last, FailureRecord)
        assert last.tool_name == "t1"
        assert last.error == "timeout"
        assert last.timestamp > 0
        assert last.wall_time > 0

    def test_last_failure_returns_none_if_no_failures(self):
        tracker = ToolFailureTracker(conv_id="c1")
        assert tracker.get_last_failure("t1") is None


class TestReset:
    def test_reset_single_tool(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=3
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
            tracker.record_failure("t2", f"err-{i}")
        tracker.reset("t1")
        assert tracker.is_disabled("t1") is False
        assert tracker.is_disabled("t2") is True

    def test_reset_all(self):
        tracker = ToolFailureTracker(
            conv_id="c1", max_consecutive_failures=3
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
            tracker.record_failure("t2", f"err-{i}")
        tracker.reset()
        assert tracker.is_disabled("t1") is False
        assert tracker.is_disabled("t2") is False
        assert tracker.get_failure_count("t1") == 0


class TestSnapshot:
    def test_snapshot_structure(self):
        tracker = ToolFailureTracker(
            conv_id="c1",
            max_consecutive_failures=3,
            cooldown_seconds=120,
        )
        for i in range(3):
            tracker.record_failure("t1", f"err-{i}")
        snap = tracker.snapshot()
        assert snap["conv_id"] == "c1"
        assert snap["max_consecutive_failures"] == 3
        assert snap["cooldown_seconds"] == 120
        assert snap["failure_counts"] == {"t1": 3}
        assert len(snap["disabled_tools"]) == 1
        assert snap["disabled_tools"][0]["tool"] == "t1"
        assert snap["disabled_tools"][0]["disabled_until_remaining_s"] > 0

    def test_snapshot_no_failures(self):
        tracker = ToolFailureTracker(conv_id="c1")
        snap = tracker.snapshot()
        assert snap["failure_counts"] == {}
        assert snap["disabled_tools"] == []


class TestDefaults:
    def test_default_max_consecutive_failures_is_5(self):
        tracker = ToolFailureTracker(conv_id="c1")
        assert tracker.max_consecutive_failures == 5

    def test_default_cooldown_is_300s(self):
        tracker = ToolFailureTracker(conv_id="c1")
        assert tracker.cooldown_seconds == 300
