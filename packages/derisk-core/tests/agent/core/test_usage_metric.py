"""PR 8: usage_metric 单元测试。

覆盖：
- estimate_cost 定价表查找（精确 / 前缀 / 未知）
- ConversationUsage.add_call 累加 + by_model/by_role 分组
- aggregate_usage_from_messages 从 metrics dict 提取 token 数
- aggregate_usage_from_messages 处理 metrics 是 str / dict / 对象
- format_usage_log
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from derisk.agent.core.usage_metric import (
    ConversationUsage,
    aggregate_usage_from_messages,
    estimate_cost,
    format_usage_log,
)


# ---------------- estimate_cost ----------------

class TestEstimateCost:
    def test_known_model_exact_match(self):
        # gpt-4o: 5.0 / 15.0 USD per 1M
        cost = estimate_cost("gpt-4o", prompt_tokens=1_000_000, completion_tokens=0)
        assert cost == pytest.approx(5.0)

    def test_known_model_prefix_match(self):
        # gpt-4o-2024-08-06 走前缀匹配到 gpt-4o
        cost = estimate_cost("gpt-4o-2024-08-06", prompt_tokens=1_000_000, completion_tokens=0)
        assert cost == pytest.approx(5.0)

    def test_completion_priced_separately(self):
        # gpt-4o: prompt 5.0, completion 15.0
        cost = estimate_cost("gpt-4o", prompt_tokens=0, completion_tokens=1_000_000)
        assert cost == pytest.approx(15.0)

    def test_combined_prompt_completion(self):
        cost = estimate_cost("gpt-4o", prompt_tokens=500_000, completion_tokens=500_000)
        # 0.5 * 5 + 0.5 * 15 = 2.5 + 7.5 = 10.0
        assert cost == pytest.approx(10.0)

    def test_unknown_model_zero_cost(self):
        assert estimate_cost("future-model-3000", prompt_tokens=1_000_000, completion_tokens=1_000_000) == 0.0

    def test_empty_model_name_zero_cost(self):
        assert estimate_cost("", prompt_tokens=1_000_000, completion_tokens=0) == 0.0

    def test_zero_tokens_zero_cost(self):
        assert estimate_cost("gpt-4o", prompt_tokens=0, completion_tokens=0) == 0.0

    def test_none_tokens_treated_as_zero(self):
        cost = estimate_cost("gpt-4o", prompt_tokens=None, completion_tokens=None)
        assert cost == 0.0


# ---------------- ConversationUsage.add_call ----------------

class TestConversationUsageAddCall:
    def test_single_call(self):
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("gpt-4o", prompt_tokens=100, completion_tokens=50)
        assert usage.total_prompt_tokens == 100
        assert usage.total_completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.total_llm_calls == 1
        assert usage.by_model == {"gpt-4o": 150}
        assert usage.by_role == {"main": 150}
        assert usage.total_cost_usd > 0

    def test_multiple_calls_accumulate(self):
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("gpt-4o", prompt_tokens=100, completion_tokens=50)
        usage.add_call("gpt-4o", prompt_tokens=200, completion_tokens=100)
        assert usage.total_prompt_tokens == 300
        assert usage.total_completion_tokens == 150
        assert usage.total_tokens == 450
        assert usage.total_llm_calls == 2

    def test_by_model_groups_correctly(self):
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("gpt-4o", prompt_tokens=100, completion_tokens=50)
        usage.add_call("claude-3-opus", prompt_tokens=200, completion_tokens=100)
        assert usage.by_model == {"gpt-4o": 150, "claude-3-opus": 300}

    def test_by_role_groups_correctly(self):
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("gpt-4o", prompt_tokens=100, completion_tokens=50, role="main")
        usage.add_call("gpt-4o", prompt_tokens=200, completion_tokens=100, role="subagent")
        assert usage.by_role == {"main": 150, "subagent": 300}

    def test_none_tokens_treated_as_zero(self):
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("gpt-4o", prompt_tokens=None, completion_tokens=None)
        assert usage.total_prompt_tokens == 0
        assert usage.total_completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.total_llm_calls == 1  # 调用次数仍 +1

    def test_empty_model_name_grouped_as_unknown(self):
        """空 model_name 走 'unknown' 分组（add_call 内部用 'unknown'）。"""
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("", prompt_tokens=100, completion_tokens=0)
        # by_model 不存空 key（add_call 里 if model_name）
        assert usage.by_model == {}
        # 但 token 数仍累加
        assert usage.total_tokens == 100
        # cost 视为 0
        assert usage.total_cost_usd == 0.0


# ---------------- aggregate_usage_from_messages ----------------

@dataclass
class FakeMessage:
    """duck-typed GptsMessage for testing."""
    model_name: Optional[str] = None
    metrics: Any = None  # dict / str / object


class TestAggregateUsageFromMessages:
    def test_empty_messages(self):
        usage = aggregate_usage_from_messages("c1", [])
        assert usage.conv_id == "c1"
        assert usage.total_tokens == 0
        assert usage.total_llm_calls == 0

    def test_metrics_dict(self):
        msgs = [
            FakeMessage(
                model_name="gpt-4o",
                metrics={"llm_metrics": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}},
            ),
            FakeMessage(
                model_name="gpt-4o",
                metrics={"llm_metrics": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}},
            ),
        ]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_prompt_tokens == 300
        assert usage.total_completion_tokens == 150
        assert usage.total_tokens == 450
        assert usage.total_llm_calls == 2
        assert usage.by_model == {"gpt-4o": 450}

    def test_metrics_json_string(self):
        """V1 DB 持久化格式是 JSON 字符串。"""
        metrics_str = json.dumps({
            "llm_metrics": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        })
        msgs = [FakeMessage(model_name="gpt-4o", metrics=metrics_str)]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_tokens == 150
        assert usage.total_llm_calls == 1

    def test_metrics_object_with_to_dict(self):
        """MessageMetrics 对象有 to_dict() 方法。"""
        class FakeMetrics:
            def to_dict(self):
                return {"llm_metrics": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}
        msgs = [FakeMessage(model_name="gpt-4o", metrics=FakeMetrics())]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_tokens == 150

    def test_metrics_none_skipped(self):
        msgs = [
            FakeMessage(model_name="gpt-4o", metrics=None),
            FakeMessage(model_name="gpt-4o", metrics={"llm_metrics": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}),
        ]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_llm_calls == 1  # 只计 1 次

    def test_invalid_json_string_skipped(self):
        msgs = [FakeMessage(model_name="gpt-4o", metrics="not valid json {")]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_llm_calls == 0

    def test_zero_token_metrics_skipped(self):
        """total_tokens=0 的消息跳过（避免空调用计入）。"""
        msgs = [
            FakeMessage(model_name="gpt-4o", metrics={"llm_metrics": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}),
        ]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_llm_calls == 0

    def test_missing_llm_metrics_skipped(self):
        msgs = [
            FakeMessage(model_name="gpt-4o", metrics={"action_metrics": []}),
        ]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_llm_calls == 0

    def test_missing_total_tokens_falls_back_to_sum(self):
        """total_tokens 缺失时用 prompt + completion 兜底。"""
        msgs = [
            FakeMessage(
                model_name="gpt-4o",
                metrics={"llm_metrics": {"prompt_tokens": 100, "completion_tokens": 50}},
            ),
        ]
        usage = aggregate_usage_from_messages("c1", msgs)
        assert usage.total_tokens == 150

    def test_role_resolver(self):
        """role_resolver 用于区分 main / subagent。"""
        msgs = [
            FakeMessage(model_name="gpt-4o", metrics={"llm_metrics": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}),
            FakeMessage(model_name="gpt-4o", metrics={"llm_metrics": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}}),
        ]

        def resolver(msg):
            # 简单逻辑：第二条消息算 subagent
            return "subagent" if msg is msgs[1] else "main"

        usage = aggregate_usage_from_messages("c1", msgs, role_resolver=resolver)
        assert usage.by_role == {"main": 150, "subagent": 300}

    def test_cost_aggregated(self):
        msgs = [
            FakeMessage(
                model_name="gpt-4o",
                metrics={"llm_metrics": {"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000}},
            ),
        ]
        usage = aggregate_usage_from_messages("c1", msgs)
        # gpt-4o prompt 5.0 USD / 1M
        assert usage.total_cost_usd == pytest.approx(5.0)


# ---------------- format_usage_log ----------------

class TestFormatUsageLog:
    def test_log_includes_key_fields(self):
        usage = ConversationUsage(conv_id="c1")
        usage.add_call("gpt-4o", prompt_tokens=100, completion_tokens=50)
        log = format_usage_log(usage)
        assert "conv=c1" in log
        assert "calls=1" in log
        assert "prompt=100" in log
        assert "completion=50" in log
        assert "total=150" in log
        assert "cost=$" in log
        assert "by_model=" in log
        assert "by_role=" in log

    def test_log_empty_usage(self):
        usage = ConversationUsage(conv_id="c1")
        log = format_usage_log(usage)
        assert "calls=0" in log
        assert "total=0" in log
