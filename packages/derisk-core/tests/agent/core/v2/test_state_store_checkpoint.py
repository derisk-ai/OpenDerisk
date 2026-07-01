import pytest
import tempfile
import os
from derisk.agent.core.v2.state_store import DbStateStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_save_and_get_checkpoint(store):
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1",
        {"type": "AUTHORIZE", "tool_name": "read_file", "options": []},
    )
    row = await store.get_interaction_checkpoint("req-1")
    assert row is not None
    assert row["request_id"] == "req-1"
    assert row["step_id"] == "step-1"
    assert row["conv_id"] == "conv-1"
    assert row["request_payload"]["tool_name"] == "read_file"
    assert "created_at" in row


async def test_get_checkpoint_returns_none_if_absent(store):
    assert await store.get_interaction_checkpoint("nope") is None


async def test_delete_checkpoint(store):
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1", {"tool": "x"}
    )
    await store.delete_interaction_checkpoint("req-1")
    assert await store.get_interaction_checkpoint("req-1") is None


async def test_delete_absent_checkpoint_is_noop(store):
    await store.delete_interaction_checkpoint("never-existed")  # no error


async def test_save_checkpoint_overwrites_on_same_request_id(store):
    # Primary key is request_id — saving twice with same id should replace
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1", {"v": 1}
    )
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1", {"v": 2}
    )
    row = await store.get_interaction_checkpoint("req-1")
    assert row["request_payload"]["v"] == 2
