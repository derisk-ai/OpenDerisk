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
        """
        初始化修剪器
        
        Args:
            max_tool_outputs: 最大工具输出数量
            protect_recent: 保护最近N条消息
            protect_system: 是否保护系统消息
        """
        self.max_tool_outputs = max_tool_outputs
        self.protect_recent = protect_recent
        self.protect_system = protect_system
        self._prune_count = 0
    
    def needs_prune(self, messages: List[Dict[str, Any]]) -> bool:
        """检查是否需要修剪"""
        tool_outputs = self._count_tool_outputs(messages)
        return tool_outputs > self.max_tool_outputs
    
    def prune(self, messages: List[Dict[str, Any]]) -> PruneResult:
        """
        修剪历史消息
        
        Args:
            messages: 消息列表
            
        Returns:
            PruneResult: 修剪结果
        """
        if not self.needs_prune(messages):
            return PruneResult(
                prune_needed=False,
                original_messages=len(messages),
                pruned_messages=len(messages),
                messages_removed=0,
                tokens_saved=0,
            )
        
        original_count = len(messages)
        original_tokens = self._estimate_tokens(messages)
        
        pruned_messages = self._do_prune(messages)
        
        pruned_tokens = self._estimate_tokens(pruned_messages)
        tokens_saved = original_tokens - pruned_tokens
        messages_removed = original_count - len(pruned_messages)
        
        self._prune_count += 1
        
        logger.info(
            f"[Pruner] 修剪历史: {original_count}条 -> {len(pruned_messages)}条, "
            f"移除 {messages_removed}条, 节省 {tokens_saved} tokens"
        )
        
        return PruneResult(
            prune_needed=True,
            original_messages=original_count,
            pruned_messages=len(pruned_messages),
            messages_removed=messages_removed,
            tokens_saved=tokens_saved,
        )
    
    def _do_prune(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行修剪"""
        pruned = []
        tool_output_indices = []
        
        for i, msg in enumerate(messages):
            if self._is_protected_message(msg, i, len(messages)):
                pruned.append(msg)
            elif self._is_tool_output(msg):
                tool_output_indices.append(i)
            else:
                pruned.append(msg)
        
        tool_outputs_to_keep = self._select_tool_outputs_to_keep(
            messages, tool_output_indices
        )
        
        for idx in tool_outputs_to_keep:
            pruned.append(messages[idx])
        
        pruned.sort(key=lambda m: messages.index(m) if m in messages else 0)
        
        return pruned
    
    def _is_protected_message(
        self,
        msg: Dict[str, Any],
        index: int,
        total: int,
    ) -> bool:
        """检查是否是受保护的消息"""
        if self.protect_system and msg.get("role") == "system":
            return True
        
        if index >= total - self.protect_recent:
            return True
        
        if msg.get("role") == "user":
            return True
        
        return False
    
    def _is_tool_output(self, msg: Dict[str, Any]) -> bool:
        """检查是否是工具输出"""
        content = msg.get("content", "")
        return isinstance(content, str) and (
            "工具" in content or "tool" in content.lower() or "执行结果" in content
        )
    
    def _select_tool_outputs_to_keep(
        self,
        messages: List[Dict[str, Any]],
        tool_output_indices: List[int],
    ) -> List[int]:
        """选择要保留的工具输出"""
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
        """统计工具输出数量"""
        count = 0
        for msg in messages:
            if self._is_tool_output(msg):
                count += 1
        return count
    
    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算Token数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(str(content)) // 4
        return total
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "prune_count": self._prune_count,
            "max_tool_outputs": self.max_tool_outputs,
            "protect_recent": self.protect_recent,
        }