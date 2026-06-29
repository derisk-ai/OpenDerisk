"""Tests for build_workspace_context materialized field."""
from unittest.mock import MagicMock, patch
from derisk_serve.workspace.context_builder import build_workspace_context


def test_build_context_includes_materialized_key():
    """build_workspace_context 返回的 dict 含 materialized 键。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.context_builder.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.workspace.context_builder.materialize_resources"
    ) as mock_mat:
        MockWsService.return_value.get_by_id.return_value = MagicMock(
            id=1, workspace_code="ws1", name="SRE", scenario_type="sre",
            default_agent_app_code="chat_normal",
        )
        MockWsService.return_value.list_members.return_value = []
        MockWsService.return_value.list_resources.return_value = []
        mock_mat.return_value = MagicMock(
            dynamic_resources=[MagicMock(type="mcp(derisk)")],
            extra_agents=[],
        )
        system_app.get_component.return_value = MockWsService.return_value
        ctx = build_workspace_context(system_app, workspace_id=1)
    assert "materialized" in ctx
    assert "dynamic_resources" in ctx["materialized"]
    assert "extra_agents" in ctx["materialized"]
    assert len(ctx["materialized"]["dynamic_resources"]) == 1


def test_build_context_materialized_empty_on_failure():
    """物化失败时 materialized 字段为空列表，不抛异常。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.context_builder.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.workspace.context_builder.materialize_resources",
        side_effect=Exception("boom"),
    ):
        MockWsService.return_value.get_by_id.return_value = MagicMock(
            id=1, workspace_code="ws1", name="SRE", scenario_type="sre",
            default_agent_app_code="chat_normal",
        )
        MockWsService.return_value.list_members.return_value = []
        MockWsService.return_value.list_resources.return_value = []
        system_app.get_component.return_value = MockWsService.return_value
        ctx = build_workspace_context(system_app, workspace_id=1)
    assert ctx["materialized"]["dynamic_resources"] == []
    assert ctx["materialized"]["extra_agents"] == []
