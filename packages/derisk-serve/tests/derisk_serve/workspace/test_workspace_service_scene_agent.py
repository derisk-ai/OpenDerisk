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


def test_create_binds_scene_agent_when_default_empty(minimal_service):
    """创建 workspace 时若 default_agent_app_code 为空，自动设置为 scene-workspace-agent。"""
    request = MagicMock()
    request.workspace_code = "ws_demo"
    request.owner_user_id = 1
    request.default_agent_app_code = None
    request.settings = None

    created = MagicMock()
    created.id = 42
    created.workspace_code = "ws_demo"
    created.owner_user_id = 1
    created.default_agent_app_code = None

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()
    minimal_service._dao.to_response.return_value = MagicMock(
        id=42,
        workspace_code="ws_demo",
        default_agent_app_code="scene-workspace-agent",
    )

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=42,
            workspace_code="ws_demo",
            default_agent_app_code="scene-workspace-agent",
        )]
    ):
        result = minimal_service.create(request)

    minimal_service._dao.update.assert_called_once()
    call_args = minimal_service._dao.update.call_args
    assert call_args[0][1]["default_agent_app_code"] == "scene-workspace-agent"


def test_create_keeps_explicit_default_agent(minimal_service):
    """创建 workspace 时若已指定 default_agent_app_code，保持原值。"""
    request = MagicMock()
    request.workspace_code = "ws_demo2"
    request.owner_user_id = 1
    request.default_agent_app_code = "custom-agent"
    request.settings = None

    created = MagicMock()
    created.id = 43
    created.workspace_code = "ws_demo2"
    created.owner_user_id = 1
    created.default_agent_app_code = "custom-agent"

    minimal_service._dao.get_one.return_value = None
    minimal_service._dao.create.return_value = created
    minimal_service._member_dao.create.return_value = MagicMock()
    minimal_service._dao.to_response.return_value = MagicMock(
        id=43,
        workspace_code="ws_demo2",
        default_agent_app_code="custom-agent",
    )

    with patch.object(
        minimal_service, "get_by_id", side_effect=[created, MagicMock(
            id=43,
            workspace_code="ws_demo2",
            default_agent_app_code="custom-agent",
        )]
    ):
        minimal_service.create(request)

    minimal_service._dao.update.assert_not_called()