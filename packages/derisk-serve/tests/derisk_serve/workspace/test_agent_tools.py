"""Tests for workspace agent read tools."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_system_app():
    return MagicMock()


def _find_tool(tools, name):
    return next(t for t in tools if t.name == name)


def test_read_tools_count(fake_system_app):
    """build_read_tools returns exactly the 10 expected read tools."""
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_task_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_artifact_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_delivery_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_asset_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_playbook_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_intervention_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_workspace_memory_service"
    ), patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_workspace_member_service"
    ):
        tools = build_read_tools(fake_system_app, workspace_id=1)

    names = {t.name for t in tools}
    assert names == {
        "list_tasks",
        "get_task_info",
        "list_artifacts",
        "list_deliveries",
        "list_assets",
        "get_workspace_memory",
        "list_workspace_members",
        "list_playbooks",
        "get_playbook_detail",
        "list_interventions",
    }


def test_list_tasks_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_task_service"
    ) as gts:
        gts.return_value.list_tasks.return_value = [
            MagicMock(to_response=lambda: {"id": 1, "title": "t"})
        ]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        list_tasks = _find_tool(tools, "list_tasks")
        result = list_tasks._func(workspace_id=1)

    assert isinstance(result, list)
    assert result == [{"id": 1, "title": "t"}]
    gts.return_value.list_tasks.assert_called_once()


def test_get_task_info_tool_returns_dict(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_task_service"
    ) as gts:
        gts.return_value.get_by_id.return_value = MagicMock(
            to_response=lambda: {"id": 1, "title": "t"}
        )
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "get_task_info")
        result = tool._func(workspace_id=1, task_id=1)

    assert isinstance(result, dict)
    assert result == {"id": 1, "title": "t"}
    gts.return_value.get_by_id.assert_called_once_with(1)


def test_list_artifacts_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_artifact_service"
    ) as gas:
        gas.return_value.list_artifacts.return_value = [
            MagicMock(to_response=lambda: {"id": 2, "title": "a"})
        ]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "list_artifacts")
        result = tool._func(workspace_id=1, task_id=10)

    assert isinstance(result, list)
    gas.return_value.list_artifacts.assert_called_once()


def test_list_deliveries_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_delivery_service"
    ) as gds:
        gds.return_value.list_deliveries.return_value = [
            MagicMock(to_response=lambda: {"id": 3})
        ]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "list_deliveries")
        result = tool._func(workspace_id=1)

    assert isinstance(result, list)
    gds.return_value.list_deliveries.assert_called_once()


def test_list_assets_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_asset_service"
    ) as gas:
        gas.return_value.list_assets.return_value = [
            MagicMock(to_response=lambda: {"id": 4, "name": "asset"})
        ]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "list_assets")
        result = tool._func(workspace_id=1)

    assert isinstance(result, list)
    gas.return_value.list_assets.assert_called_once()


def test_list_playbooks_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_playbook_service"
    ) as gps:
        gps.return_value.list_playbooks.return_value = [
            MagicMock(to_response=lambda: {"id": 5, "name": "pb"})
        ]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "list_playbooks")
        result = tool._func(workspace_id=1)

    assert isinstance(result, list)
    gps.return_value.list_playbooks.assert_called_once()


def test_get_playbook_detail_tool_returns_dict(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_playbook_service"
    ) as gps:
        gps.return_value.get_by_id.return_value = MagicMock(
            to_response=lambda: {"id": 5, "name": "pb"}
        )
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "get_playbook_detail")
        result = tool._func(workspace_id=1, playbook_id=5)

    assert isinstance(result, dict)
    gps.return_value.get_by_id.assert_called_once_with(5)


def test_list_interventions_tool_returns_list(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_intervention_service"
    ) as gis:
        gis.return_value.list_interventions.return_value = [
            MagicMock(to_response=lambda: {"id": 6})
        ]
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "list_interventions")
        result = tool._func(workspace_id=1, task_id=10)

    assert isinstance(result, list)
    gis.return_value.list_interventions.assert_called_once()


def test_get_workspace_memory_graceful_when_no_service(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_workspace_memory_service",
        return_value=None,
    ):
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "get_workspace_memory")
        result = tool._func(workspace_id=1)

    assert result == {
        "memory": None,
        "note": "no workspace memory configured",
    }


def test_list_workspace_members_graceful_when_no_service(fake_system_app):
    from derisk_serve.workspace.agent_tools.read_tools import build_read_tools

    with patch(
        "derisk_serve.workspace.agent_tools.read_tools.get_workspace_member_service",
        return_value=None,
    ):
        tools = build_read_tools(fake_system_app, workspace_id=1)
        tool = _find_tool(tools, "list_workspace_members")
        result = tool._func(workspace_id=1)

    assert result == {
        "members": [],
        "note": "no member service configured",
    }
