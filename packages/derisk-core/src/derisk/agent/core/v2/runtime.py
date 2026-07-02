# packages/derisk-core/src/derisk/agent/core/v2/runtime.py
"""run_step()——V2 Runtime 入口.

P0: INIT → THINKING → ACTING（可选）→ OBSERVING → DONE
P1: + PermissionGate 在 ACTING 前拦截，AWAITING_TOOL_PERMISSION 状态
崩溃恢复：每个 yield 前持久化，resume_step 从 StateStore 重放 + 重做未完成 step。
"""
from __future__ import annotations
import uuid
import time
from typing import AsyncGenerator, Callable, Awaitable, Optional, Dict, TYPE_CHECKING
from derisk.agent.core.v2.step_state import (
    StepState, validate_transition, IllegalTransitionError,
)
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.event_stream import EventStream

if TYPE_CHECKING:
    from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime


ThinkingFn = Callable[[dict], AsyncGenerator[dict, None]]
ActingFn = Callable[[dict], Awaitable[dict]]

_AWAITING_STATES = {
    StepState.AWAITING_USER,
    StepState.AWAITING_TOOL_PERMISSION,
    StepState.AWAITING_SUB_AGENT,
}

# Per-process tracker of the last state per step_id. Used by validate_transition.
# In a multi-process setup each process has its own tracker and loads initial
# state from StateStore on resume.
_step_state_tracker: Dict[str, StepState] = {}


def _validate_and_track_transition(step_id: str, prev: Optional[StepState], new: StepState) -> None:
    """Validate prev -> new transition; raise on invalid; track new state.

    If prev is None, we trust the caller (initial state or resume from store).
    Consecutive events in the same state are allowed (e.g. multiple THINKING tokens).
    """
    if prev is not None and prev is not new:
        if not validate_transition(prev, new):
            raise IllegalTransitionError(
                f"Invalid transition for step {step_id}: {prev.value} -> {new.value}"
            )
    _step_state_tracker[step_id] = new


def _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start):
    """创建 emit 函数：构造 StepEvent、校验状态转换、持久化、返回。"""
    seq = {"n": seq_start}

    async def emit(state, event_type, input_data=None, output_data=None):
        prev = _step_state_tracker.get(step_id)
        _validate_and_track_transition(step_id, prev, state)
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


async def _run_acting_phase(
    emit, gate, tool_calls, acting_fn, state_store=None,
    subagent_runtime=None, parent_step_id=None, parent_conv_id=None,
    parent_agent_id=None, step_id=None, conv_id=None,
):
    """ACTING + OBSERVING 阶段。每个 tool_call 前 PermissionGate.check()。"""
    for tc in tool_calls:
        # Sub-agent interception (spec §8)
        if tc.get("tool") == "spawn_subagent" and subagent_runtime is not None:
            from derisk.agent.core.v2.subagent_runtime import SubAgentSpawnSpec
            spec_input = tc.get("input", {})
            # Strip test-only injected callables from persisted event input
            display_input = {k: v for k, v in spec_input.items() if not k.startswith("_")}
            yield await emit(
                StepState.AWAITING_SUB_AGENT, "subagent_spawn",
                input_data={**tc, "input": display_input},
            )
            spec = SubAgentSpawnSpec(
                agent_name=spec_input.get("agent_name", "unknown"),
                task=spec_input.get("task", ""),
                run_in_background=spec_input.get("run_in_background", False),
                context=spec_input.get("context", {}),
                parent_step_id=parent_step_id or "step-unknown",
                parent_conv_id=parent_conv_id or "conv-unknown",
                parent_agent_id=parent_agent_id or "agent-unknown",
                depth=0,  # P2 simplification: depth tracking via context in P3
                thinking_fn=spec_input.get("_sub_thinking_fn"),
                acting_fn=spec_input.get("_sub_acting_fn"),
                interaction_gateway=None,
            )
            handle = await subagent_runtime.spawn(spec)
            yield await emit(
                StepState.OBSERVING, "tool_result",
                output_data=handle.to_payload(),
            )
            continue

        # PermissionGate path (existing)
        if gate is not None:
            async for perm_event in gate.check(tc, emit=emit):
                yield perm_event
            result = gate.last_result
            if result.decision == PermissionDecision.DENY:
                yield await emit(
                    StepState.ACTING, "tool_call",
                    input_data=tc, output_data={"denied": True, "reason": result.reason},
                )
                continue
            # ALLOW path: delete the interaction checkpoint (if a request_id was set)
            if result.request_id and state_store is not None:
                await state_store.delete_interaction_checkpoint(result.request_id)
        yield await emit(StepState.ACTING, "tool_call", input_data=tc)
        if acting_fn is not None:
            result_dict = await acting_fn(tc)
            # P2 follow-up: legacy ActionOutput.ask_user compat (§9.4)
            if isinstance(result_dict, dict) and "ask_user" in result_dict:
                from derisk.agent.core.v2.ask_user_adapter import AskUserAdapter
                adapter = AskUserAdapter(state_store=state_store) if state_store else None
                if adapter is not None:
                    ask_event = await adapter.convert(
                        result_dict["ask_user"],
                        step_id=step_id or parent_step_id or "step-unknown",
                        conv_id=conv_id or parent_conv_id or "conv-unknown",
                    )
                    # Re-emit via runtime's emit so seq is correct
                    _step_state_tracker.pop(step_id or parent_step_id or "step-unknown", None)
                    yield await emit(
                        StepState.AWAITING_USER, "interaction_request",
                        input_data=ask_event.input,
                    )
                    return  # step suspended
            yield await emit(StepState.OBSERVING, "tool_result", output_data=result_dict)


