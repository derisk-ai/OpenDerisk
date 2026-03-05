"""
历史修剪器 - 修剪旧的对话历史

定期清理旧的工具输出，保留关键消息
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    """修剪结果"""

    prune_needed: bool
    original_messages: int
    pruned_messages: int
    messages_removed: int
    tokens_saved: int


class HistoryPruner:
    """
    历史修剪器

    定期清理旧的工具输出，保留关键消息
    """

    def __init__(
        self,
        max_tool_outputs: int = 20,
        protect_recent: int = 10,
        protect_system: bool = True,
    ):
        self.max_tool_outputs = max_tool_outputs
        self.protect_recent = protect_recent
        self.protect_system = protect_system
        self._prune_count = 0

        logger.info(
            f"[Layer2:Prune] INIT | max_tool_outputs={max_tool_outputs}, "
            f"protect_recent={protect_recent}, protect_system={protect_system}"
        )

    def needs_prune(self, messages: List[Dict[str, Any]]) -> bool:
        tool_outputs = self._count_tool_outputs(messages)
        needs_it = tool_outputs > self.max_tool_outputs
        logger.debug(
            f"[Layer2:Prune] CHECK | tool_outputs={tool_outputs}/{self.max_tool_outputs} | "
            f"needs_prune={needs_it}"
        )
        return needs_it

    def prune(self, messages: List[Dict[str, Any]]) -> PruneResult:
        if not self.needs_prune(messages):
            logger.info(
                f"[Layer2:Prune] SKIP | messages={len(messages)} | reason=below_threshold"
            )
            return PruneResult(
                prune_needed=False,
                original_messages=len(messages),
                pruned_messages=len(messages),
                messages_removed=0,
                tokens_saved=0,
            )

        logger.info(f"[Layer2:Prune] START | original_messages={len(messages)}")

        original_count = len(messages)
        original_tokens = self._estimate_tokens(messages)

        pruned_messages = self._do_prune(messages)

        pruned_tokens = self._estimate_tokens(pruned_messages)
        tokens_saved = original_tokens - pruned_tokens
        messages_removed = original_count - len(pruned_messages)

        self._prune_count += 1

        compression_ratio = (
            pruned_tokens / original_tokens if original_tokens > 0 else 0
        )
        logger.info(
            f"[Layer2:Prune] COMPLETE | original={original_count}msgs/{original_tokens}tokens -> "
            f"pruned={len(pruned_messages)}msgs/{pruned_tokens}tokens | "
            f"removed={messages_removed}msgs | saved={tokens_saved}tokens | "
            f"compression_ratio={compression_ratio:.1%}"
        )

        return PruneResult(
            prune_needed=True,
            original_messages=original_count,
            pruned_messages=len(pruned_messages),
            messages_removed=messages_removed,
            tokens_saved=tokens_saved,
        )

    def _do_prune(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pruned = []
        tool_output_indices = []
        protected_count = 0

        for i, msg in enumerate(messages):
            if self._is_protected_message(msg, i, len(messages)):
                pruned.append(msg)
                protected_count += 1
            elif self._is_tool_output(msg):
                tool_output_indices.append(i)
            else:
                pruned.append(msg)

        logger.debug(
            f"[Layer2:Prune] ANALYZE | total={len(messages)} | "
            f"protected={protected_count} | tool_outputs={len(tool_output_indices)}"
        )

        tool_outputs_to_keep = self._select_tool_outputs_to_keep(
            messages, tool_output_indices
        )

        for idx in tool_outputs_to_keep:
            pruned.append(messages[idx])

        pruned.sort(key=lambda m: messages.index(m) if m in messages else 0)

        logger.debug(
            f"[Layer2:Prune] SELECT | tool_outputs_to_keep={len(tool_outputs_to_keep)}/{len(tool_output_indices)}"
        )

        return pruned

    def _is_protected_message(
        self,
        msg: Dict[str, Any],
        index: int,
        total: int,
    ) -> bool:
        if self.protect_system and msg.get("role") == "system":
            return True

        if index >= total - self.protect_recent:
            return True

        if msg.get("role") == "user":
            return True

        return False

    def _is_tool_output(self, msg: Dict[str, Any]) -> bool:
        content = msg.get("content", "")
        return isinstance(content, str) and (
            "工具" in content or "tool" in content.lower() or "执行结果" in content
        )

    def _select_tool_outputs_to_keep(
        self,
        messages: List[Dict[str, Any]],
        tool_output_indices: List[int],
    ) -> List[int]:
        if len(tool_output_indices) <= self.max_tool_outputs:
            return tool_output_indices

        step = len(tool_output_indices) / self.max_tool_outputs
        selected = []

        for i in range(self.max_tool_outputs):
            idx = int(i * step)
            if idx < len(tool_output_indices):
                selected.append(tool_output_indices[idx])

        return selected

    def _count_tool_outputs(self, messages: List[Dict[str, Any]]) -> int:
        count = 0
        for msg in messages:
            if self._is_tool_output(msg):
                count += 1
        return count

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(str(content)) // 4
        return total

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "prune_count": self._prune_count,
            "max_tool_outputs": self.max_tool_outputs,
            "protect_recent": self.protect_recent,
        }
