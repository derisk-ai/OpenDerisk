"""Tests for InterventionService.execute_resolved routing."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The task package __init__ eagerly imports endpoints -> runtime -> agent
# controller, which requires derisk_app.config. Provide a lightweight stub so
# unit tests can import task/playbook modules without the full derisk_app
# package installed.
if "derisk_app.config" not in sys.modules:
    sys.modules["derisk_app"] = MagicMock()
    sys.modules["derisk_app.config"] = MagicMock()

from derisk_serve.intervention.service.service import InterventionService


@pytest.fixture
def fake_system_app():
    return MagicMock()


@pytest.fixture
def service(fake_system_app):
    svc = InterventionService(fake_system_app, config=MagicMock())
    svc._dao = MagicMock()
    svc._system_app = fake_system_app
    return svc


def _make_session(entity):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = entity
    return session


@pytest.mark.asyncio
async def test_execute_resolved_routes_start_task(fake_system_app, service):
    entity = MagicMock(
        id=1,
        conv_uid="conv-1",
        task_id=None,
        question_json={
            "tool": "start_task",
            "args": {"workspace_id": 1, "playbook_id": 10, "title": "t"},
        },
        status="requested",
    )
    service._dao.get_raw_session.return_value = _make_session(entity)

    task_service = MagicMock()
    task_service.create.return_value = MagicMock(id=99)
    fake_system_app.get_component.return_value = task_service

    mock_pmb = AsyncMock()
    service._post_message_back = mock_pmb
    result = await service.execute_resolved(1, "approved", None, 1)

    task_service.create.assert_called_once()
    req = task_service.create.call_args[0][0]
    assert req.workspace_id == 1
    assert req.title == "t"
    assert result is entity
    assert entity.status == "resolved"
    mock_pmb.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_resolved_unknown_tool_raises(fake_system_app, service):
    entity = MagicMock(
        id=1,
        conv_uid="conv-1",
        question_json={"tool": "unknown_tool", "args": {}},
        status="requested",
    )
    service._dao.get_raw_session.return_value = _make_session(entity)

    mock_pmb = AsyncMock()
    service._post_message_back = mock_pmb
    with pytest.raises(ValueError, match="Unknown tool"):
        await service.execute_resolved(1, "approved", None, 1)

    mock_pmb.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_resolved_rejected(fake_system_app, service):
    entity = MagicMock(
        id=1,
        conv_uid="conv-1",
        question_json={"tool": "start_task", "args": {}},
        status="requested",
    )
    service._dao.get_raw_session.return_value = _make_session(entity)
    task_service = MagicMock()
    fake_system_app.get_component.return_value = task_service

    mock_pmb = AsyncMock()
    service._post_message_back = mock_pmb
    await service.execute_resolved(1, "rejected", None, 1)

    task_service.create.assert_not_called()
    assert entity.status == "rejected"
    mock_pmb.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_resolved_routes_publish_asset(fake_system_app, service):
    entity = MagicMock(
        id=1,
        conv_uid="conv-1",
        question_json={
            "tool": "publish_asset",
            "args": {"workspace_id": 2, "type": "case", "name": "asset-name"},
        },
        status="requested",
    )
    service._dao.get_raw_session.return_value = _make_session(entity)

    asset_service = MagicMock()
    asset_service.create.return_value = MagicMock(id=88)
    fake_system_app.get_component.return_value = asset_service

    mock_pmb = AsyncMock()
    service._post_message_back = mock_pmb
    await service.execute_resolved(1, "approved", None, 1)

    asset_service.create.assert_called_once()
    req = asset_service.create.call_args[0][0]
    assert req.workspace_id == 2
    assert req.name == "asset-name"
    assert req.is_published is True
    assert entity.status == "resolved"
    mock_pmb.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_message_back_skips_without_conv_uid(fake_system_app, service):
    with patch("derisk_serve.agent.agents.controller.multi_agents") as m:
        m.app_chat.return_value = async_generator([])
        await service._post_message_back(None, "start_task", {"task_id": 1}, 1)
    m.app_chat.assert_not_called()


@pytest.mark.asyncio
async def test_post_message_back_calls_app_chat(fake_system_app, service):
    with patch("derisk_serve.agent.agents.controller.multi_agents") as m:
        m.app_chat.return_value = async_generator([])
        await service._post_message_back("conv-1", "start_task", {"task_id": 1}, 1)
    m.app_chat.assert_called_once()
    call_kwargs = m.app_chat.call_args.kwargs
    assert call_kwargs["conv_uid"] == "conv-1"
    assert call_kwargs["gpts_name"] == "chat_normal"
    assert "start_task" in call_kwargs["user_query"]
    assert call_kwargs["user_code"] == "1"


@pytest.mark.asyncio
async def test_post_message_back_uses_workspace_default_agent_app_code(
    fake_system_app, service
):
    workspace = MagicMock(default_agent_app_code="scenario_workspace_agent")
    workspace_service = MagicMock()
    workspace_service.get_by_id.return_value = workspace
    fake_system_app.get_component.return_value = workspace_service

    with patch("derisk_serve.agent.agents.controller.multi_agents") as m:
        m.app_chat.return_value = async_generator([])
        await service._post_message_back(
            "conv-1", "start_task", {"task_id": 1}, 1, workspace_id=42
        )
    m.app_chat.assert_called_once()
    call_kwargs = m.app_chat.call_args.kwargs
    assert call_kwargs["gpts_name"] == "scenario_workspace_agent"
    workspace_service.get_by_id.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_post_message_back_falls_back_when_workspace_has_no_default_app(
    fake_system_app, service
):
    workspace = MagicMock(default_agent_app_code=None)
    workspace_service = MagicMock()
    workspace_service.get_by_id.return_value = workspace
    fake_system_app.get_component.return_value = workspace_service

    with patch("derisk_serve.agent.agents.controller.multi_agents") as m:
        m.app_chat.return_value = async_generator([])
        await service._post_message_back(
            "conv-1", "start_task", {"task_id": 1}, 1, workspace_id=42
        )
    m.app_chat.assert_called_once()
    assert m.app_chat.call_args.kwargs["gpts_name"] == "chat_normal"


async def async_generator(items):
    for item in items:
        yield item
