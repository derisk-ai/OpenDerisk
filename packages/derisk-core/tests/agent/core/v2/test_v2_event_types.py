from derisk.agent.core.v2.v2_event_types import V2Event, V2EventType


def test_v2_event_creation():
    """测试V2事件创建"""
    event = V2Event(
        event=V2EventType.STEP_START,
        seq=1,
        ts=123456,
        payload={"step_id": "s1", "state": "INIT", "agent_id": "agent-1"},
    )
    assert event["event"] == "step_start"
    assert event["seq"] == 1
    assert event["payload"]["step_id"] == "s1"


def test_v2_event_type_values():
    """测试事件类型值"""
    assert V2EventType.STEP_START == "step_start"
    assert V2EventType.LLM_TOKEN == "llm_token"
    assert V2EventType.TOOL_CALL == "tool_call"
    assert V2EventType.VIS_UPDATE == "vis_update"
    assert V2EventType.DONE == "done"
