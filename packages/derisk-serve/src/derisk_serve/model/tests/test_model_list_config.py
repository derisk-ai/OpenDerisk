import pytest
import asyncio
from unittest.mock import MagicMock
from fastapi import FastAPI
from httpx import AsyncClient

from derisk.component import SystemApp
from derisk.model.cluster import WorkerManager
from derisk.model.cluster.controller.controller import BaseModelController
from derisk.model.parameter import WorkerType
from derisk.storage.metadata import db
from derisk_serve.core.tests.conftest import (  # noqa: F401
    asystem_app,
    client,
    system_app,
)

from ..api.endpoints import init_endpoints, router, get_model_controller
from ..config import SERVE_CONFIG_KEY_PREFIX, ServeConfig


@pytest.fixture(autouse=True)
def setup_and_teardown():
    # DB initialization is not needed for this test as we mock the controller
    # and do not access the database directly in the tested code path.
    yield


def client_init_caller(app: FastAPI, system_app: SystemApp):
    app.include_router(router)
    # Mock ServeConfig for init_endpoints
    serve_config = ServeConfig()
    init_endpoints(system_app, serve_config)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client, asystem_app",
    [
        (
            {"app_caller": client_init_caller},
            {
                "app_config": {
                    "agent.llm.model": "gpt-4o",
                    "agent.llm.provider": "openai",
                }
            },
        )
    ],
    indirect=["client", "asystem_app"],
)
async def test_model_list_with_config(client: AsyncClient, asystem_app: SystemApp):
    # Mock BaseModelController to return empty list (no cluster models)
    mock_controller = MagicMock(spec=BaseModelController)
    
    # Configure the mock to behave like an awaitable for async method
    future = asyncio.Future()
    future.set_result([])
    mock_controller.get_all_instances.return_value = future
    
    # Access the FastAPI app from the SystemApp to set dependency overrides
    app = asystem_app.app
    app.dependency_overrides[get_model_controller] = lambda: mock_controller

    response = await client.get("/models")
    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    
    models = result["data"]
    # Should contain the configured model
    assert len(models) == 1
    model = models[0]
    assert model["model_name"] == "gpt-4o"
    assert model["worker_type"] == "llm"
    assert model["host"] == "cloud-proxy"
    assert model["healthy"] is True
