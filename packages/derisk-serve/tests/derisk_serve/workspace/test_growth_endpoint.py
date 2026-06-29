"""Tests for workspace growth endpoint."""
from unittest.mock import MagicMock, patch

from derisk_serve.workspace.service.service import WorkspaceService


def test_get_workspace_growth_returns_dict_with_expected_keys():
    """get_workspace_growth 返回含 expected keys。"""
    system_app = MagicMock()
    with patch.object(WorkspaceService, "__init__", lambda self, system_app: None), \
         patch.object(WorkspaceService, "get_growth", return_value={
             "assets_count": 12,
             "evolution_proposals_count": 0,
             "tasks_trend": [{"date": "2026-06-28", "count": 3}],
             "knowledge_graph_nodes": 0,
         }):
        svc = WorkspaceService(system_app=system_app)
        growth = svc.get_growth(workspace_id=1)
    assert "assets_count" in growth
    assert "evolution_proposals_count" in growth
    assert "tasks_trend" in growth
    assert "knowledge_graph_nodes" in growth


def test_get_workspace_growth_proposals_zero_in_p0():
    """P0 阶段演化提议数恒为 0（提议生成 P2 才做）。"""
    system_app = MagicMock()
    with patch.object(WorkspaceService, "__init__", lambda self, system_app: None), \
         patch.object(WorkspaceService, "get_growth", return_value={
             "assets_count": 5,
             "evolution_proposals_count": 0,
             "tasks_trend": [],
             "knowledge_graph_nodes": 0,
         }):
        svc = WorkspaceService(system_app=system_app)
        growth = svc.get_growth(workspace_id=1)
    assert growth["evolution_proposals_count"] == 0


def test_get_growth_uses_large_limit_and_counts_all_assets():
    """超过默认 limit=100 的资产/任务也应被全部统计。"""
    from derisk_serve.task.api.schemas import TaskListFilter
    from derisk_serve.task.service.service import TASK_SERVICE_COMPONENT_NAME
    from derisk_serve.workspace_asset.api.schemas import AssetListFilter
    from derisk_serve.workspace_asset.service.service import (
        ASSET_SERVICE_COMPONENT_NAME,
    )

    system_app = MagicMock()
    asset_svc = MagicMock()
    asset_svc.list_assets.return_value = [MagicMock() for _ in range(150)]
    task_svc = MagicMock()
    task_svc.list_tasks.return_value = []

    def _get_component(name, _cls):
        if name == ASSET_SERVICE_COMPONENT_NAME:
            return asset_svc
        if name == TASK_SERVICE_COMPONENT_NAME:
            return task_svc
        raise KeyError(name)

    system_app.get_component.side_effect = _get_component

    with patch.object(WorkspaceService, "__init__", lambda self, system_app: None):
        svc = WorkspaceService(system_app=system_app)
        svc._system_app = system_app
        growth = svc.get_growth(workspace_id=1)

    assert growth["assets_count"] == 150

    asset_filter = asset_svc.list_assets.call_args.args[0]
    assert isinstance(asset_filter, AssetListFilter)
    assert asset_filter.limit == 10000

    task_filter = task_svc.list_tasks.call_args.args[0]
    assert isinstance(task_filter, TaskListFilter)
    assert task_filter.limit == 10000
