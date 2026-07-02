import os
import tempfile

import pytest

from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_acting_fn_returning_ask_user_emits_awaiting_user(store):
    """P2 follow-up: legacy ActionOutput.ask_user -> AWAITING_USER via AskUserAdapter."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "legacy_action", "input": {}}]}

    async def acting(tc):
        # Legacy Action returns ask_user payload
        return {"ask_user": {"message": "What's your name?", "options": ["Alice", "Bob"]}}

    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store, thinking, acting):
        events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_USER in states
    # The AWAITING_USER event should carry the ask_user payload
    awaiting = [e for e in events if e.state is StepState.AWAITING_USER]
    assert len(awaiting) == 1
    assert awaiting[0].input["type"] == "ASK_USER_LEGACY"
    assert awaiting[0].input["message"] == "What's your name?"
    # Should NOT have a normal OBSERVING event for this tool_call
    observing = [e for e in events if e.state is StepState.OBSERVING]
    assert len(observing) == 0
    # Should NOT reach DONE (step is suspended waiting for user)
    assert states[-1] is not StepState.DONE


async def test_acting_fn_returning_normal_result_still_emits_observing(store):
    """Backwards compat: non-ask_user returns go through normal OBSERVING path."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "normal", "input": {}}]}

    async def acting(tc):
        return {"result": "ok"}

    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store, thinking, acting):
        events.append(e)

    observing = [e for e in events if e.state is StepState.OBSERVING]
    assert len(observing) == 1
    assert observing[0].output == {"result": "ok"}
