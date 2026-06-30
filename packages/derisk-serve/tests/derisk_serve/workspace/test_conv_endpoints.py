"""Tests for workspace conversation management endpoints."""
from unittest.mock import Mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from derisk.component import SystemApp
from derisk.storage.metadata import db
from derisk_serve.core.tests.conftest import asystem_app  # noqa: F401
from derisk_serve.workspace.api.endpoints import get_service, init_endpoints, router
from derisk_serve.workspace.config import ServeConfig


@pytest.fixture(autouse=True)
def setup_db():
    db.init_db("sqlite:///:memory:")
    db.create_all()
    yield


def _create_app(system_app: SystemApp) -> FastAPI:
    test_app = system_app.app
    test_app.include_router(router)
    init_endpoints(system_app, ServeConfig())
    return test_app


@pytest_asyncio.fixture
async def workspace_client(asystem_app: SystemApp):
    test_app = _create_app(asystem_app)
    async with AsyncClient(
        transport=ASGITransport(test_app), base_url="http://test"
    ) as client:
        yield client, test_app


@pytest.mark.asyncio
async def test_get_current_conversation(workspace_client):
    client, app = workspace_client
    mock_svc = Mock()
    mock_svc.config.api_keys = None
    mock_svc.get_current_conversation.return_value = {
        "conv_uid": "conv-1",
        "title": "t",
        "is_current": True,
    }
    app.dependency_overrides[get_service] = lambda: mock_svc

    res = await client.get(
        "/workspaces/1/conversations/current", headers={"X-User-ID": "u1"}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["conv_uid"] == "conv-1"
    mock_svc.get_current_conversation.assert_called_once_with(
        workspace_id=1, user_id="u1"
    )


@pytest.mark.asyncio
async def test_set_current_conversation(workspace_client):
    client, app = workspace_client
    mock_svc = Mock()
    mock_svc.config.api_keys = None
    mock_svc.set_current_conversation.return_value = {
        "conv_uid": "conv-2",
        "is_current": True,
    }
    app.dependency_overrides[get_service] = lambda: mock_svc

    res = await client.post(
        "/workspaces/1/conversations/set-current",
        json={"conv_uid": "conv-2"},
        headers={"X-User-ID": "u1"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["conv_uid"] == "conv-2"
    mock_svc.set_current_conversation.assert_called_once_with(
        workspace_id=1, user_id="u1", conv_uid="conv-2"
    )


@pytest.mark.asyncio
async def test_rename_conversation(workspace_client):
    client, app = workspace_client
    mock_svc = Mock()
    mock_svc.config.api_keys = None
    mock_svc.rename_conversation.return_value = {
        "conv_uid": "conv-1",
        "title": "new",
    }
    app.dependency_overrides[get_service] = lambda: mock_svc

    res = await client.patch(
        "/conversations/conv-1/rename", json={"title": "new"}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["title"] == "new"
    mock_svc.rename_conversation.assert_called_once_with(
        conv_uid="conv-1", title="new"
    )
