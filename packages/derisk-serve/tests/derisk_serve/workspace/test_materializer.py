"""Tests for workspace_resource materializer."""
import pytest
from unittest.mock import MagicMock, patch
from derisk_serve.workspace.materializer import (
    materialize_resources,
    MaterializedResources,
)


def test_materialize_empty_resources_returns_empty():
    """空资源列表返回空物化结果，不抛异常。"""
    system_app = MagicMock()
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService:
        MockWsService.return_value.list_resources.return_value = []
        result = materialize_resources(system_app, workspace_id=1)
    assert isinstance(result, MaterializedResources)
    assert result.dynamic_resources == []
    assert result.extra_agents == []


def test_materialize_unknown_type_skipped_not_raised():
    """未知 type（如 slo/oncall_rotation）跳过，不抛异常，记 warning。"""
    system_app = MagicMock()
    unknown_resource = MagicMock(
        type="slo",
        name="p99_latency",
        physical_ref=None,
        config_json='{"metric": "p99", "target": 200}',
        is_active=True,
    )
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService:
        MockWsService.return_value.list_resources.return_value = [unknown_resource]
        result = materialize_resources(system_app, workspace_id=1)
    assert result.dynamic_resources == []
    assert result.extra_agents == []


def test_materialize_mcp_resource_produces_agent_resource():
    """type=mcp 的资源物化成 AgentResource（type=mcp(derisk)）。"""
    system_app = MagicMock()
    mcp_resource = MagicMock(
        type="mcp",
        name="k8s_mcp",
        physical_ref="k8s_mcp_code",
        config_json="{}",
        is_active=True,
    )
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService, patch(
        "derisk_serve.agent.resource.tool.mcp_collect.get_mcp_info"
    ) as mock_get_mcp:
        MockWsService.return_value.list_resources.return_value = [mcp_resource]
        mock_get_mcp.return_value = {
            "mcp_servers": [{"url": "http://k8s-mcp.local"}],
            "headers": {},
            "source": "sse",
            "timeout": 30,
        }
        result = materialize_resources(system_app, workspace_id=1)
    assert len(result.dynamic_resources) == 1
    res = result.dynamic_resources[0]
    assert res.type == "mcp(derisk)"


def test_materialize_inactive_resource_skipped():
    """is_active=False 的资源跳过。"""
    system_app = MagicMock()
    inactive = MagicMock(
        type="mcp",
        name="old_mcp",
        physical_ref="old_code",
        config_json="{}",
        is_active=False,
    )
    with patch(
        "derisk_serve.workspace.materializer.WorkspaceService"
    ) as MockWsService:
        MockWsService.return_value.list_resources.return_value = [inactive]
        result = materialize_resources(system_app, workspace_id=1)
    assert result.dynamic_resources == []
    assert result.extra_agents == []
