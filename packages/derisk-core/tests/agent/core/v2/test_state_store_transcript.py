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


async def test_save_and_get_transcript(store):
    await store.save_transcript(
        transcript_id="t-1", task_id="task-1", sub_conv_id="conv-sub",
        parent_step_id="step-p", parent_conv_id="conv-p", agent_name="BAIZE",
        status="running", latest_event_seq=5,
        payload={"prompt": "hi", "last_token": "..."},
    )
    row = await store.get_transcript("t-1")
    assert row is not None
    assert row["transcript_id"] == "t-1"
    assert row["task_id"] == "task-1"
    assert row["sub_conv_id"] == "conv-sub"
    assert row["parent_conv_id"] == "conv-p"
    assert row["agent_name"] == "BAIZE"
    assert row["status"] == "running"
    assert row["latest_event_seq"] == 5
    assert row["payload"]["prompt"] == "hi"


async def test_get_transcript_returns_none_if_absent(store):
    assert await store.get_transcript("nope") is None


async def test_list_transcripts_for_parent(store):
    await store.save_transcript(
        "t-1", "task-1", "conv-sub-1", "step-p", "conv-p", "BAIZE",
        "running", 0, {},
    )
    await store.save_transcript(
        "t-2", "task-2", "conv-sub-2", "step-p2", "conv-p", "BAIZE",
        "done", 10, {"result": "ok"},
    )
    await store.save_transcript(
        "t-3", "task-3", "conv-sub-3", "step-p3", "conv-other", "BAIZE",
        "running", 0, {},
    )
    rows = await store.list_transcripts_for_parent("conv-p")
    assert len(rows) == 2
    task_ids = {r["task_id"] for r in rows}
    assert task_ids == {"task-1", "task-2"}


async def test_delete_transcript(store):
    await store.save_transcript(
        "t-1", "task-1", "conv-sub", "step-p", "conv-p", "BAIZE",
        "running", 0, {},
    )
    await store.delete_transcript("t-1")
    assert await store.get_transcript("t-1") is None


async def test_delete_absent_is_noop(store):
    await store.delete_transcript("never-existed")  # no error


async def test_save_transcript_overwrites_on_same_id(store):
    await store.save_transcript(
        "t-1", "task-1", "conv-sub", "step-p", "conv-p", "BAIZE",
        "running", 0, {"v": 1},
    )
    await store.save_transcript(
        "t-1", "task-1", "conv-sub", "step-p", "conv-p", "BAIZE",
        "done", 20, {"v": 2, "result": "ok"},
    )
    row = await store.get_transcript("t-1")
    assert row["status"] == "done"
    assert row["latest_event_seq"] == 20
    assert row["payload"]["v"] == 2
