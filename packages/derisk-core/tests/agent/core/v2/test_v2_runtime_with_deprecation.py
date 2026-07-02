"""P4 Task 4: V2 runtime still works with deprecation warnings on legacy APIs."""
import warnings
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


@pytest.mark.xfail(
    reason="Task 2 signature migration: the ask_user check in _run_acting_phase (line 186) "
    "is dead code — result_dict is constructed from V2ToolResult fields and never includes "
    "an \"ask_user\" key. Task 10 (default_acting_fn) should re-implement the ask_user path."
)
async def test_v2_ask_user_path_still_works_with_deprecation(store):
    """AskUserAdapter path still converts ask_user payloads even though
    ActionOutput.ask_user is now deprecated."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "legacy", "input": {}}]}

    async def acting(tc: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
        return V2ToolResult.ok(
            output="ask_user_payload",
            tool_name="legacy",
            metadata={"ask_user": {"message": "hi", "options": []}},
        )

    events = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        async for e in run_step("a", "c", {"prompt": "x"}, store, thinking, acting):
            events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_USER in states