# Import here to avoid circular import at module load
from derisk.agent.core.v2.permission_gate import PermissionGate, PermissionDecision  # noqa: E402


async def run_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
    subagent_runtime: Optional["SubAgentRuntime"] = None,
) -> AsyncGenerator[StepEvent, None]:
    """跑一个 step，yield 所有 StepEvent。每个事件持久化后再 yield。"""
    stream = EventStream(state_store)
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    if permission_gate is not None:
        permission_gate._step_id = step_id  # bind gate to this step
    emit = _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start=0)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    if result_box["tool_calls"]:
        async for e in _run_acting_phase(
            emit, permission_gate, result_box["tool_calls"], acting_fn,
            state_store=state_store,
            subagent_runtime=subagent_runtime,
            parent_step_id=step_id, parent_conv_id=conv_id, parent_agent_id=agent_id,
            step_id=step_id, conv_id=conv_id,
        ):
            yield e
        # P2 follow-up: if acting phase suspended for user input, don't emit DONE
        if _step_state_tracker.get(step_id) in _AWAITING_STATES:
            return

    yield await emit(StepState.DONE, "step_done")


async def resume_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
    subagent_runtime: Optional["SubAgentRuntime"] = None,
) -> AsyncGenerator[StepEvent, None]:
    """从崩溃点续接。

    - 无 step_id：等价 run_step
    - 有 step_id 且最后状态是 AWAITING_*：恢复到等待状态（不重跑 thinking）
    - 有 step_id 且最后状态是 THINKING/ACTING/OBSERVING/INIT：重做该 step
    """
    if not step_id:
        async for e in run_step(
            agent_id, conv_id, input_, state_store,
            thinking_fn, acting_fn, permission_gate=permission_gate,
            subagent_runtime=subagent_runtime,
        ):
            yield e
        return

    # Inspect last state for this step
    state_result = await state_store.get_step_state(step_id)
    last_state = state_result[0] if state_result else None

    stream = EventStream(state_store)
    if permission_gate is not None:
        permission_gate._step_id = step_id
    existing = await state_store.get_events(conv_id)
    seq_start = existing[-1].seq + 1 if existing else 0
    emit = _make_emit(stream, step_id, conv_id, agent_id, None, seq_start)

    # P0 Important #3: resume_awaiting path
    if last_state in _AWAITING_STATES:
        # Restore the awaiting state without re-running thinking
        # _validate_and_track_transition needs prev=None to skip the check
        # (the step's persisted state is already this; we're re-emitting for SSE)
        _step_state_tracker.pop(step_id, None)
        yield await emit(last_state, "interaction_request",
                         input_data={"reason": f"resumed from {last_state.value}"})
        return

    # redo_step path: re-run thinking + acting (P0 Important #1: acting_fn now included)
    _step_state_tracker.pop(step_id, None)  # reset tracker so INIT is valid
    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    if result_box["tool_calls"]:
        async for e in _run_acting_phase(
            emit, permission_gate, result_box["tool_calls"], acting_fn,
            state_store=state_store,
            subagent_runtime=subagent_runtime,
            parent_step_id=step_id, parent_conv_id=conv_id, parent_agent_id=agent_id,
            step_id=step_id, conv_id=conv_id,
        ):
            yield e
        # P2 follow-up: if acting phase suspended for user input, don't emit DONE
        if _step_state_tracker.get(step_id) in _AWAITING_STATES:
            return

    yield await emit(StepState.DONE, "step_done")
