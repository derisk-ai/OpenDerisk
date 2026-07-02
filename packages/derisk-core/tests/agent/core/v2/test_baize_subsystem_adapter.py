import pytest
from derisk.agent.core.v2.baize_subsystem_adapter import BAIZESubsystemAdapter
from derisk.agent.core.v2.stream_event import StreamEvent


async def _collect(adapter_method, *args):
    emitted = []

    async def emit(evt: StreamEvent):
        emitted.append(evt)

    adapter = BAIZESubsystemAdapter(emit_callback=emit)
    await adapter_method(adapter, *args)
    return emitted


async def test_on_kanban_update_emits_workspace_task_created():
    emitted = await _collect(
        lambda a, s: a.on_kanban_update(s),
        {"task_id": "t1", "title": "do X"},
    )
    assert len(emitted) == 1
    assert emitted[0].type == "workspace"
    assert emitted[0].payload["event_type"] == "task_created"
    assert emitted[0].payload["task_id"] == "t1"


async def test_on_phase_change_emits_workspace_context_loaded():
    emitted = await _collect(
        lambda a, p: a.on_phase_change(p),
        "analysis",
    )
    assert emitted[0].type == "workspace"
    assert emitted[0].payload["event_type"] == "context_loaded"
    assert emitted[0].payload["phase"] == "analysis"


async def test_on_worklog_emits_content():
    emitted = await _collect(
        lambda a, w: a.on_worklog(w),
        {"entry": "did thing"},
    )
    assert emitted[0].type == "content"
    assert emitted[0].payload["entry"] == "did thing"


async def test_on_system_event_emits_workspace_with_custom_type():
    emitted = await _collect(
        lambda a, et, p: a.on_system_event(et, p),
        "artifact_produced", {"artifact_id": "a1"},
    )
    assert emitted[0].type == "workspace"
    assert emitted[0].payload["event_type"] == "artifact_produced"
    assert emitted[0].payload["artifact_id"] == "a1"
