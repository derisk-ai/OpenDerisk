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
@pytest.mark.asyncio
async def test_step_end_emits_both_step_end_and_done_marker():
    events = [StreamEvent(type="step_end", payload={"conv_id": "c1", "step_id": "s1"}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert len(out) == 2
    assert "step_end" in out[0]
    assert "[DONE]" in out[1]


async def test_workspace_emits_workspace_type():
    events = [StreamEvent(type="workspace", payload={"event_type": "task_created", "x": 1}, seq=0)]
    out = [s async for s in stream_to_sse(_gen(events))]
    assert "task_created" in out[0]
