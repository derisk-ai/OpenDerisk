"""P4 Task 4: V2 runtime still works with deprecation warnings on legacy APIs."""
import warnings
import pytest
import tempfile
import os
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


async def test_v2_ask_user_path_still_works_with_deprecation(store):
    """AskUserAdapter path still converts ask_user payloads even though
    ActionOutput.ask_user is now deprecated."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "legacy", "input": {}}]}

    async def acting(tc):
        return {"ask_user": {"message": "hi", "options": []}}

    events = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        async for e in run_step("a", "c", {"prompt": "x"}, store, thinking, acting):
            events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_USER in states
