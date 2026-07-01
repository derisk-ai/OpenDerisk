"""Tests for workspace materialized resource injection in aggregation_chat."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The task package __init__ eagerly imports endpoints -> runtime -> agent
# controller, which requires derisk_app.config. Provide a lightweight stub so
# unit tests can import chat modules without the full derisk_app package
# installed.
if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk.agent import ConversableAgent, LLMConfig
from derisk_serve.agent.agents.chat.agent_chat import (
    AgentChat,
    _inject_workspace_context,
)
from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit


class _ConcreteAgentChat(AgentChat):
    async def chat(self, *args, **kwargs):
        pass


def _make_fake_ctx(materialized=None):
    return {
        "workspace_id": 1,
        "workspace": MagicMock(),
        "members": [],
        "resources": [],
        "materialized": materialized or {},
        "current_task": None,
        "recent_tasks": [],
        "recent_assets": [],
        "task_artifacts": [],
        "task_interventions": [],
    }


@pytest.mark.asyncio
async def test_workspace_materialized_resources_injected_to_ext_info():
    """workspace_id 存在时，物化的 dynamic_resources 合并到 ext_info。"""
    agent_chat = object.__new__(_ConcreteAgentChat)
    agent_chat.system_app = MagicMock()
    ext_info = {"workspace_id": 1, "task_id": None}

    fake_resource = MagicMock()
    fake_resource.type = "mcp(derisk)"
    fake_ctx = _make_fake_ctx(
        materialized={
            "dynamic_resources": [fake_resource],
            "extra_agents": [{"app_code": "analyzer"}],
        }
    )

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat._legacy_build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="summary",
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
            system_prompt=[],
            extra_agents=ext_info.setdefault("extra_agents", []),
            ext_info=ext_info,
        )

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
    _inject_workspace_context(
        system_app=MagicMock(),
        workspace_id=None,
        user_id=None,
        conv_uid="conv-1",
        task_id=None,
        system_prompt=[],
        extra_agents=[],
        ext_info=ext_info,
    )
    assert "dynamic_resources" not in ext_info
    assert "extra_agents" not in ext_info
    assert "workspace_context" not in ext_info


@pytest.mark.asyncio
async def test_workspace_materialized_resources_merged_with_existing():
    """已有 dynamic_resources / extra_agents 时，物化资源追加而非覆盖。"""
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

    fake_ctx = _make_fake_ctx(
        materialized={
            "dynamic_resources": [materialized_resource],
            "extra_agents": [{"app_code": "materialized"}],
        }
    )

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat._legacy_build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="summary",
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_toolkit",
        return_value=None,
    ):
        _inject_workspace_context(
            system_app=MagicMock(),
            workspace_id=ext_info.get("workspace_id"),
            user_id=None,
            conv_uid="conv-1",
            task_id=ext_info.get("task_id"),
            system_prompt=[],
            extra_agents=ext_info["extra_agents"],
            ext_info=ext_info,
        )

    assert len(ext_info["dynamic_resources"]) == 2
    assert ext_info["dynamic_resources"][0] == existing_resource
    assert ext_info["dynamic_resources"][1] == materialized_resource

    assert len(ext_info["extra_agents"]) == 2
    assert ext_info["extra_agents"][0] == {"app_code": "existing"}
    assert ext_info["extra_agents"][1] == {"app_code": "materialized"}


@pytest.mark.asyncio
async def test_workspace_control_agent_appended_to_existing_empty_extra_agents():
    """生产路径：ext_info 已有空 extra_agents 列表时，WorkspaceControlAgent 仍被注入。

    调用方通过 `extra_agents=ext_info.setdefault("extra_agents", [])` 把同一个列
    表对象传进来；_inject_workspace_context 必须保留该对象身份，否则追加的
    WorkspaceControlAgent 会落到被丢弃的旧列表上，导致 ext_info 里看不到。
    """
    ext_info = {"workspace_id": 1, "task_id": None, "extra_agents": []}
    extra_agents = ext_info["extra_agents"]

    fake_agent = MagicMock(name="WorkspaceControlAgent")
    fake_ctx = _make_fake_ctx()

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat._legacy_build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context",
        return_value=fake_ctx,
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary",
        return_value="summary",
    ), patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_toolkit",
        return_value=fake_agent,
    ):
        _inject_workspace_context(
            system_app=MagicMock(),
            workspace_id=ext_info.get("workspace_id"),
            user_id=None,
            conv_uid="conv-1",
            task_id=ext_info.get("task_id"),
            system_prompt=[],
            extra_agents=extra_agents,
            ext_info=ext_info,
        )

    assert ext_info["extra_agents"] is extra_agents
    assert fake_agent in ext_info["extra_agents"]
    assert ext_info["extra_agents"].count(fake_agent) == 1


@pytest.mark.asyncio
async def test_build_extra_employees_passes_through_prebuilt_agent():
    """_build_extra_employees 对 prebuilt agent 不调用 app_service.app_detail。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.agent_tools.toolkit.build_read_tools",
        return_value=[],
    ), patch(
        "derisk_serve.workspace.agent_tools.toolkit.build_write_tools",
        return_value=[],
    ):
        agent = build_workspace_toolkit(
            system_app=system_app,
            workspace_id=1,
            user_id=None,
            conv_uid="conv-1",
            mode="lobby",
            llm_config=LLMConfig(),
        )

    agent_chat = object.__new__(_ConcreteAgentChat)

    fake_app_service = MagicMock()
    fake_app_service.app_detail = AsyncMock(
        side_effect=AssertionError("app_detail should not be called for prebuilt agent")
    )

    with patch(
        "derisk_serve.agent.agents.chat.agent_chat.get_app_service",
        return_value=fake_app_service,
    ):
        employees = await agent_chat._build_extra_employees(
            extra_agents=[agent],
            context=MagicMock(),
            agent_memory=MagicMock(),
            rm=MagicMock(),
            scheduler=None,
        )

    assert len(employees) == 1
    assert employees[0] is agent
    fake_app_service.app_detail.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_control_agent_has_llm_config():
    """WorkspaceControlAgent 通过 build_workspace_toolkit 构建后 llm_config 非空。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.agent_tools.toolkit.build_read_tools",
        return_value=[],
    ), patch(
        "derisk_serve.workspace.agent_tools.toolkit.build_write_tools",
        return_value=[],
    ):
        agent = build_workspace_toolkit(
            system_app=system_app,
            workspace_id=1,
            user_id=None,
            conv_uid="conv-1",
            mode="lobby",
        )

    assert isinstance(agent, ConversableAgent)
    assert agent.llm_config is not None


@pytest.mark.asyncio
async def test_workspace_control_agent_forwarded_llm_config():
    """显式传入的 llm_config 被透传到 WorkspaceControlAgent。"""
    system_app = MagicMock()
    cfg = LLMConfig(llm_param={"temperature": 0.42})
    with patch(
        "derisk_serve.workspace.agent_tools.toolkit.build_read_tools",
        return_value=[],
    ), patch(
        "derisk_serve.workspace.agent_tools.toolkit.build_write_tools",
        return_value=[],
    ):
        agent = build_workspace_toolkit(
            system_app=system_app,
            workspace_id=1,
            user_id=None,
            conv_uid="conv-1",
            mode="lobby",
            llm_config=cfg,
        )

    assert agent.llm_config is cfg
