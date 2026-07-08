from unittest.mock import MagicMock, patch

import pytest

from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def minimal_service():
    svc = WorkspaceService(
        system_app=MagicMock(),
        config=MagicMock(),
        dao=MagicMock(),
        member_dao=MagicMock(),
        resource_dao=MagicMock(),
        conv_link_dao=MagicMock(),
    )
    svc.init_app(MagicMock())
    return svc


def _make_request(workspace_code, owner_user_id, default_agent_app_code):
    request = MagicMock()
    request.workspace_code = workspace_code
    request.owner_user_id = owner_user_id
    request.default_agent_app_code = default_agent_app_code
    request.settings = None
    return request


def _make_created(workspace_id, workspace_code, default_agent_app_code):
    created = MagicMock()
    created.id = workspace_id
    created.workspace_code = workspace_code
    created.owner_user_id = 1
    created.default_agent_app_code = default_agent_app_code
    return created


def test_create_binds_scene_agent_when_default_none(minimal_service):
    """创建 workspace 时若 default_agent_app_code 为 None，自动绑定 scene-workspace-agent。"""
    request = _make_request("ws_demo", 1, None)
    created = _make_created(42, "ws_demo", None)

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=42,
            workspace_code="ws_demo",
            default_agent_app_code="scene-workspace-agent",
        )]
    ):
        minimal_service.create(request)

    minimal_service._dao.update.assert_called_once()
    call_args = minimal_service._dao.update.call_args
    assert call_args[0][1]["default_agent_app_code"] == "scene-workspace-agent"


def test_create_binds_scene_agent_when_default_empty_string(minimal_service):
    """创建 workspace 时若 default_agent_app_code 为空字符串，同样自动绑定。"""
    request = _make_request("ws_demo3", 1, "")
    created = _make_created(44, "ws_demo3", "")

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=44,
            workspace_code="ws_demo3",
            default_agent_app_code="scene-workspace-agent",
        )]
    ):
        minimal_service.create(request)

    minimal_service._dao.update.assert_called_once()
    call_args = minimal_service._dao.update.call_args
    assert call_args[0][1]["default_agent_app_code"] == "scene-workspace-agent"


def test_create_keeps_explicit_default_agent(minimal_service):
    """创建 workspace 时若已指定 default_agent_app_code，保持原值。"""
    request = _make_request("ws_demo2", 1, "custom-agent")
    created = _make_created(43, "ws_demo2", "custom-agent")

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=43,
            workspace_code="ws_demo2",
            default_agent_app_code="custom-agent",
        )]
    ):
        minimal_service.create(request)

    minimal_service._dao.update.assert_not_called()
