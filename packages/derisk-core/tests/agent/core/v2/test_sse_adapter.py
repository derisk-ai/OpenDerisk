import pytest
import json
from derisk.agent.core.v2.sse_adapter import stream_to_sse
from derisk.agent.core.v2.stream_event import StreamEvent


async def _gen(events):
    for e in events:
        yield e


@pytest.mark.asyncio
async def test_metadata_emits_vis_metadata():
    events = [StreamEvent(type="metadata", payload={"conv_session_id": "s1", "conv_uid": "u1"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 1
    assert "metadata" in out[0]
    assert "u1" in out[0]


@pytest.mark.asyncio
async def test_content_uses_vis_converter():
    class FakeConverter:
        def visualization(self, payload):
            return f"VIS({payload.get('text', '')})"
    events = [StreamEvent(type="content", payload={"text": "hello"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events), vis_converter=FakeConverter())]
    assert len(out) == 1
    assert "VIS(hello)" in out[0]


@pytest.mark.asyncio
async def test_content_without_converter_emits_raw():
    events = [StreamEvent(type="content", payload={"text": "hello"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 1
    assert "hello" in out[0]


@pytest.mark.asyncio
async def test_usage_metric_emits_vis_usage_metric():
    events = [StreamEvent(type="usage_metric", payload={"total": 100}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 1
    parsed = json.loads(out[0].replace("data:", "").strip())
    assert parsed["vis"]["type"] == "usage_metric"
    assert parsed["vis"]["payload"]["total"] == 100


@pytest.mark.asyncio
async def test_done_emits_done_marker():
    events = [StreamEvent(type="done", payload={}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert "[DONE]" in out[0]


@pytest.mark.asyncio
async def test_error_emits_vis_error():
    events = [StreamEvent(type="error", payload={"message": "boom"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert "error" in out[0]
    assert "boom" in out[0]


@pytest.mark.asyncio
async def test_interaction_request_emits_intervention_triggered():
    events = [StreamEvent(type="interaction_request", payload={"request_id": "r1"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert "intervention_triggered" in out[0]


@pytest.mark.asyncio
async def test_llm_token_emits_string_vis():
    """BAIZE compat: token emitted as string vis so frontend appends to message text."""
    events = [StreamEvent(type="llm_token", payload={"token": "Hello"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 1
    parsed = json.loads(out[0].replace("data:", "").strip())
    assert parsed["vis"] == "Hello"  # string, not object


@pytest.mark.asyncio
async def test_step_start_is_suppressed():
    """No BAIZE vis equivalent — suppress to avoid raw-object-as-text rendering."""
    events = [StreamEvent(type="step_start", payload={"prompt": "hi"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 0


@pytest.mark.asyncio
async def test_step_end_is_suppressed():
    """step_end has no BAIZE vis equivalent — suppress; [DONE] emitted by caller."""
    events = [StreamEvent(type="step_end", payload={"conv_id": "c1", "step_id": "s1"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 0


@pytest.mark.asyncio
async def test_tool_call_is_suppressed():
    """tool_call has no BAIZE vis equivalent — suppress."""
    events = [StreamEvent(type="tool_call", payload={"tool": "read_file"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 0


@pytest.mark.asyncio
async def test_tool_result_is_suppressed():
    """tool_result has no BAIZE vis equivalent — suppress."""
    events = [StreamEvent(type="tool_result", payload={"content": "data"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 0


@pytest.mark.asyncio
async def test_workspace_is_suppressed():
    """workspace events without BAIZE equivalent — suppress."""
    events = [StreamEvent(type="workspace", payload={"event_type": "task_created", "x": 1}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 0
