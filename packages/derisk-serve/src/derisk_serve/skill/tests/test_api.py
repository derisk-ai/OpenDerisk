import pytest
from fastapi.testclient import TestClient
from derisk_serve.skill.api.endpoints import router
from derisk_serve.skill.api.schemas import SkillRequest
from derisk_serve.skill.service.service import Service

# Mock the service to avoid database interaction during API tests
@pytest.fixture
def mock_service(mocker):
    service = mocker.MagicMock(spec=Service)
    # Setup default return values if necessary
    return service

@pytest.fixture
def client(mock_service):
    # This fixture needs to properly setup the FastAPI app and override the dependency
    # For a full integration test, you'd setup a test DB.
    # For unit testing the router, we can mock the dependency.
    
    # Since endpoint structure relies on a global app or complex dependency injection, 
    # and given the current environment limitations for full app setup, 
    # we'll focus on unit testing the logic if possible, or skip if too complex to mock.
    # However, creating a simple app to mount the router is standard.
    
    from fastapi import FastAPI
    from derisk_serve.skill.api.endpoints import get_service, check_api_key

    app = FastAPI()
    app.include_router(router)
    
    app.dependency_overrides[get_service] = lambda: mock_service
    # Override auth to allow all requests
    app.dependency_overrides[check_api_key] = lambda: None
    
    return TestClient(app)

def test_create_skill(client, mock_service):
    # Mock response
    mock_service.create.return_value = {
        "skill_code": "123",
        "name": "test-skill",
        "description": "test",
        "type": "python",
        "gmt_created": "2023-01-01T00:00:00",
        "gmt_modified": "2023-01-01T00:00:00"
    }

    response = client.post("/create", json={
        "name": "test-skill",
        "description": "test",
        "type": "python"
    })
    
    assert response.status_code == 200
    assert response.json()["data"]["skill_code"] == "123"

def test_get_skill(client, mock_service):
    mock_service.get.return_value = {
        "skill_code": "123",
        "name": "test-skill",
        "description": "test",
        "type": "python",
        "gmt_created": "2023-01-01T00:00:00",
        "gmt_modified": "2023-01-01T00:00:00"
    }
    
    response = client.post("/query", json={"skill_code": "123"})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "test-skill"

@pytest.mark.asyncio
async def test_sync_git(client, mock_service):
    # Mock the sync_from_git method
    mock_service.sync_from_git.return_value = []
    
    # Use POST as defined in the router
    # Note: query parameters should be in the URL or params argument
    response = client.post(
        "/sync_git", 
        params={
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "force_update": True
        }
    )
    
    assert response.status_code == 200
    assert response.json()["success"] is True

