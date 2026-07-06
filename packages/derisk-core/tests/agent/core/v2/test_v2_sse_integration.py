# packages/derisk-core/tests/agent/core/v2/test_v2_sse_integration.py
"""V2 SSE集成测试 - 验证完整事件流"""
import asyncio
import json
from derisk.agent.core.v2.v2_event_emitter import V2EventEmitter
from derisk.agent.core.v2.v2_vis_component import VisOperationType, VisComponentTag


async def test_full_event_stream():
    """测试完整事件流生成"""
    emitter = V2EventEmitter(step_id="test-s1", agent_id="test-agent", conv_id="test-conv")
    events = []

    # 生成完整流程事件
    events.append(await emitter.emit_step_start())
    events.append(await emitter.emit_step_status("THINKING"))
    events.append(await emitter.emit_vis_update(
        VisOperationType.REPLACE, "test-s1-step_status-0", VisComponentTag.STEP_STATUS, ""
    ))

    # LLM tokens
    for token in ["你", "好"]:
        events.append(await emitter.emit_llm_token(token))
        events.append(await emitter.emit_vis_update(
            VisOperationType.INCR, "test-s1-thinking-0", VisComponentTag.THINKING, token
        ))

    events.append(await emitter.emit_step_end(had_tool_calls=False))
    events.append(await emitter.emit_done())

    # 验证seq递增
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(1, len(events) + 1))

    # 验证事件类型
    event_types = [e["event"] for e in events]
    assert "step_start" in event_types
    assert "llm_token" in event_types
    assert "vis_update" in event_types
    assert "done" in event_types

    # 验证VIS组件UID格式
    vis_events = [e for e in events if e["event"] == "vis_update"]
    for ve in vis_events:
        payload = ve["payload"]
        assert payload["uid"].startswith("test-s1-")


def run_async_test(coro):
    asyncio.run(coro)

def test_full_event_stream_sync():
    run_async_test(test_full_event_stream())