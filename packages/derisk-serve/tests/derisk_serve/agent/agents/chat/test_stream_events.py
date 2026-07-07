"""Tests for workspace stream event helpers."""
import json
from derisk_serve.agent.agents.chat.agent_chat import (
    format_workspace_event,
    WORKSPACE_EVENT_TYPES,
)


def test_format_workspace_event_context_loaded():
    """context_loaded 事件格式正确。"""
    chunk = format_workspace_event(
        "context_loaded",
        {"skills": ["db_query", "anomaly_detect"], "assets": ["asset_78"]},
    )
    assert chunk.startswith("data:")
    assert chunk.endswith("\n\n")
    payload = json.loads(chunk[len("data:"):].strip())
    assert payload["vis"]["type"] == "context_loaded"
    assert payload["vis"]["payload"]["skills"] == ["db_query", "anomaly_detect"]


def test_format_workspace_event_task_created():
    """task_created 事件格式正确。"""
    chunk = format_workspace_event(
        "task_created", {"task_id": 124, "title": "容量巡检"}
    )
    payload = json.loads(chunk[len("data:"):].strip())
    assert payload["vis"]["type"] == "task_created"
    assert payload["vis"]["payload"]["task_id"] == 124


def test_format_workspace_event_invalid_type_returns_empty():
    """非法事件 type 不抛异常，记录 warning 并返回空串。"""
    chunk = format_workspace_event("bogus_type", {})
    assert chunk == ""


def test_workspace_event_types_contains_expected():
    """事件 type 白名单含预期的 6 种。"""
    expected = {
        "task_created",
        "context_loaded",
        "intervention_triggered",
        "artifact_produced",
        "delivery_sent",
        "asset_referenced",
    }
    assert expected.issubset(WORKSPACE_EVENT_TYPES)
