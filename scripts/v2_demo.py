"""V2 Runtime 最小可运行 demo — 验证 run_step + StepEvent → StreamEvent → SSE 全链路。

跑法：
    cd /Users/tuyang/GitHub/OpenDerisk
    python scripts/v2_demo.py
"""
import asyncio
import tempfile
import os
import json

from derisk.agent.core.v2 import (
    DbStateStore,
    run_step,
    resume_step,
    StepState,
    step_event_to_stream_event,
    stream_to_sse,
    EventStream,
    PermissionGate,
    PermissionMode,
    SubAgentRuntime,
    SubAgentSpawnSpec,
    emit_usage_metric,
    aggregate_usage,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall, V2ToolResult
from derisk.agent.tools.context import ToolContext


async def thinking_fn(input_):
    """模拟 LLM 流式输出 + 工具调用。带 usage 字段验证 §10.7。"""
    yield {"token": "你好", "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
    yield {"token": "，我来帮你", "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}}
    yield {
        "token": "",
        "tool_calls": [{"tool": "read_file", "input": {"path": "/tmp/x"}}],
    }


async def acting_fn(tool_call: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
    """模拟工具执行。"""
    return V2ToolResult.ok(output=f"读到了 {tool_call.name} 的内容", tool_name=tool_call.name)


async def main():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = DbStateStore(path)

    print("=" * 60)
    print("Phase 1: run_step — 跑一个完整 step, 收集 StepEvent")
    print("=" * 60)

    events = []
    async for e in run_step(
        agent_id="demo-agent",
        conv_id="demo-conv",
        input_={"prompt": "hi"},
        state_store=store,
        thinking_fn=thinking_fn,
        acting_fn=acting_fn,
    ):
        events.append(e)
        print(f"  [{e.state.value:15}] {e.event_type:20} seq={e.seq}")

    # 发一个 usage_metric 事件验证 §10.7 链路
    print("\nPhase 1b: 发 usage_metric 事件 (§10.7 实时可观测性)")
    stream = EventStream(store)
    existing = await store.get_events("demo-conv")
    seq_start = existing[-1].seq + 1 if existing else 0

    async def emit(state, event_type, input_data=None, output_data=None):
        import time, uuid
        from derisk.agent.core.v2 import StepEvent
        evt = StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id="step-demo",
            conv_id="demo-conv",
            agent_id="demo-agent",
            parent_step_id=None,
            state=state,
            event_type=event_type,
            input=input_data or {},
            output=output_data or {},
            seq=seq_start,
            timestamp=time.time(),
        )
        return await stream.emit(evt)

    await emit_usage_metric(
        store=store, emit=emit,
        step_id="step-demo", conv_id="demo-conv", agent_id="demo-agent",
        llm_call_id="call-1", model="claude-sonnet-4-6",
        this_call={"prompt": 20, "completion": 6, "total": 26},
    )
    agg = await aggregate_usage(store, "demo-conv")
    print(f"  cumulative usage: {agg}")

    print("\n" + "=" * 60)
    print("Phase 2: StepEvent → StreamEvent → SSE (前端协议)")
    print("=" * 60)

    async def stream_gen():
        for e in events:
            yield step_event_to_stream_event(e)

    async for sse_line in stream_to_sse(stream_gen()):
        print(f"  {sse_line.rstrip()}")

    print("\n" + "=" * 60)
    print("Phase 3: 崩溃恢复 — 模拟从最后状态 resume_step")
    print("=" * 60)
    # 用一个新 step_id 演示 resume (这里 conv 已有 events, resume 等价于新 step)
    resumed = []
    async for e in resume_step(
        agent_id="demo-agent",
        conv_id="demo-conv",
        input_={"prompt": "继续"},
        state_store=store,
        thinking_fn=thinking_fn,
        acting_fn=acting_fn,
    ):
        resumed.append(e)
    print(f"  resume_step 产出 {len(resumed)} 个事件, 末态: {resumed[-1].state.value}")

    print("\n" + "=" * 60)
    print("Phase 4: SubAgentRuntime — spawn 一个同步子 agent")
    print("=" * 60)
    sub_runtime = SubAgentRuntime(state_store=store, max_depth=5)

    async def sub_thinking(input_):
        yield {"token": "子 agent 思考中"}
        yield {"token": "", "tool_calls": []}

    async def sub_acting(tc: V2ToolCall, ctx: ToolContext) -> V2ToolResult:
        return V2ToolResult.ok(output="子 agent 完成", tool_name=tc.name)

    spec = SubAgentSpawnSpec(
        agent_name="BAIZE-sub",
        task="做一件子任务",
        run_in_background=False,
        parent_step_id="step-demo",
        parent_conv_id="demo-conv",
        parent_agent_id="demo-agent",
        depth=0,
        thinking_fn=sub_thinking,
        acting_fn=sub_acting,
    )
    handle = await sub_runtime.spawn(spec)
    print(f"  子 agent 完成: status={handle.status.value}, result={handle.result}")

    print("\n" + "=" * 60)
    print("✅ V2 全链路验证通过")
    print("=" * 60)
    os.unlink(path)


if __name__ == "__main__":
    asyncio.run(main())
