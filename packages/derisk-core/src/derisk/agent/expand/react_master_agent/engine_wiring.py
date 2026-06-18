"""ContextEngine 与 BAIZE agent 的装配适配器。

把 context_engine 的注入接口（EventEmitter / SummarizeFn）对接到 agent 的
SystemEventManager 与 llm_client。这些适配器依赖 agent 侧基础设施，因此放在
react_master_agent 层而非 context_engine 内部（保持引擎可纯测）。
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SystemEventAdapter:
    """把 context_engine 的字符串事件映射为 SystemEventType 并上报。"""

    def __init__(self, system_event_manager: Optional[Any]):
        self._mgr = system_event_manager

    def emit(self, event_type: str, title: str, description: str = "", metadata=None):
        if self._mgr is None:
            return
        try:
            from derisk.agent.core.memory.gpts.system_event import SystemEventType

            mapping = {
                "COMPRESSION_START": SystemEventType.COMPRESSION_START,
                "COMPRESSION_COMPLETE": SystemEventType.COMPRESSION_COMPLETE,
                "COMPRESSION_LLM_FAILED": SystemEventType.COMPRESSION_LLM_FAILED,
            }
            evt = mapping.get(event_type)
            if evt is None:
                return
            self._mgr.add_event(
                event_type=evt,
                title=title,
                description=description,
                metadata=metadata or {},
            )
        except Exception as e:  # 事件失败不影响主流程
            logger.debug("[SystemEventAdapter] emit failed: %s", e)


def make_summarize_fn(llm_client, temperature: float = 0.3):
    """用 Agent 自身的 llm_client 构造一次性摘要 callable。

    返回 ``async (prompt, max_tokens) -> str``。失败由 ColdSummarizer 兜底（截断）。
    """
    if llm_client is None:
        return None

    async def _summarize(prompt: str, max_tokens: int) -> str:
        try:
            from derisk.core.interface.media import MediaContent
        except Exception:
            MediaContent = None  # type: ignore

        response = await llm_client.async_call(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = getattr(response, "content", None)
        if isinstance(content, list) and MediaContent is not None:
            return MediaContent.last_text(content)
        if hasattr(content, "get_text"):
            return content.get_text()
        if isinstance(content, str):
            return content
        if hasattr(response, "text"):
            return response.text
        return str(content) if content is not None else ""

    return _summarize
