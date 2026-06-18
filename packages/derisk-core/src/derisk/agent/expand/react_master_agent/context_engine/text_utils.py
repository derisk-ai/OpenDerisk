"""共享文本工具 —— 纯函数，无 agent / 存储依赖。

把历史上分散在 ``history_message_builder`` / ``react_master_agent`` 的文本抽取、
多模态构建、token 估算逻辑抽出为单一来源，供整个 context_engine 与 work_log 复用。

token 估算：约 4 个字符 = 1 个 token。**全引擎唯一来源**，所有组件必须使用
同一个 ``DEFAULT_CHARS_PER_TOKEN``，否则分层边界会错乱。
"""

import json
from typing import Any, Dict, List, Union

try:  # MediaContent 为可选依赖（多模态）
    from derisk.core.interface.media import MediaContent
except Exception:  # pragma: no cover - 极少数环境无 media 模块
    MediaContent = None  # type: ignore


# 统一 token 估算常量：约 4 个字符为 1 个 token。
DEFAULT_CHARS_PER_TOKEN = 4

# 老格式多模态 content_types -> OpenAI part 类型映射
_MEDIA_TYPE_MAPPING = {
    "image_url": "image_url",
    "file_url": "file_url",
    "audio_url": "audio_url",
    "video_url": "video_url",
}


def extract_text_content(content: Any) -> str:
    """将各种格式的 content 统一转为 str。

    处理 str / list(MediaContent|dict|str) / dict 等格式。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                obj = item.get("object", {})
                text_parts.append(obj.get("data", "") if isinstance(obj, dict) else "")
            elif hasattr(item, "object"):
                obj = getattr(item, "object", None)
                text_parts.append(getattr(obj, "data", "") if obj else "")
        return "\n".join(filter(None, text_parts))
    return str(content)


def build_user_content(msg: Any) -> Union[str, List[Dict[str, Any]]]:
    """从 GptsMessage 构建用户消息 content，支持多模态。

    新格式：content 直接是 List[MediaContent]，转为 OpenAI 多模态格式。
    老格式（兼容）：content 是纯文本，从 content_types + context 重建多模态。

    返回 OpenAI 多模态格式（list）或纯文本字符串。
    """
    content = getattr(msg, "content", "")

    # 新格式：content 已经是 List[MediaContent]
    if MediaContent is not None and isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, MediaContent):
            return MediaContent.to_chat_completion_message(content)

    # 纯文本或老格式
    text = extract_text_content(content)

    content_types = getattr(msg, "content_types", None) or []
    context = getattr(msg, "context", None) or {}

    multimodal_parts: List[Dict[str, Any]] = []
    if isinstance(context, dict):
        for ctx_key, part_type in _MEDIA_TYPE_MAPPING.items():
            if ctx_key in content_types and ctx_key in context:
                urls = context[ctx_key]
                if isinstance(urls, str):
                    urls = [urls]
                for url in urls:
                    if url:
                        multimodal_parts.append(
                            {"type": part_type, part_type: {"url": url}}
                        )

    if not multimodal_parts:
        return text

    parts: List[Dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    parts.extend(multimodal_parts)
    return parts if parts else text


def estimate_tokens_text(
    text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN
) -> int:
    """估算一段文本的 token 数。最小返回 1（与历史实现保持一致）。"""
    if not text:
        return 1
    return max(1, len(text) // chars_per_token)


def estimate_message_tokens(
    msg: Dict[str, Any], chars_per_token: int = DEFAULT_CHARS_PER_TOKEN
) -> int:
    """估算一条 OpenAI 风格 message dict 的 token 数（含 tool_calls）。"""
    content = msg.get("content", "")
    if isinstance(content, str):
        chars = len(content)
    else:
        chars = len(str(content))

    tool_calls = msg.get("tool_calls")
    if tool_calls:
        try:
            chars += len(json.dumps(tool_calls, ensure_ascii=False, default=str))
        except Exception:
            chars += len(str(tool_calls))

    return max(1, chars // chars_per_token)


def estimate_messages_tokens(
    messages: List[Dict[str, Any]], chars_per_token: int = DEFAULT_CHARS_PER_TOKEN
) -> int:
    """估算一组 message dict 的总 token 数。"""
    return sum(estimate_message_tokens(m, chars_per_token) for m in messages)
