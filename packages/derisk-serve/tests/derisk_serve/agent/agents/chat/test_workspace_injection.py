"""Tests for workspace materialized resource injection in aggregation_chat."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from derisk_serve.agent.agents.chat.agent_chat import AgentChat


class _ConcreteAgentChat(AgentChat):
    async def chat(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_workspace_materialized_resources_injected_to_ext_info():
    """workspace_id 存在时，物化的 dynamic_resources 合并到 ext_info。"""
    agent_chat = object.__new__(_ConcreteAgentChat)
    agent_chat.system_app = MagicMock()
    ext_info = {"workspace_id": 1, "task_id": None}

    fake_resource = MagicMock()
    fake_resource.type = "mcp(derisk)"
    fake_ctx = {
        "workspace_id": 1,
        "workspace": MagicMock(),
        "members": [],
        "resources": [],
        "materialized": {
            "dynamic_resources": [fake_resource],
            "extra_agents": [{"app_code": "analyzer"}],
        },
        "current_task": None,
        "recent_tasks": [],
        "recent_assets": [],
        "task_artifacts": [],
        "task_interventions": [],
    }

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="summary",
    ):
        # 直接调注入逻辑（aggregation_chat 太重，测注入分支）
        # 这里用反射或抽出 helper 测
        from derisk_serve.agent.agents.chat.agent_chat import (
            _inject_workspace_context,
        )
        _inject_workspace_context(agent_chat, ext_info)

    assert "dynamic_resources" in ext_info
    assert len(ext_info["dynamic_resources"]) == 1
    assert ext_info["dynamic_resources"][0] == fake_resource
    assert "extra_agents" in ext_info
    assert ext_info["extra_agents"] == [{"app_code": "analyzer"}]
    assert "workspace_context" in ext_info


@pytest.mark.asyncio
async def test_workspace_injection_no_workspace_id_noop():
    """无 workspace_id 时 ext_info 不被改动。"""
    ext_info = {}
    from derisk_serve.agent.agents.chat.agent_chat import (
        _inject_workspace_context,
    )
    agent_chat = object.__new__(_ConcreteAgentChat)
    agent_chat.system_app = MagicMock()
    _inject_workspace_context(agent_chat, ext_info)
    assert "dynamic_resources" not in ext_info
    assert "extra_agents" not in ext_info
    assert "workspace_context" not in ext_info
