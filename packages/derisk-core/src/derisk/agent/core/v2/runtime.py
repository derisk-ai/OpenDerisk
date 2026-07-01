# packages/derisk-core/src/derisk/agent/core/v2/runtime.py
"""run_step()——V2 Runtime 入口。

P0 实现：INIT → THINKING（yield tokens）→ ACTING（可选）→ OBSERVING → DONE
thinking_fn / acting_fn 可注入，P0 测试用桩，P1+ 接真实 LLM 和工具。

崩溃恢复：每个 yield 前持久化，进程崩溃后 resume_step 从 StateStore
重放已完成事件，未完成的 step 重新执行（LLM 调用重新发，但已完成
的 step 从事件流读结果不重做）。
"""
from __future__ import annotations
import uuid
import time
from typing import AsyncGenerator, Callable, Awaitable, Optional
from derisk.agent.core.v2.step_state import StepState
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.event_stream import EventStream


ThinkingFn = Callable[[dict], AsyncGenerator[dict, None]]
ActingFn = Callable[[dict], Awaitable[dict]]


def _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start):
    """创建 emit 函数：构造 StepEvent、持久化、返回。seq 单调递增。"""
    seq = {"n": seq_start}

    async def emit(state, event_type, input_data=None, output_data=None):
        event = StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id=step_id,
            conv_id=conv_id,
            agent_id=agent_id,
            parent_step_id=parent_step_id,
            state=state,
            event_type=event_type,
            input=input_data or {},
            output=output_data or {},
            seq=seq["n"],
            timestamp=time.time(),
        )
        seq["n"] += 1
        return await stream.emit(event)

    return emit


async def _run_thinking_phase(emit, thinking_fn, input_, result_box):
    """INIT + THINKING 阶段。yield 事件，把 tool_calls/await_user 写入 result_box。"""
    yield await emit(StepState.INIT, "step_init", input_data=input_)
    result_box["tool_calls"] = []
    result_box["await_user"] = False
    async for chunk in thinking_fn(input_):
        if chunk.get("await_user"):
            result_box["await_user"] = True
            yield await emit(
                StepState.AWAITING_USER, "interaction_request",
                input_data={"reason": "thinking_fn requested user input"},
            )
            return
        if chunk.get("tool_calls"):
            result_box["tool_calls"].extend(chunk["tool_calls"])
        yield await emit(
            StepState.THINKING, "llm_token",
            output_data={"token": chunk.get("token", "")},
        )


async def run_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    parent_step_id: Optional[str] = None,
) -> AsyncGenerator[StepEvent, None]:
    """跑一个 step，yield 所有 StepEvent。每个事件持久化后再 yield。"""
    stream = EventStream(state_store)
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    emit = _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start=0)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    # ACTING + OBSERVING（P0 无 permission gate，P1 加）
    if result_box["tool_calls"] and acting_fn:
        for tc in result_box["tool_calls"]:
            yield await emit(StepState.ACTING, "tool_call", input_data=tc)
            result = await acting_fn(tc)
            yield await emit(StepState.OBSERVING, "tool_result", output_data=result)

    yield await emit(StepState.DONE, "step_done")


async def resume_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    step_id: Optional[str] = None,
) -> AsyncGenerator[StepEvent, None]:
    """从崩溃点续接。

    若指定 step_id 且该 step 未完成，重做该 step（重新跑 thinking_fn）。
    已完成的 step 从事件流读结果不重做（P0 简化：直接重做指定 step）。
    """
    if not step_id:
        async for e in run_step(agent_id, conv_id, input_, state_store, thinking_fn, acting_fn):
            yield e
        return

    stream = EventStream(state_store)
    existing = await state_store.get_events(conv_id)
    seq_start = existing[-1].seq + 1 if existing else 0
    emit = _make_emit(stream, step_id, conv_id, agent_id, None, seq_start)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    yield await emit(StepState.DONE, "step_done")
