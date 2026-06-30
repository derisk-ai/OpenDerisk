"""Tests for WorkspaceConversationLinkDao."""
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.workspace.models.models import (
    WorkspaceConversationLinkDao,
    WorkspaceConversationLinkEntity,
)
from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    with db.session() as session:
        yield session


@pytest.fixture
def service(db_session):
    system_app = MagicMock()
    config = MagicMock()
    return WorkspaceService(
        system_app=system_app,
        config=config,
        conv_link_dao=WorkspaceConversationLinkDao(),
    )


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


# ---------------- Conversation service ----------------


def test_service_set_current_persists(service, db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1)

    service.set_current_conversation(workspace_id=1, user_id=1, conv_uid="conv-2")

    current = service.get_current_conversation(workspace_id=1, user_id=1)
    assert current["conv_uid"] == "conv-2"
    refreshed_first = _refresh(db_session, "conv-1")
    refreshed_second = _refresh(db_session, "conv-2")
    assert refreshed_first.is_current is False
    assert refreshed_second.is_current is True


def test_service_set_current_wrong_user_raises(service):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=2)
    with pytest.raises(ValueError, match="not linked to workspace 1 for user 1"):
        service.set_current_conversation(workspace_id=1, user_id=1, conv_uid="conv-1")


def test_service_rename(service, db_session):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=1)
    renamed = service.rename_conversation(conv_uid="conv-1", title="my title")
    assert renamed["title"] == "my title"
    refreshed = _refresh(db_session, "conv-1")
    assert refreshed.title == "my title"


def test_service_get_current_conversation_none_when_not_set(service):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=1)
    current = service.get_current_conversation(workspace_id=1, user_id=1)
    assert current is None
