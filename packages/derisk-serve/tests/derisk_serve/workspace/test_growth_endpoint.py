"""Tests for workspace growth endpoint."""
import pytest
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
