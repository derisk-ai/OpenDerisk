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


def test_write_tools_count(fake_system_app):
    """build_write_tools returns exactly the 5 expected Layer-2 write tools."""
    from derisk_serve.workspace.agent_tools.write_tools import build_write_tools

    with patch(
        "derisk_serve.workspace.agent_tools.write_tools.get_intervention_service"
    ):
        tools = build_write_tools(
            fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=None,
        )

    names = {t.name for t in tools}
    assert names == {
        "start_task",
        "close_task",
        "publish_asset",
        "create_delivery",
        "update_workspace",
    }


def test_write_tool_creates_intervention_with_null_task(fake_system_app):
    """start_task now creates a real Task; close_task still creates an intervention."""
    from derisk_serve.intervention.api.schemas import InterventionRequest
    from derisk_serve.workspace.agent_tools.write_tools import build_write_tools

    with patch(
        "derisk_serve.workspace.agent_tools.write_tools.get_intervention_service"
    ) as gis:
        gis.return_value.create.return_value = MagicMock(id=42)
        tools = build_write_tools(
            fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=None,
        )
        close_task = _find_tool(tools, "close_task")
        result = close_task._func(workspace_id=1, task_id=5)

    assert result == {"intervention_id": 42, "status": "awaiting_human"}
    request = gis.return_value.create.call_args.kwargs["request"]
    assert isinstance(request, InterventionRequest)
    assert request.task_id is None
    assert request.conv_uid == "conv-1"
    assert request.workspace_id == 1
    assert request.requested_by == "u1"
    assert request.question == {
        "tool": "close_task",
        "args": {"workspace_id": 1, "task_id": 5},
    }


def test_each_write_tool_uses_its_own_name_in_question(fake_system_app):
    """Each intervention-based write tool uses its own name. start_task is excluded."""
    from derisk_serve.workspace.agent_tools.write_tools import build_write_tools

    with patch(
        "derisk_serve.workspace.agent_tools.write_tools.get_intervention_service"
    ) as gis:
        gis.return_value.create.return_value = MagicMock(id=1)
        tools = build_write_tools(
            fake_system_app,
            workspace_id=2,
            user_id="u2",
            conv_uid="conv-2",
            task_id=None,
        )
        for tool in tools:
            if tool.name == "start_task":
                continue  # start_task now creates a real Task, not an intervention
            gis.return_value.create.reset_mock()
            tool._func(workspace_id=2)
            request = gis.return_value.create.call_args.kwargs["request"]
            assert request.question["tool"] == tool.name


def test_playbook_tools_count(fake_system_app):
    """build_playbook_tools returns exactly the 3 expected Layer-3 write tools."""
    from derisk_serve.workspace.agent_tools.playbook_tools import build_playbook_tools

    with patch(
        "derisk_serve.workspace.agent_tools.playbook_tools.get_intervention_service"
    ):
        tools = build_playbook_tools(
            fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=5,
        )

    names = {t.name for t in tools}
    assert names == {
        "launch_playbook",
        "update_playbook",
        "archive_playbook",
    }


def test_playbook_write_tool_creates_intervention(fake_system_app):
    from derisk_serve.intervention.api.schemas import InterventionRequest
    from derisk_serve.workspace.agent_tools.playbook_tools import build_playbook_tools

    with patch(
        "derisk_serve.workspace.agent_tools.playbook_tools.get_intervention_service"
    ) as gis:
        gis.return_value.create.return_value = MagicMock(id=7)
        tools = build_playbook_tools(
            fake_system_app,
            workspace_id=1,
            user_id="u1",
            conv_uid="conv-1",
            task_id=5,
        )
        launch = _find_tool(tools, "launch_playbook")
        result = launch._func(workspace_id=1, playbook_id=10)

    assert result == {"intervention_id": 7, "status": "awaiting_human"}
    request = gis.return_value.create.call_args.kwargs["request"]
    assert isinstance(request, InterventionRequest)
    assert request.task_id == 5
    assert request.conv_uid == "conv-1"
    assert request.workspace_id == 1
    assert request.requested_by == "u1"
    assert request.question == {
        "tool": "launch_playbook",
        "args": {"workspace_id": 1, "playbook_id": 10},
    }


def test_each_playbook_tool_uses_its_own_name_in_question(fake_system_app):
    from derisk_serve.workspace.agent_tools.playbook_tools import build_playbook_tools

    with patch(
        "derisk_serve.workspace.agent_tools.playbook_tools.get_intervention_service"
    ) as gis:
        gis.return_value.create.return_value = MagicMock(id=2)
        tools = build_playbook_tools(
            fake_system_app,
            workspace_id=3,
            user_id="u3",
            conv_uid="conv-3",
            task_id=9,
        )
        for tool in tools:
            gis.return_value.create.reset_mock()
            tool._func(workspace_id=3)
            request = gis.return_value.create.call_args.kwargs["request"]
            assert request.question["tool"] == tool.name
            assert request.task_id == 9
