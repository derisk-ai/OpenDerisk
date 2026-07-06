import pytest
from unittest.mock import MagicMock

from derisk_serve.workspace.agent_tools._task_creator import create_task_from_tool


class TestCreateTaskFromTool:
    """Tests for _task_creator.create_task_from_tool."""

    def _build_system_app(self, mock_task, mock_playbook=None):
        """Build a mock system_app with task and playbook services."""
        mock_task_service = MagicMock()
        mock_task_service.create.return_value = mock_task

        mock_playbook_service = MagicMock()
        if mock_playbook is not None:
            mock_playbook_service.get_by_id.return_value = mock_playbook

        system_app = MagicMock()

        def get_component(name, cls):
            if name == "serve_task_service":
                return mock_task_service
            if name == "serve_playbook_service":
                return mock_playbook_service
            return None

        system_app.get_component = get_component
        return system_app

    def test_creates_task_with_playbook(self):
        """When playbook_id is given, task title defaults to playbook name."""
        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.title = "容量巡检"
        mock_task.status = "draft"
        mock_task.playbook_id = 7
        mock_task.triggered_by = "manual"

        mock_playbook = MagicMock()
        mock_playbook.name = "容量巡检"

        system_app = self._build_system_app(mock_task, mock_playbook)

        result = create_task_from_tool(
            system_app, workspace_id=1, user_id="100", playbook_id=7
        )
        assert result["task_id"] == 42
        assert result["title"] == "容量巡检"
        assert result["status"] == "draft"
        assert result["playbook_id"] == 7
        assert result["playbook_name"] == "容量巡检"
        assert result["triggered_by"] == "manual"

    def test_creates_task_with_custom_title(self):
        """When title is given, it overrides the playbook name."""
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "自定义标题"
        mock_task.status = "draft"
        mock_task.playbook_id = None
        mock_task.triggered_by = "manual"

        system_app = self._build_system_app(mock_task)

        result = create_task_from_tool(
            system_app,
            workspace_id=1,
            user_id="100",
            title="自定义标题",
            description="测试描述",
        )
        assert result["task_id"] == 1
        assert result["title"] == "自定义标题"

    def test_creates_task_without_playbook(self):
        """When no playbook_id, title defaults to '手动创建任务'."""
        mock_task = MagicMock()
        mock_task.id = 99
        mock_task.title = "手动创建任务"
        mock_task.status = "draft"
        mock_task.playbook_id = None
        mock_task.triggered_by = "manual"

        system_app = self._build_system_app(mock_task)

        result = create_task_from_tool(
            system_app, workspace_id=1, user_id="100"
        )
        assert result["task_id"] == 99
        assert result["title"] == "手动创建任务"
        assert result["playbook_id"] is None
        assert result["playbook_name"] is None

    def test_user_id_non_digit(self):
        """When user_id is not a digit, created_by_user_id is None."""
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "手动创建任务"
        mock_task.status = "draft"
        mock_task.playbook_id = None
        mock_task.triggered_by = "manual"

        system_app = self._build_system_app(mock_task)

        result = create_task_from_tool(
            system_app, workspace_id=1, user_id="system"
        )
        assert result["task_id"] == 1


class TestWriteToolsStartTask:
    """Tests for write_tools.build_write_tools start_task behavior."""

    def test_start_task_emits_event(self):
        """start_task should call on_event with task_created."""
        from derisk_serve.workspace.agent_tools.write_tools import build_write_tools

        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.title = "测试任务"
        mock_task.status = "draft"
        mock_task.playbook_id = None
        mock_task.triggered_by = "manual"

        mock_task_service = MagicMock()
        mock_task_service.create.return_value = mock_task

        mock_playbook_service = MagicMock()

        system_app = MagicMock()

        def get_component(name, cls):
            if name == "serve_task_service":
                return mock_task_service
            if name == "serve_playbook_service":
                return mock_playbook_service
            return None

        system_app.get_component = get_component

        events = []

        def on_event(event_type, payload):
            events.append((event_type, payload))

        tools = build_write_tools(
            system_app,
            workspace_id=1,
            user_id="100",
            conv_uid="conv-1",
            on_event=on_event,
        )

        start_task_tool = next(t for t in tools if t.name == "start_task")
        result = start_task_tool.execute()

        assert result["task_id"] == 42
        assert len(events) == 1
        assert events[0][0] == "task_created"
        assert events[0][1]["task_id"] == 42
        assert events[0][1]["workspace_id"] == 1

    def test_start_task_without_event_callback(self):
        """start_task should work without on_event (no error)."""
        from derisk_serve.workspace.agent_tools.write_tools import build_write_tools

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "任务"
        mock_task.status = "draft"
        mock_task.playbook_id = None
        mock_task.triggered_by = "manual"

        mock_task_service = MagicMock()
        mock_task_service.create.return_value = mock_task

        mock_playbook_service = MagicMock()

        system_app = MagicMock()

        def get_component(name, cls):
            if name == "serve_task_service":
                return mock_task_service
            if name == "serve_playbook_service":
                return mock_playbook_service
            return None

        system_app.get_component = get_component

        tools = build_write_tools(
            system_app,
            workspace_id=1,
            user_id="100",
            conv_uid="conv-1",
            on_event=None,
        )

        start_task_tool = next(t for t in tools if t.name == "start_task")
        result = start_task_tool.execute()

        assert result["task_id"] == 1

    def test_non_start_task_tools_still_create_interventions(self):
        """close_task, publish_asset, etc. should still create interventions."""
        from derisk_serve.workspace.agent_tools.write_tools import build_write_tools

        mock_intervention = MagicMock()
        mock_intervention.id = 99

        mock_intervention_service = MagicMock()
        mock_intervention_service.create.return_value = mock_intervention

        mock_task_service = MagicMock()
        mock_playbook_service = MagicMock()

        system_app = MagicMock()

        def get_component(name, cls):
            if name == "serve_intervention_service":
                return mock_intervention_service
            if name == "serve_task_service":
                return mock_task_service
            if name == "serve_playbook_service":
                return mock_playbook_service
            return None

        system_app.get_component = get_component

        tools = build_write_tools(
            system_app,
            workspace_id=1,
            user_id="100",
            conv_uid="conv-1",
        )

        close_task_tool = next(t for t in tools if t.name == "close_task")
        result = close_task_tool.execute(task_id=5)
        assert result["intervention_id"] == 99
        assert result["status"] == "awaiting_human"