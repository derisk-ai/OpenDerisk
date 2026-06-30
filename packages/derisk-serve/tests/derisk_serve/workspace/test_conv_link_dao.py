"""Tests for WorkspaceConversationLinkDao."""
import pytest

from derisk.storage.metadata import db
from derisk_serve.workspace.models.models import (
    WorkspaceConversationLinkDao,
    WorkspaceConversationLinkEntity,
)


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    with db.session() as session:
        yield session


def _refresh(session, conv_uid):
    return (
        session.query(WorkspaceConversationLinkEntity)
        .filter(WorkspaceConversationLinkEntity.conv_uid == conv_uid)
        .first()
    )


def test_link_with_set_current_flips_previous(db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, set_current=True)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1, set_current=True)

    refreshed_first = _refresh(db_session, "conv-1")
    refreshed_second = _refresh(db_session, "conv-2")
    assert refreshed_first.is_current is False
    assert refreshed_second.is_current is True


def test_get_current_conversation(db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, set_current=True)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1, set_current=False)

    current = dao.get_current(workspace_id=1, user_id=1)
    assert current.conv_uid == "conv-1"


def test_rename_conversation(db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, title="old")
    dao.rename(conv_uid="conv-1", title="new title")

    refreshed = _refresh(db_session, "conv-1")
    assert refreshed.title == "new title"


def test_to_response_includes_new_fields():
    entity = WorkspaceConversationLinkEntity(
        id=1,
        workspace_id=1,
        conv_uid="conv-1",
        task_id=2,
        user_id=3,
        title="title",
        is_current=True,
    )
    response = WorkspaceConversationLinkDao().to_response(entity)
    assert response["title"] == "title"
    assert response["is_current"] is True
