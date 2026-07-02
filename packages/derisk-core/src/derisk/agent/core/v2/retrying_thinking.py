"""LLM stream 重试装饰器。

从 BAIZE react_master_agent.py:1908-2044 的 llm_thinking MAX_ATTEMPTS 逻辑抽出。
包装一个 async generator（LLM stream），失败时重试，可带模型降级。
"""
from typing import AsyncGenerator, Callable, Optional, Any


async def retrying_thinking(
    stream_fn: Callable[[], AsyncGenerator],
    max_attempts: int = 3,
    model_fallback: Optional[Callable[[str], str]] = None,
    initial_model: Optional[str] = None,
) -> AsyncGenerator:
    """重试 LLM stream。

    Args:
        stream_fn: 返回 async generator 的 callable（每次调用产生新 stream）
        max_attempts: 最大尝试次数
        model_fallback: 失败时调用的模型降级函数，传入 last_model 返回 new_model
        initial_model: 初始 model（用于第一次调用 + fallback 链）

    Yields: stream_fn 产生的 chunk
    """
    last_model = initial_model
    for attempt in range(max_attempts):
        try:
            async for chunk in stream_fn():
                yield chunk
            return  # 成功完成
        except Exception:
            if attempt + 1 >= max_attempts:
                raise
            if model_fallback and last_model is not None:
                last_model = model_fallback(last_model)
            # 否则用原 model 重试
