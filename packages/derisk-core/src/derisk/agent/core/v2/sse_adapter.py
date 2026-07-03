"""stream_to_sse — StreamEvent → SSE data line converter.

Emits BAIZE-compatible vis format so the existing frontend (use-chat.ts) renders
V2 events the same way it renders BAIZE events:
  - text tokens  → data:{"vis":"<text>"}\n\n          (string vis, appended to current message)
  - metadata     → data:{"vis":{"type":"metadata",...}}\n\n
  - error        → data:{"vis":{"type":"error","content":"..."}}\n\n
  - interaction  → data:{"vis":{"type":"intervention_triggered","payload":{...}}}\n\n
  - usage_metric → data:{"vis":{"type":"usage_metric","payload":{...}}}\n\n
  - done         → data:{"vis":"[DONE]"} \n\n

Internal V2 events without a BAIZE equivalent (step_start, step_end, tool_call,
tool_result, sub_agent_start) are suppressed — the frontend has no vis type for
them and would otherwise render the raw object as text.
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

from derisk.agent.core.v2.stream_event import StreamEvent


def _sse_data(vis: Any) -> str:
    return f"data:{json.dumps({'vis': vis}, ensure_ascii=False)}\n\n"


def _sse_text(token: str) -> str:
    """String vis — frontend appends to current message text."""
    return f"data:{json.dumps({'vis': token}, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return 'data:{"vis":"[DONE]"} \n\n'


async def stream_to_sse(
    event_stream: AsyncGenerator[StreamEvent, None],
    vis_converter: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """Convert StreamEvents to BAIZE-compatible SSE data lines."""
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
        elif event.type == "llm_token":
            # BAIZE compat: emit token as string vis so frontend appends to message
            token = event.payload.get("token", "")
            if token:
                yield _sse_text(token)
        elif event.type == "interaction_request":
            yield _sse_data({"type": "intervention_triggered", "payload": event.payload})
        elif event.type == "usage_metric":
            yield _sse_data({"type": "usage_metric", "payload": event.payload})
        elif event.type == "error":
            yield _sse_data(
                {"type": "error", "content": event.payload.get("message", "")}
            )
        elif event.type in ("step_start", "step_end", "tool_call", "tool_result",
                            "sub_agent_start", "workspace"):
            # No BAIZE vis equivalent — suppress to avoid raw-object-as-text rendering
            continue
        elif event.type == "done":
            yield _sse_done()
        else:
            # Unknown type — suppress by default to avoid frontend fallback to text
            continue
