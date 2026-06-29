"""Tests for playbook runtime passing materialized resources."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from derisk_serve.playbook.runtime import run_task
from derisk_serve.playbook.service.service import PLAYBOOK_SERVICE_COMPONENT_NAME
from derisk_serve.task.service.service import TASK_SERVICE_COMPONENT_NAME
from derisk_serve.workspace.service.service import WORKSPACE_SERVICE_COMPONENT_NAME


@pytest.mark.asyncio
async def test_run_task_passes_materialized_resources_to_app_chat():
    """run_task 把物化的 dynamic_resources/extra_agents 透传给 app_chat_v3。"""
    fake_task = MagicMock(
        id=1,
        workspace_id=10,
        title="容量巡检",
        playbook_id=5,
        playbook_version_id=2,
        context_json="{}",
        status="running",
        conv_session_id="conv-1",
        created_by_user_id=1,
        description=None,
    )
    fake_playbook = MagicMock(
        id=5,
        name="容量巡检",
        scenario_type="sre",
        task_type="routine",
        declaration={"skills": [], "context": {}, "deliverables": [], "distill": {}},
        declaration_dsl_json='{"skills": [], "context": {}, "deliverables": [], "distill": {}}',
        current_version=1,
    )
    fake_workspace = MagicMock(
        default_agent_app_code="chat_normal", name="ws", scenario_type="sre"
    )
    fake_materialized = MagicMock(
        dynamic_resources=[MagicMock(type="mcp(derisk)")],
        extra_agents=[{"app_code": "analyzer"}],
    )

    system_app = MagicMock()

    with patch(
        "derisk_serve.playbook.runtime.PlaybookService"
    ) as MockPbService, patch(
        "derisk_serve.playbook.runtime.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.playbook.runtime.materialize_resources",
        return_value=fake_materialized,
    ) as mock_mat, patch(
        "derisk_serve.playbook.runtime.multi_agents"
    ) as mock_multi:
        MockPbService.return_value.get_by_id.return_value = fake_playbook
        MockWsService.return_value.get_by_id.return_value = fake_workspace

        task_service = MagicMock()
        task_service.get_by_id.return_value = fake_task

        def get_component(name, cls):
            if name == PLAYBOOK_SERVICE_COMPONENT_NAME:
                return MockPbService.return_value
            if name == WORKSPACE_SERVICE_COMPONENT_NAME:
                return MockWsService.return_value
            if name == TASK_SERVICE_COMPONENT_NAME:
                return task_service
            return MagicMock()

        system_app.get_component.side_effect = get_component

        mock_multi.app_chat_v3 = AsyncMock(return_value=(None, None))
        await run_task(system_app, 1)

        # 验证 app_chat_v3 被调用时 ext_info 含物化资源
        call_kwargs = mock_multi.app_chat_v3.call_args.kwargs
        assert "dynamic_resources" in call_kwargs
        assert len(call_kwargs["dynamic_resources"]) == 1
        assert "extra_agents" in call_kwargs
        assert call_kwargs["extra_agents"] == [{"app_code": "analyzer"}]

        mock_mat.assert_called_once_with(system_app, 10)


@pytest.mark.asyncio
async def test_run_task_materialize_failure_transitions_task_to_failed():
    """物化资源失败时，任务应被标记为 failed 且不应调用 app_chat_v3。"""
    fake_task = MagicMock(
        id=1,
        workspace_id=10,
        title="容量巡检",
        playbook_id=5,
        playbook_version_id=2,
        context_json="{}",
        status="running",
        conv_session_id="conv-1",
        created_by_user_id=1,
        description=None,
    )
    fake_playbook = MagicMock(
        id=5,
        name="容量巡检",
        scenario_type="sre",
        task_type="routine",
        declaration={"skills": [], "context": {}, "deliverables": [], "distill": {}},
        declaration_dsl_json='{"skills": [], "context": {}, "deliverables": [], "distill": {}}',
        current_version=1,
    )
    fake_workspace = MagicMock(
        default_agent_app_code="chat_normal", name="ws", scenario_type="sre"
    )

    system_app = MagicMock()

    with patch(
        "derisk_serve.playbook.runtime.PlaybookService"
    ) as MockPbService, patch(
        "derisk_serve.playbook.runtime.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.playbook.runtime.materialize_resources",
        side_effect=RuntimeError("workspace not found"),
    ) as mock_mat, patch(
        "derisk_serve.playbook.runtime.multi_agents"
    ) as mock_multi:
        MockPbService.return_value.get_by_id.return_value = fake_playbook
        MockWsService.return_value.get_by_id.return_value = fake_workspace

        task_service = MagicMock()
        task_service.get_by_id.return_value = fake_task

        def get_component(name, cls):
            if name == PLAYBOOK_SERVICE_COMPONENT_NAME:
                return MockPbService.return_value
            if name == WORKSPACE_SERVICE_COMPONENT_NAME:
                return MockWsService.return_value
            if name == TASK_SERVICE_COMPONENT_NAME:
                return task_service
            return MagicMock()

        system_app.get_component.side_effect = get_component

        mock_multi.app_chat_v3 = AsyncMock(return_value=(None, None))
        result = await run_task(system_app, 1)

        mock_mat.assert_called_once_with(system_app, 10)
        task_service.transition.assert_called_once_with(1, "failed")
        mock_multi.app_chat_v3.assert_not_called()
        assert result["status"] == "failed"
        assert "materialize failed" in result["error"]
