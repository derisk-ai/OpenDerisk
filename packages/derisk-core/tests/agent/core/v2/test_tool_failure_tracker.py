"""ToolFailureTracker 测试。"""
from derisk.agent.core.v2.tool_failure_tracker import ToolFailureTracker


def test_record_failure_below_threshold():
    tracker = ToolFailureTracker(max_failures=3)
    assert not tracker.record_failure("bash")  # 1 次
    assert not tracker.is_blocked("bash")


def test_record_failure_at_threshold():
    tracker = ToolFailureTracker(max_failures=3)
    tracker.record_failure("bash")
    tracker.record_failure("bash")
    assert tracker.record_failure("bash")  # 3 次，返回 True 表示达阈值
    assert tracker.is_blocked("bash")


def test_reset():
    tracker = ToolFailureTracker(max_failures=3)
    tracker.record_failure("bash")
    tracker.record_failure("bash")
    tracker.reset("bash")
    assert not tracker.is_blocked("bash")
    assert not tracker.record_failure("bash")  # 重新从 1 开始


def test_different_tools_independent():
    tracker = ToolFailureTracker(max_failures=3)
    tracker.record_failure("bash")
    tracker.record_failure("read")
    assert not tracker.is_blocked("bash")
    assert not tracker.is_blocked("read")


def test_default_max_failures():
    tracker = ToolFailureTracker()
    assert tracker._max_failures == 3
