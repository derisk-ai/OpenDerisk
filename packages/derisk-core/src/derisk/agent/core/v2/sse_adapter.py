"""stream_to_sse — StreamEvent → SSE data line converter.

Spec §10.3. Reuses existing VisProtocolConverter for content events (VIS markdown).
Frontend SSE protocol unchanged — the adapter produces the same `data:{"vis":...}` format.
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

from derisk.agent.core.v2.stream_event import StreamEvent


def _sse_data(vis: Any) -> str:
    return f"data:{json.dumps({'vis': vis}, ensure_ascii=False)}\n\n"


async def stream_to_sse(
    event_stream: AsyncGenerator[StreamEvent, None],
    vis_converter: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """Convert StreamEvents to SSE data lines.

    Args:
        event_stream: async generator of StreamEvent
        vis_converter: optional VisProtocolConverter with .visualization(payload) -> str
            (used for content events to produce VIS markdown)

    Yields:
        SSE-formatted strings (each ending with `\n\n`)
    """
    async for event in event_stream:
        if event.type == "metadata":
            yield _sse_data(
                {
                    "type": "metadata",
                    "conv_session_id": event.payload.get("conv_session_id", ""),
                    "conv_uid": event.payload.get("conv_uid", ""),
                }
            )
        elif event.type == "content":
            if vis_converter is not None:
                yield _sse_data(vis_converter.visualization(event.payload))
            else:
                yield _sse_data({"type": "content", "payload": event.payload})
        elif event.type == "workspace":
            inner_type = event.payload.get("event_type", "workspace")
            inner_payload = {k: v for k, v in event.payload.items() if k != "event_type"}
            yield _sse_data({"type": inner_type, "payload": inner_payload})
        elif event.type == "interaction_request":
            yield _sse_data({"type": "intervention_triggered", "payload": event.payload})
        elif event.type == "usage_metric":
            yield _sse_data({"type": "usage_metric", "payload": event.payload})
        elif event.type == "error":
            yield _sse_data(
                {"type": "error", "content": event.payload.get("message", "")}
            )
        elif event.type == "step_end":
            yield _sse_data({"type": event.type, "payload": event.payload})
            yield 'data:{"vis":"[DONE]"} \n\n'
        elif event.type == "done":
            yield 'data:{"vis":"[DONE]"} \n\n'
        else:
            yield _sse_data({"type": event.type, "payload": event.payload})
