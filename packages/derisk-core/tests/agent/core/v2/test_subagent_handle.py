# packages/derisk-core/tests/agent/core/v2/test_subagent_handle.py
import time
from derisk.agent.core.v2.subagent_handle import (
    SubAgentHandle, SubAgentMode, SubAgentStatus,
)


def _make_handle(**overrides):
    defaults = dict(
        task_id="task-1", parent_step_id="step-p", parent_conv_id="conv-p",
        sub_conv_id="conv-sub", agent_name="BAIZE",
        mode=SubAgentMode.SYNC, status=SubAgentStatus.RUNNING,
        created_at=time.time(), updated_at=time.time(),
    )
    defaults.update(overrides)
    return SubAgentHandle(**defaults)


def test_handle_basic_fields():
    h = _make_handle()
    assert h.task_id == "task-1"
    assert h.mode is SubAgentMode.SYNC
    assert h.status is SubAgentStatus.RUNNING
    assert h.result is None


def test_is_done_true_for_terminal_states():
    assert _make_handle(status=SubAgentStatus.DONE).is_done()
    assert _make_handle(status=SubAgentStatus.FAILED).is_done()
    assert _make_handle(status=SubAgentStatus.CANCELLED).is_done()


def test_is_done_false_for_running():
    assert not _make_handle(status=SubAgentStatus.RUNNING).is_done()
    assert not _make_handle(status=SubAgentStatus.PENDING).is_done()


def test_to_payload_roundtrip():
    h = _make_handle(
        status=SubAgentStatus.DONE,
        result={"answer": 42},
        transcript_id="t-1",
    )
    p = h.to_payload()
    assert p["task_id"] == "task-1"
    assert p["status"] == "done"
    assert p["result"] == {"answer": 42}
    assert p["transcript_id"] == "t-1"


def test_async_mode():
    h = _make_handle(mode=SubAgentMode.ASYNC, transcript_id="t-1")
    assert h.mode is SubAgentMode.ASYNC
    assert h.transcript_id == "t-1"
