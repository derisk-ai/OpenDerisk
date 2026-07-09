"""Unit tests for SceneAgentWorkspaceConverter."""
import json
import re
import pytest

from derisk_ext.vis.derisk.derisk_vis_scene_agent_workspace_converter import (
    SceneAgentWorkspaceConverter,
)


def _make_gpt_msg(action_report=None, ai_message=""):
    """构造一个最小 GptsMessage-like 对象供测试使用。"""
    class _Msg:
        def __init__(self):
            self.action_report = action_report
            self.ai_message = ai_message
            self.role_name = "LLM"
    return _Msg()


@pytest.mark.asyncio
async def test_render_name_is_scene_agent_workspace():
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    assert conv.render_name == "scene_agent_workspace"
    assert conv.web_use is True


@pytest.mark.asyncio
async def test_visualization_returns_structured_vis_with_execution_step():
    """给定带 action_report 的 message,visualization 产出含 execution 步骤的结构化 vis。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    action_report = {
        "view": "tool_view",
        "content": json.dumps({
            "name": "search_workspace",
            "args": {"query": "营收"},
            "status": "complete",
            "content": "找到 3 条记录",
        }),
    }
    msg = _make_gpt_msg(action_report=action_report, ai_message="正在搜索")

    out = await conv.visualization(messages=[msg], gpt_msg=msg, is_first_chunk=True)
    # 解析 vis tag 包裹的结构化 JSON,断言完整 payload 而非子串存在性
    match = re.search(r"```scene_agent_workspace\n(.*?)\n```", out, re.DOTALL)
    assert match is not None, f"未找到 scene_agent_workspace vis tag, got: {out!r}"
    payload = json.loads(match.group(1))

    assert payload["render_name"] == "scene_agent_workspace"
    assert payload["planning"] is None
    assert len(payload["execution"]) == 1

    step = payload["execution"][0]
    assert step["action"] == "search_workspace"
    # action_report status="complete" 经转换器映射为 "done"
    assert step["status"] == "done"
    assert step["action_input"] == {"query": "营收"}
    assert step["output"] == "找到 3 条记录"

    assert payload["summary"] == "正在搜索"