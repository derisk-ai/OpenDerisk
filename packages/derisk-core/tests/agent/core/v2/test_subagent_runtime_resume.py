import os
import tempfile

import pytest

from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.subagent_handle import SubAgentMode, SubAgentStatus
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _sub_thinking(input_):
    yield {"token": "sub", "tool_calls": []}


async def _sub_acting(tc):
    return {"result": "ok"}


async def test_get_transcript_by_task_id_returns_latest_matching_row(store):
    await store.save_transcript(
        "t-old",
        "task-1",
        "conv-old",
        "step-p",
        "conv-p",
        "BAIZE",
        "running",
        1,
        {"v": "old"},
    )
    await store.save_transcript(
        "t-new",
        "task-1",
        "conv-new",
        "step-p",
        "conv-p",
        "BAIZE",
        "done",
        2,
        {"v": "new"},
    )

    row = await store.get_transcript_by_task_id("task-1")
    assert row is not None
    assert row["transcript_id"] == "t-new"
    assert row["payload"] == {"v": "new"}


async def test_get_transcript_by_task_id_returns_none_if_absent(store):
    assert await store.get_transcript_by_task_id("never-existed") is None


async def test_reconstruct_handle_from_transcript_after_crash(store):
    """P2 follow-up: cross-process resume — reconstruct handle from agent_transcript table."""
    runtime_a = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="BAIZE",
        task="bg work",
        run_in_background=True,
        parent_step_id="step-p",
        parent_conv_id="conv-p",
        parent_agent_id="agent-p",
        depth=0,
        thinking_fn=_sub_thinking,
        acting_fn=_sub_acting,
    )
    handle_a = await runtime_a.spawn(spec)
    await runtime_a.wait(handle_a, timeout=2.0)

    runtime_b = SubAgentRuntime(state_store=store, max_depth=5)

    direct = await runtime_b.reconstruct_handle_from_transcript(handle_a.task_id)
    assert direct is not None
    assert direct.task_id == handle_a.task_id
    assert direct.status is SubAgentStatus.DONE
    assert direct.sub_conv_id == handle_a.sub_conv_id
    assert direct.mode is SubAgentMode.ASYNC

    fetched = await runtime_b.get_status(handle_a.task_id)
    assert fetched is not None
    assert fetched.task_id == handle_a.task_id
    assert fetched.status is SubAgentStatus.DONE
    assert fetched.sub_conv_id == handle_a.sub_conv_id
    assert fetched.mode is SubAgentMode.ASYNC


async def test_resume_falls_back_to_transcript(store):
    runtime_a = SubAgentRuntime(state_store=store, max_depth=5)
    spec = SubAgentSpawnSpec(
        agent_name="BAIZE",
        task="bg",
        run_in_background=True,
        parent_step_id="step-p",
        parent_conv_id="conv-p",
        parent_agent_id="agent-p",
        depth=0,
        thinking_fn=_sub_thinking,
        acting_fn=_sub_acting,
    )
    handle_a = await runtime_a.spawn(spec)
    await runtime_a.wait(handle_a, timeout=2.0)

    runtime_b = SubAgentRuntime(state_store=store, max_depth=5)
    resumed = await runtime_b.resume(handle_a.task_id)
    assert resumed is not None
    assert resumed.task_id == handle_a.task_id


async def test_reconstruct_returns_none_when_no_transcript(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    assert await runtime.get_status("never-existed") is None
