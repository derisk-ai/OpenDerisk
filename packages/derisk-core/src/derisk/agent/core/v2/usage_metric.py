"""usage_metric — real-time token observability (spec §10.7).

emit_usage_metric() is called after each LLM call. It reads prior usage_metric
StepEvents from StateStore to compute cumulative totals, looks up the model's
context window from ModelConfigCache, and emits a new usage_metric StepEvent.

aggregate_usage() sums all usage_metric events for a conversation.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from derisk.agent.core.v2.step_state import StepState


_CONTEXT_WINDOW_KEYS = (
    "context_length",
    "max_context_length",
    "max_context_len",
    "context_window",
    "max_context_window",
    "max_tokens",
)


def _get_context_window(model: str) -> int:
    """Look up a model's context window. Returns 0 if unknown."""
    try:
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache

        cfg = ModelConfigCache.get_config(model)
    except Exception:
        return 0

    if not isinstance(cfg, dict):
        return 0

    for key in _CONTEXT_WINDOW_KEYS:
        value = cfg.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


async def aggregate_usage(store: Any, conv_id: str) -> Dict[str, int]:
    """Sum all usage_metric events for conv_id."""
    events = await store.get_events(conv_id)
    aggregate = {"prompt": 0, "completion": 0, "total": 0}
    for event in events:
        if event.event_type != "usage_metric":
            continue
        this_call = event.output.get("this_call", {})
        aggregate["prompt"] += int(this_call.get("prompt", 0) or 0)
        aggregate["completion"] += int(this_call.get("completion", 0) or 0)
        aggregate["total"] += int(this_call.get("total", 0) or 0)
    return aggregate


async def emit_usage_metric(
    store: Any,
    emit: Callable[..., Awaitable[Any]],
    step_id: str,
    conv_id: str,
    agent_id: str,
    llm_call_id: str,
    model: str,
    this_call: Dict[str, int],
) -> None:
    """Emit a usage_metric StepEvent with this call, cumulative totals, and ratio."""
    aggregate = await aggregate_usage(store, conv_id)
    cumulative = {
        "prompt": aggregate["prompt"] + int(this_call.get("prompt", 0) or 0),
        "completion": aggregate["completion"] + int(this_call.get("completion", 0) or 0),
        "total": aggregate["total"] + int(this_call.get("total", 0) or 0),
    }
    context_window = _get_context_window(model)
    ratio = cumulative["total"] / context_window if context_window > 0 else 0.0

    await emit(
        StepState.THINKING,
        "usage_metric",
        output_data={
            "step_id": step_id,
            "conv_id": conv_id,
            "agent_id": agent_id,
            "llm_call_id": llm_call_id,
            "model": model,
            "this_call": this_call,
            "cumulative": cumulative,
            "context_window": context_window,
            "ratio": ratio,
        },
    )
