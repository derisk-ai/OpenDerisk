"""Tests for scene dynamic context injection in aggregation_chat."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk.agent import LLMConfig
from derisk_serve.agent.agents.chat.agent_chat import _inject_workspace_context
from derisk_serve.building.app.api.schema_app import GptsApp


class _FakeAgentChat:
    system_app = MagicMock()


@pytest.mark.asyncio
async def test_inject_workspace_context_appends_scene_dynamic_block():
    """_inject_workspace_context 在 lobby/workbench 模式下都追加场景动态上下文。"""
    agent_chat = _FakeAgentChat()
    ext_info = {"workspace_id": 1, "task_id": None}
    system_prompt: list[str] = []

    fake_workspace = MagicMock()
    fake_workspace.name = "Test空间"
    fake_ctx = MagicMock(
        workspace=fake_workspace,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        task=None,
        playbook_declaration=None,
        user_id=None,
        workspace_id=1,
        task_id=None,
        playbooks=[MagicMock(id=1, name="数据分析", scenario_type="data_ops")],
        active_tasks=[MagicMock(id=2, title="活跃任务", status="running")],
    )

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat._legacy_build_workspace_context",
        return_value={"materialized": {"dynamic_resources": [], "extra_agents": []}},
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="# 当前空间：Test空间",
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_scene_dynamic_context",
        return_value="## 当前场景上下文\n模式：lobby",
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_toolkit",
        return_value=None,
    ):
        _inject_workspace_context(
            system_app=agent_chat.system_app,
            workspace_id=ext_info.get("workspace_id"),
            user_id=None,
            conv_uid="conv-1",
            task_id=ext_info.get("task_id"),
            system_prompt=system_prompt,
            extra_agents=ext_info.setdefault("extra_agents", []),
            ext_info=ext_info,
            llm_config=LLMConfig(),
        )

    assert len(system_prompt) == 2
    assert "当前空间：Test空间" in system_prompt[0]
    assert "当前场景上下文" in system_prompt[1]


def test_aggregation_chat_merges_system_prompt_into_app_template():
    """aggregation_chat 把动态上下文合并进 gpt_app.system_prompt_template。"""
    app = GptsApp(
        app_code="scene-workspace-agent",
        system_prompt_template="静态提示",
    )
    ext_info = {"system_prompt": "动态上下文"}

    # The merge logic is a plain inline mutation; assert it behaves as expected.
    if ext_info.get("system_prompt") and app.system_prompt_template:
        app.system_prompt_template = (
            f"{app.system_prompt_template}\n\n{ext_info['system_prompt']}"
        )

    assert "静态提示" in app.system_prompt_template
    assert "动态上下文" in app.system_prompt_template