"""Tests for nullable task_id and conv_uid on InterventionEntity."""
import pytest

from derisk.storage.metadata import db
from derisk_serve.intervention.models.models import InterventionDao, InterventionEntity


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    with db.session() as session:
        yield session


def test_create_intervention_with_null_task(db_session):
    dao = InterventionDao()
    entity = dao.create(
        workspace_id=1,
        question_json={"tool": "start_task", "args": {"workspace_id": 1}},
        user_id="u1",
        conv_uid="conv-1",
        task_id=None,
    )
    assert entity.id is not None
    assert entity.task_id is None
    assert entity.conv_uid == "conv-1"

    refreshed = (
        db_session.query(InterventionEntity)
        .filter(InterventionEntity.id == entity.id)
        .first()
    )
    assert refreshed is not None
    assert refreshed.task_id is None
    assert refreshed.conv_uid == "conv-1"
