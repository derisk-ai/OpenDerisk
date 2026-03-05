"""
上下文压缩器 - 压缩对话上下文

当上下文超过窗口限制时，自动生成摘要
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompactionResult:
    compact_needed: bool
    original_messages: int
    compacted_messages: int
    tokens_saved: int
    summary: Optional[str] = None
    new_messages: Optional[List[Dict[str, Any]]] = None


class ContextCompactor:
    """
    上下文压缩器

    当上下文超过窗口限制时，自动生成摘要以节省Token
    """

    def __init__(
        self,
        max_tokens: int = 128000,
        threshold_ratio: float = 0.8,
        enable_summary: bool = True,
    ):
        self.max_tokens = max_tokens
        self.threshold_ratio = threshold_ratio
        self.enable_summary = enable_summary
        self._compaction_count = 0

        logger.info(
            f"[Layer3:Compaction] INIT | max_tokens={max_tokens}, "
            f"threshold_ratio={threshold_ratio}, enable_summary={enable_summary}"
        )

    def needs_compaction(self, messages: List[Dict[str, Any]]) -> bool:
        total_tokens = self._estimate_tokens(messages)
        threshold = int(self.max_tokens * self.threshold_ratio)
        needs_it = total_tokens > threshold

        logger.debug(
            f"[Layer3:Compaction] CHECK | tokens={total_tokens}/{self.max_tokens} | "
            f"threshold={threshold} | needs_compaction={needs_it}"
        )

        return needs_it

    def compact(
        self,
        messages: List[Dict[str, Any]],
        llm_adapter: Optional[Any] = None,
    ) -> CompactionResult:
        if not self.needs_compaction(messages):
            logger.info(
                f"[Layer3:Compaction] SKIP | messages={len(messages)} | "
                f"reason=below_threshold"
            )
            return CompactionResult(
                compact_needed=False,
                original_messages=len(messages),
                compacted_messages=len(messages),
                tokens_saved=0,
            )

        logger.info(f"[Layer3:Compaction] START | original_messages={len(messages)}")

        original_count = len(messages)
        original_tokens = self._estimate_tokens(messages)

        if self.enable_summary and llm_adapter:
            logger.info(f"[Layer3:Compaction] GENERATE_SUMMARY | using_llm=True")
            summary = self._generate_summary(messages, llm_adapter)
            new_messages = self._build_compacted_messages(messages, summary)
        else:
            logger.info(f"[Layer3:Compaction] SIMPLE_COMPACT | using_llm=False")
            new_messages = self._simple_compact(messages)
            summary = None

        compacted_tokens = self._estimate_tokens(new_messages)
        tokens_saved = original_tokens - compacted_tokens

        self._compaction_count += 1

        compression_ratio = (
            compacted_tokens / original_tokens if original_tokens > 0 else 0
        )
        logger.info(
            f"[Layer3:Compaction] COMPLETE | original={original_count}msgs/{original_tokens}tokens -> "
            f"compacted={len(new_messages)}msgs/{compacted_tokens}tokens | "
            f"saved={tokens_saved}tokens | compression_ratio={compression_ratio:.1%}"
        )

        return CompactionResult(
            compact_needed=True,
            original_messages=original_count,
            compacted_messages=len(new_messages),
            tokens_saved=tokens_saved,
            summary=summary,
            new_messages=new_messages,
        )

    def _generate_summary(
        self,
        messages: List[Dict[str, Any]],
        llm_adapter: Any,
    ) -> str:
        conversation_text = self._format_messages(messages)

        prompt = f"""请为以下对话生成简洁的摘要，保留关键信息和决策：

{conversation_text}

摘要应包含：
1. 主要任务和目标
2. 已完成的关键步骤
3. 重要的决策和发现
4. 当前状态和下一步计划

摘要："""

        try:
            if hasattr(llm_adapter, "generate"):
                response = llm_adapter.generate(prompt)
                if hasattr(response, "content"):
                    logger.info(
                        f"[Layer3:Compaction] SUMMARY_GENERATED | length={len(response.content)}"
                    )
                    return response.content
                return str(response)
            else:
                return self._simple_summary(messages)
        except Exception as e:
            logger.error(f"[Layer3:Compaction] SUMMARY_ERROR | error={e}")
            return self._simple_summary(messages)

    def _simple_summary(self, messages: List[Dict[str, Any]]) -> str:
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        summary = f"对话摘要：共 {len(user_messages)} 个用户消息，{len(assistant_messages)} 个助手回复。"

        if user_messages:
            first_user_msg = user_messages[0].get("content", "")[:100]
            summary += f"\n初始请求: {first_user_msg}..."

        logger.debug(
            f"[Layer3:Compaction] SIMPLE_SUMMARY | user_msgs={len(user_messages)}, assistant_msgs={len(assistant_messages)}"
        )

        return summary

    def _build_compacted_messages(
        self,
        messages: List[Dict[str, Any]],
        summary: str,
    ) -> List[Dict[str, Any]]:
        compacted = []

        if messages and messages[0].get("role") == "system":
            compacted.append(messages[0])

        compacted.append({"role": "system", "content": f"[上下文摘要]\n{summary}"})

        recent_messages = messages[-6:] if len(messages) > 6 else messages
        compacted.extend(recent_messages)

        logger.debug(
            f"[Layer3:Compaction] BUILD_COMPACTED | kept_recent={len(recent_messages)}"
        )

        return compacted

    def _simple_compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if messages and messages[0].get("role") == "system":
            result = [messages[0]] + messages[-10:]
        else:
            result = messages[-10:]

        logger.debug(f"[Layer3:Compaction] SIMPLE_COMPACT | kept={len(result)}")

        return result

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(content) // 4
        return total

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"[{role.upper()}] {content}")
        return "\n\n".join(lines)

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "compaction_count": self._compaction_count,
            "max_tokens": self.max_tokens,
            "threshold_ratio": self.threshold_ratio,
        }
