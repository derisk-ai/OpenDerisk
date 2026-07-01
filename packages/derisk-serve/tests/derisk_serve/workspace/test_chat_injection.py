import pytest
from unittest.mock import MagicMock, patch


def test_inject_workspace_context_appends_agent_and_prompt():
    from derisk_serve.agent.agents.chat import agent_chat

    fake_system_app = MagicMock()
    extra_agents = []
    system_prompt = ["base"]
    with patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_context"
    ) as bc, patch(
        "derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary"
    ) as rs, patch(
        "derisk_serve.agent.agents.chat.agent_chat.build_workspace_toolkit"
    ) as bt:
        bc.return_value = MagicMock(
            workspace_id=1, task=None, playbook_declaration=None
        )
        rs.return_value = "WORKSPACE SUMMARY"
        bt.return_value = MagicMock(name="workspace_agent")
        agent_chat._inject_workspace_context(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=None,
            system_prompt=system_prompt,
            extra_agents=extra_agents,
        )
        assert "WORKSPACE SUMMARY" in system_prompt
        assert len(extra_agents) == 1
