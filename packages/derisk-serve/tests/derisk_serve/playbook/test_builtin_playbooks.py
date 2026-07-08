"""Tests for built-in playbook templates and seeding."""
from unittest.mock import MagicMock, patch

import pytest

from derisk_serve.playbook.builtin_examples import BUILTIN_PLAYBOOKS
from derisk_serve.playbook.service.service import PlaybookService
from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def playbook_service():
    svc = PlaybookService(MagicMock(), MagicMock())
    svc._dao = MagicMock()
    svc._version_dao = MagicMock()
    svc._system_app = MagicMock()
    return svc


def test_builtin_playbooks_include_data_analysis_and_rca():
    names = {p["name"] for p in BUILTIN_PLAYBOOKS}
    assert "数据分析" in names
    assert "RCA 问题诊断" in names
    assert "Data Operations Weekly Report" in names
    assert "SRE Capacity Inspection" in names
    assert len(BUILTIN_PLAYBOOKS) == 4


def test_seed_builtin_playbooks_creates_missing_and_skips_existing(playbook_service):
    # First seed: empty workspace
    playbook_service._dao.list_by_filter.return_value = []
    playbook_service.create = MagicMock(side_effect=[MagicMock(id=i) for i in range(1, 5)])

    results = playbook_service.seed_builtin_playbooks(workspace_id=1)

    assert playbook_service.create.call_count == 4
    created_names = {r["name"] for r in results if r["status"] == "created"}
    assert created_names == {p["name"] for p in BUILTIN_PLAYBOOKS}

    # Second seed: all already exist
    existing = []
    for p in BUILTIN_PLAYBOOKS:
        mock = MagicMock()
        mock.name = p["name"]
        existing.append(mock)
    playbook_service._dao.list_by_filter.return_value = existing
    playbook_service.create.reset_mock()
    playbook_service.create.side_effect = None

    results2 = playbook_service.seed_builtin_playbooks(workspace_id=1)

    playbook_service.create.assert_not_called()
    assert all(r["status"] == "exists" for r in results2)


def test_workspace_create_auto_seeds_builtin_playbooks():
    svc = WorkspaceService(MagicMock(), MagicMock())
    svc._dao = MagicMock()
    svc._member_dao = MagicMock()
    svc._resource_dao = MagicMock()
    svc._conv_link_dao = MagicMock()
    svc._system_app = MagicMock()

    fake_entity = MagicMock(id=42, owner_user_id=1)
    svc._dao.get_one.return_value = None
    svc._dao.create.return_value = fake_entity

    fake_playbook_service = MagicMock()
    svc._system_app.get_component.return_value = fake_playbook_service

    request = MagicMock()
    request.workspace_code = "ws_test"
    request.owner_user_id = 1

    with patch.object(svc, "get_by_id", return_value=MagicMock()):
        svc.create(request)

    svc._system_app.get_component.assert_called_once()
    fake_playbook_service.seed_builtin_playbooks.assert_called_once_with(42)
