import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _subagent_thinking(input_):
    yield {"token": "sub"}
    yield {"token": "", "tool_calls": []}


async def _acting_fn(tc):
    # Should not be called for spawn_subagent — runtime intercepts
    return {"result": "should not reach"}


async def test_run_step_sync_subagent_emits_awaiting_sub_agent(store):
    sub_runtime = SubAgentRuntime(state_store=store, max_depth=5)

    async def _parent_thinking_with_sub(input_):
        yield {"token": "calling sub"}
        yield {
            "token": "",
            "tool_calls": [{
                "tool": "spawn_subagent",
                "input": {
                    "agent_name": "BAIZE",
                    "task": "do thing",
                    "run_in_background": False,
                    # Inject sub-agent fns via context (runtime knows to read them)
                    "_sub_thinking_fn": _subagent_thinking,
                    "_sub_acting_fn": lambda tc: {"result": "sub-ok"},
                },
            }],
        }

    events = []
    async for e in run_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store,
        _parent_thinking_with_sub, _acting_fn,
        subagent_runtime=sub_runtime,
    ):
        events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_SUB_AGENT in states
    # After AWAITING_SUB_AGENT, should go to OBSERVING then DONE
    assert states[-1] is StepState.DONE
    # The OBSERVING event should carry the sub-agent's result
    observing = [e for e in events if e.state is StepState.OBSERVING]
    assert len(observing) >= 1
    # The tool_result for spawn_subagent includes the handle
    assert observing[-1].output.get("status") == "done" or "task_id" in observing[-1].output


async def test_run_step_without_subagent_runtime_falls_back_to_acting_fn(store):
    """If subagent_runtime is None, spawn_subagent tool_call goes to acting_fn (backwards compat)."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "spawn_subagent", "input": {}}]}

    async def acting(tc):
        return {"result": "legacy path"}

    events = []
    async for e in run_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store,
        thinking, acting,
        subagent_runtime=None,
    ):
        events.append(e)
    observing = [e for e in events if e.state is StepState.OBSERVING]
    assert len(observing) == 1
    assert observing[0].output == {"result": "legacy path"}
