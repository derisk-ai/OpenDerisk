"""ToolContext v2 新增字段测试。"""
from derisk.agent.tools.context import ToolContext


def test_default_language_zh():
    ctx = ToolContext()
    assert ctx.language == "zh"


def test_scene_fields():
    ctx = ToolContext(scene="data_analyst", scenario_id="wm-sales-2025", language="en")
    assert ctx.scene == "data_analyst"
    assert ctx.scenario_id == "wm-sales-2025"
    assert ctx.language == "en"


def test_step_fields():
    ctx = ToolContext(step_id="step-abc123", round_index=3)
    assert ctx.step_id == "step-abc123"
    assert ctx.round_index == 3


def test_set_get_resource_still_works():
    ctx = ToolContext()
    ctx.set_resource("sandbox_client", "fake_client")
    assert ctx.get_resource("sandbox_client") == "fake_client"
    assert ctx.get_resource("nonexistent") is None
