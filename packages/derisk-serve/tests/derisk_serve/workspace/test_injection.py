import pytest
from unittest.mock import MagicMock, patch


def _named_tool(name: str):
    m = MagicMock()
    m.name = name
    return m


def test_build_workspace_toolkit_lobby_has_12_tools():
    from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
    fake_system_app = MagicMock()
    layer1 = [_named_tool(n) for n in ["list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets"]]
    layer2_read = [_named_tool(n) for n in ["get_workspace_memory", "list_workspace_members"]]
    # Include Layer-3 reads in the all_read list to prove Lobby filters them out
    layer3_read = [_named_tool(n) for n in ["list_playbooks", "get_playbook_detail", "list_interventions"]]
    all_read = layer1 + layer2_read + layer3_read

    with patch("derisk_serve.workspace.agent_tools.toolkit.build_read_tools", return_value=all_read) as gr, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_write_tools", return_value=[_named_tool(f"w{i}") for i in range(5)]) as gw, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_playbook_tools") as gp:
        agent = build_workspace_toolkit(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=None,
            mode="lobby",
        )
        assert agent is not None
        assert len(agent._tools) == 12, f"Lobby must have 12 tools, got {len(agent._tools)}"
        gr.assert_called_once()
        gw.assert_called_once()
        gp.assert_not_called()


def test_build_workspace_toolkit_workbench_has_11_tools():
    from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
    fake_system_app = MagicMock()
    layer1 = [_named_tool(n) for n in ["list_tasks", "get_task_info", "list_artifacts", "list_deliveries", "list_assets"]]
    layer2_read = [_named_tool(n) for n in ["get_workspace_memory", "list_workspace_members"]]
    layer3_read = [_named_tool(n) for n in ["list_playbooks", "get_playbook_detail", "list_interventions"]]
    all_read = layer1 + layer2_read + layer3_read

    with patch("derisk_serve.workspace.agent_tools.toolkit.build_read_tools", return_value=all_read) as gr, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_write_tools") as gw, \
         patch("derisk_serve.workspace.agent_tools.toolkit.build_playbook_tools", return_value=[_named_tool(f"p{i}") for i in range(3)]) as gp:
        agent = build_workspace_toolkit(
            system_app=fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=10,
            mode="workbench",
        )
        assert agent is not None
        assert len(agent._tools) == 11, f"Workbench must have 11 tools, got {len(agent._tools)}"
        gr.assert_called_once()
        gw.assert_not_called()
        gp.assert_called_once()


def test_build_workspace_toolkit_returns_none_without_conv_uid():
    from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit
    fake_system_app = MagicMock()
    agent = build_workspace_toolkit(
        system_app=fake_system_app,
        workspace_id=1,
        user_id="u1",
        conv_uid=None,
        task_id=None,
        mode="lobby",
    )
    assert agent is None
