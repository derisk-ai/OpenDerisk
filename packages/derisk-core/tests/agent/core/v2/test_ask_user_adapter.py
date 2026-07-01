import pytest
import tempfile
import os
from derisk.agent.core.v2.ask_user_adapter import AskUserAdapter
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_convert_ask_user_to_event(store):
    """Legacy ActionOutput.ask_user dict → AWAITING_USER StepEvent + checkpoint."""
    adapter = AskUserAdapter(state_store=store)
    ask_payload = {
        "type": "ask_user",
        "message": "What's your name?",
        "options": ["Alice", "Bob"],
    }
    event = await adapter.convert(ask_payload, step_id="step-1", conv_id="conv-1")
    assert event.state is StepState.AWAITING_USER
    assert event.event_type == "interaction_request"
    assert event.input["type"] == "ASK_USER_LEGACY"
    assert event.input["message"] == "What's your name?"
    assert event.input["options"] == ["Alice", "Bob"]
    assert event.input["step_id"] == "step-1"
    assert event.input["conv_id"] == "conv-1"
    assert "request_id" in event.input
    # Checkpoint persisted
    cp = await store.get_interaction_checkpoint(event.input["request_id"])
    assert cp is not None
    assert cp["request_payload"]["type"] == "ASK_USER_LEGACY"


async def test_convert_preserves_request_id_format(store):
    adapter = AskUserAdapter(state_store=store)
    event = await adapter.convert({"message": "hi"}, step_id="s", conv_id="c")
    assert event.input["request_id"].startswith("req-")


async def test_convert_handles_minimal_payload(store):
    """Empty message / no options still works."""
    adapter = AskUserAdapter(state_store=store)
    event = await adapter.convert({}, step_id="s", conv_id="c")
    assert event.input["message"] == ""
    assert event.input["options"] == []
