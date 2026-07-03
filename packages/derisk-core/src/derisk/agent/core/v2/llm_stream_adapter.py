"""derisk_llm stream 适配器。

把 derisk_llm 的 OpenAI 格式 delta stream 转成 default_thinking_fn 期望的 chunk：
  {"token": str} / {"tool_calls": [{"tool": str, "input": dict}]} / {"usage": dict}
"""
import json
from typing import Any, AsyncGenerator, Callable


def make_derisk_llm_stream(derisk_stream_fn: Callable) -> Callable:
    """包装 derisk_llm stream。

    Args:
        derisk_stream_fn: async generator factory，输入 (model, messages)，
            yield OpenAI 格式 chunk:
            {"choices": [{"delta": {"content": ...}, "finish_reason": ...,
                          "message": {"tool_calls": [...]}}],
             "usage": {...}}

    Returns:
        async generator factory，输入 (messages, model)，
        yield {"token": str} / {"tool_calls": [...]} / {"usage": dict}
    """

    async def adapted_stream(messages, model) -> AsyncGenerator[dict, None]:
        async for raw in derisk_stream_fn(model, messages):
            choices = raw.get("choices", [])
            usage = raw.get("usage")

            for choice in choices:
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                content = delta.get("content")
                if content:
                    yield {"token": content, "usage": usage}

                if finish_reason == "tool_calls":
                    message = choice.get("message", {})
                    raw_tool_calls = message.get("tool_calls", [])
                    tcs = []
                    for tc in raw_tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name")
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except json.JSONDecodeError:
                            args = {"_raw": args_str}
                        if name:
                            tcs.append({"tool": name, "input": args})
                    if tcs:
                        yield {"tool_calls": tcs, "usage": usage}

                if usage and not content and finish_reason != "tool_calls":
                    yield {"usage": usage}

    return adapted_stream


def make_derisk_llm_stream_fn(ai_wrapper, model_alias: str):
    """构造 default_thinking_fn 需要的 llm_stream_fn（dict chunk 格式）。

    包装 AIWrapper.create(stream_out=True) → yield {"token", "usage", "tool_calls"}.
    BAIZE 路径同样通过 AIWrapper 解析 LLM provider（self.llm_provider 在生产为 None）。
    """
    async def _stream(messages, model):
        async for model_output in ai_wrapper.create(
            messages=messages,
            llm_model=model or model_alias,
            stream_out=True,
        ):
            chunk = {}
            text = getattr(model_output, "text", None) or ""
            if text:
                chunk["token"] = text
            if getattr(model_output, "usage", None):
                chunk["usage"] = model_output.usage
            tool_calls = getattr(model_output, "tool_calls", None)
            if tool_calls:
                if isinstance(tool_calls, str):
                    try:
                        tool_calls = json.loads(tool_calls)
                    except Exception:
                        tool_calls = None
                if isinstance(tool_calls, list):
                    normalized = []
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function") or {}
                            normalized.append({
                                "tool": fn.get("name") or tc.get("name") or tc.get("tool"),
                                "input": _parse_args(fn.get("arguments") or tc.get("input") or tc.get("args") or {}),
                            })
                        else:
                            normalized.append({"tool": str(tc), "input": {}})
                    chunk["tool_calls"] = normalized
            if chunk:
                yield chunk

    return _stream


def _parse_args(args):
    """tool_call arguments may be JSON string or dict."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except Exception:
            return {"_raw": args}
    return args or {}
