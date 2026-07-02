"""default_thinking_fn 工厂。

流程：
1. Memory 注入（consume_prefetch 或 sync retrieve_relevant_memories）
2. ContextEngine.build_messages
3. 拼最终 LLM messages（system + memory + history + user_prompt）
4. LLM stream（带 retrying_thinking MAX_ATTEMPTS）
5. StreamingContextScrubber 清洗 token
6. yield TokenChunk / ToolCallChunk / UsageChunk
"""
from typing import Any, AsyncGenerator, Callable, Optional

from derisk.agent.core.v2.thinking_chunk import (
    ThinkingChunk, TokenChunk, ToolCallChunk, UsageChunk,
)
from derisk.agent.core.v2.tool_call_types import V2ToolCall
from derisk.agent.core.v2.retrying_thinking import retrying_thinking


STATIC_ROOMS = ["profile", "preference"]


def make_default_thinking_fn(
    *,
    llm_stream_fn: Callable,  # async generator: (messages, model) -> chunks of {"token", "usage", "tool_calls"}
    model_alias: str,
    context_engine: Any,
    memory_bundle: Optional[Any] = None,
    get_session_messages: Callable,  # async or sync: (session_id) -> List[message dict]
    get_work_log: Callable,          # async or sync: (conv_id) -> List[work entry]
    get_context_window: Callable,    # async or sync: (model) -> int
    max_attempts: int = 3,
    model_fallback: Optional[Callable[[str], str]] = None,
    system_prompt: Optional[str] = None,
) -> Callable:
    """构造 ThinkingFn。

    llm_stream_fn: async generator factory，输入 (messages, model)，yield dict chunk：
        {"token": str, "usage": Optional[dict], "tool_calls": Optional[List[dict]]}
    """

    async def thinking_fn(input_: dict) -> AsyncGenerator[ThinkingChunk, None]:
        user_prompt = input_["prompt"]
        conv_id = input_["conv_id"]
        session_id = input_["session_id"]
        sys_prompt = input_.get("system_prompt", system_prompt)

        # 1. Memory 注入（dynamic）
        memory_context = ""
        if memory_bundle is not None:
            pipeline = getattr(memory_bundle, "pipeline", None)
            if pipeline is not None:
                result = await pipeline.consume_prefetch(timeout=0.0)
                if result is None:
                    result = await memory_bundle.manager.retrieve_relevant_memories(
                        query=user_prompt, exclude_rooms=STATIC_ROOMS,
                    )
                memory_context = _build_memory_context_block(result)

        # 2. ContextEngine.build_messages
        messages = await _maybe_await(get_session_messages(session_id))
        work_logs_by_conv = {conv_id: await _maybe_await(get_work_log(conv_id))}
        context_window = await _maybe_await(get_context_window(model_alias))
        build_out = await context_engine.build_messages(
            messages, work_logs_by_conv, conv_id, session_id, context_window,
        )

        # 3. 拼最终 LLM messages
        llm_messages = []
        if sys_prompt:
            llm_messages.append({"role": "system", "content": sys_prompt})
        if memory_context:
            llm_messages.append({"role": "user", "content": memory_context})
        llm_messages.extend(build_out.messages)
        # 最后一条 human 消息覆写为 user_prompt
        llm_messages.append({"role": "user", "content": user_prompt})

        # 4 + 5. LLM stream + retry + scrub
        scrubber = getattr(getattr(memory_bundle, "pipeline", None), "scrub_stream_delta", None) if memory_bundle else None

        async def _stream():
            async for chunk in llm_stream_fn(llm_messages, model_alias):
                yield chunk

        async for chunk in retrying_thinking(
            _stream, max_attempts=max_attempts, model_fallback=model_fallback,
            initial_model=model_alias,
        ):
            token = chunk.get("token")
            usage = chunk.get("usage")
            tool_calls_raw = chunk.get("tool_calls")

            if token:
                if scrubber is not None:
                    token = scrubber(token)
                yield TokenChunk(token=token, usage=usage)
            elif tool_calls_raw:
                tcs = [V2ToolCall(name=tc["tool"], args=tc.get("input", {})) for tc in tool_calls_raw]
                yield ToolCallChunk(tool_calls=tcs)
            elif usage:
                yield UsageChunk(usage=usage)

    return thinking_fn


async def _maybe_await(value):
    import inspect
    if inspect.isawaitable(value):
        return await value
    return value


def _build_memory_context_block(raw: str) -> str:
    """等价 BAIZE memory/read_pipeline.build_memory_context_block。"""
    if not raw:
        return ""
    return f"<memory-context>\n{raw}\n</memory-context>"
