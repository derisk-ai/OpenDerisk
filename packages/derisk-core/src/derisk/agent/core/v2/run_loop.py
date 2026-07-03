"""V2 多轮循环。

包 run_step，循环直到 LLM 不再 emit tool_calls / terminate / max_steps / 失败 / awaiting。
turn 结束触发 HookManager.turn_complete，conversation 结束触发 conversation_complete。
"""
import dataclasses
from typing import Any, AsyncGenerator, Callable, Optional

from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


_AWAITING_STATES = {
    StepState.AWAITING_USER,
    StepState.AWAITING_TOOL_PERMISSION,
    StepState.AWAITING_SUB_AGENT,
}


@dataclasses.dataclass
class _TurnContext:
    round: int = 0
    interrupted: bool = False
    user_prompt: str = ""
    final_answer: Optional[str] = None
    user_id: Optional[str] = None
    conv_id: str = ""
    agent_id: str = ""
    step_count: int = 0


async def run_loop(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: Callable,
    acting_fn: Optional[Callable] = None,
    *,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[Any] = None,
    subagent_runtime: Optional[Any] = None,
    hook_manager: Optional[Any] = None,
    max_steps: int = 20,
    user_id: Optional[str] = None,
) -> AsyncGenerator[StepEvent, None]:
    """多轮循环。"""
    turn_ctx = _TurnContext(
        round=0,
        user_prompt=input_.get("prompt", ""),
        user_id=user_id,
        conv_id=conv_id,
        agent_id=agent_id,
    )

    step_count = 0
    last_had_tool_calls = True
    turn_complete_fired = False

    while step_count < max_steps and last_had_tool_calls:
        last_had_tool_calls = False
        final_answer_parts = []

        async for step_event in run_step(
            agent_id=agent_id,
            conv_id=conv_id,
            input_=input_,
            state_store=state_store,
            thinking_fn=thinking_fn,
            acting_fn=acting_fn,
            parent_step_id=parent_step_id,
            permission_gate=permission_gate,
            subagent_runtime=subagent_runtime,
        ):
            yield step_event

            # 收集 final_answer（来自 llm_token）
            if step_event.event_type == "llm_token":
                token = step_event.output.get("token", "") if step_event.output else ""
                if token:
                    final_answer_parts.append(token)

            # 检查 tool_calls
            if step_event.event_type == "tool_call":
                last_had_tool_calls = True

            # 检查 awaiting 状态
            if step_event.state in _AWAITING_STATES:
                turn_ctx.interrupted = True
                # turn_complete NOT fired here — an interrupted turn is not "complete".
                # Memory tier1 (write_turn_lightweight) registered on turn_complete
                # skips interrupted turns by design. If future design requires recording
                # interrupted turns, fire turn_complete with interrupted=True here.
                return

            if step_event.state == StepState.FAILED:
                return

            if step_event.state == StepState.DONE and step_event.event_type == "step_done":
                step_count += 1

        # 一个 step 结束
        if not last_had_tool_calls:
            # turn 结束
            turn_ctx.round += 1
            turn_ctx.final_answer = "".join(final_answer_parts) or None
            turn_ctx.step_count = step_count

            if hook_manager is not None:
                from derisk.agent.core.v2.hook_integration import (
                    build_turn_complete_context,
                )
                await hook_manager.trigger(
                    "turn_complete",
                    build_turn_complete_context(
                        round=turn_ctx.round,
                        interrupted=turn_ctx.interrupted,
                        user_prompt=turn_ctx.user_prompt,
                        final_answer=turn_ctx.final_answer,
                        user_id=turn_ctx.user_id,
                        conv_id=turn_ctx.conv_id,
                        agent_id=turn_ctx.agent_id,
                        step_count=turn_ctx.step_count,
                    ),
                )
            turn_complete_fired = True
            break  # turn 结束，退出 loop

    if step_count >= max_steps and not turn_complete_fired:
        # 达到上限，触发 turn_complete（interrupted=True）
        if hook_manager is not None:
            from derisk.agent.core.v2.hook_integration import (
                build_turn_complete_context,
            )
            turn_ctx.interrupted = True
            turn_ctx.round += 1
            await hook_manager.trigger(
                "turn_complete",
                build_turn_complete_context(
                    round=turn_ctx.round,
                    interrupted=True,
                    user_prompt=turn_ctx.user_prompt,
                    final_answer=None,
                    user_id=turn_ctx.user_id,
                    conv_id=turn_ctx.conv_id,
                    agent_id=turn_ctx.agent_id,
                    step_count=step_count,
                ),
            )


async def trigger_conversation_complete(
    hook_manager: Any,
    *,
    conv_id: str,
    agent_id: str,
    user_id: Optional[str],
    total_rounds: int,
) -> None:
    """run_loop 调用方在 conversation 结束时调。"""
    if hook_manager is None:
        return
    from derisk.agent.core.v2.hook_integration import (
        build_conversation_complete_context,
    )
    await hook_manager.trigger(
        "conversation_complete",
        build_conversation_complete_context(
            conv_id=conv_id, agent_id=agent_id, user_id=user_id,
            total_rounds=total_rounds,
        ),
    )
