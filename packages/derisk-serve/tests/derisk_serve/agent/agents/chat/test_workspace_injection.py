"""Tests for workspace materialized resource injection in aggregation_chat."""
import pytest
from unittest.mock import MagicMock, patch
from derisk_serve.agent.agents.chat.agent_chat import (
    AgentChat,
    _inject_workspace_context,
)


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
    agent_chat = object.__new__(_ConcreteAgentChat)
    agent_chat.system_app = MagicMock()
    _inject_workspace_context(agent_chat, ext_info)
    assert "dynamic_resources" not in ext_info
    assert "extra_agents" not in ext_info
    assert "workspace_context" not in ext_info


@pytest.mark.asyncio
async def test_workspace_materialized_resources_merged_with_existing():
    """已有 dynamic_resources / extra_agents 时，物化资源追加而非覆盖。"""
    agent_chat = object.__new__(_ConcreteAgentChat)
    agent_chat.system_app = MagicMock()

    existing_resource = MagicMock()
    existing_resource.type = "existing"
    materialized_resource = MagicMock()
    materialized_resource.type = "materialized"

    ext_info = {
        "workspace_id": 1,
        "task_id": None,
        "dynamic_resources": [existing_resource],
        "extra_agents": [{"app_code": "existing"}],
    }

    fake_ctx = {
        "workspace_id": 1,
        "workspace": MagicMock(),
        "members": [],
        "resources": [],
        "materialized": {
            "dynamic_resources": [materialized_resource],
            "extra_agents": [{"app_code": "materialized"}],
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
        _inject_workspace_context(agent_chat, ext_info)

    assert len(ext_info["dynamic_resources"]) == 2
    assert ext_info["dynamic_resources"][0] == existing_resource
    assert ext_info["dynamic_resources"][1] == materialized_resource

    assert len(ext_info["extra_agents"]) == 2
    assert ext_info["extra_agents"][0] == {"app_code": "existing"}
    assert ext_info["extra_agents"][1] == {"app_code": "materialized"}
