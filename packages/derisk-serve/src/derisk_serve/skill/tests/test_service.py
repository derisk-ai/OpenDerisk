import pytest
from unittest.mock import MagicMock
from derisk_serve.skill.service.service import Service
from derisk_serve.skill.api.schemas import SkillRequest

@pytest.fixture
def mock_dao():
    return MagicMock()

@pytest.fixture
def service(mock_dao):
    system_app = MagicMock()
    config = MagicMock()
    return Service(system_app, config, dao=mock_dao)

def test_create(service, mock_dao):
    req = SkillRequest(name="test", description="desc", type="type")
    service.create(req)
    mock_dao.create.assert_called_once()
    
    # Check that skill_code was generated
    call_args = mock_dao.create.call_args[0][0]
    assert call_args.skill_code is not None

def test_update(service, mock_dao):
    req = SkillRequest(skill_code="123", name="test_updated", description="desc", type="type")
    service.update(req)
    
    mock_dao.update.assert_called_once()
    assert mock_dao.update.call_args[0][0] == {"skill_code": "123"}
    
    # Check that read-only fields were removed
    update_data = mock_dao.update.call_args[0][1]
    assert "skill_code" not in update_data

def test_delete(service, mock_dao):
    req = SkillRequest(skill_code="123", name="test", description="desc", type="type")
    service.delete(req)
    mock_dao.delete.assert_called_once_with(req)

def test_get(service, mock_dao):
    req = SkillRequest(skill_code="123", name="test", description="desc", type="type")
    service.get(req)
    mock_dao.get_one.assert_called_once_with(req)
