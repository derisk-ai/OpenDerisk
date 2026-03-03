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
    """压缩结果"""
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
        """
        初始化压缩器
        
        Args:
            max_tokens: 最大Token数
            threshold_ratio: 触发压缩的阈值比例
            enable_summary: 是否生成摘要
        """
        self.max_tokens = max_tokens
        self.threshold_ratio = threshold_ratio
        self.enable_summary = enable_summary
        self._compaction_count = 0
    
    def needs_compaction(self, messages: List[Dict[str, Any]]) -> bool:
        """检查是否需要压缩"""
        total_tokens = self._estimate_tokens(messages)
        threshold = int(self.max_tokens * self.threshold_ratio)
        
        return total_tokens > threshold
    
    def compact(
        self,
        messages: List[Dict[str, Any]],
        llm_adapter: Optional[Any] = None,
    ) -> CompactionResult:
        """
        压缩上下文
        
        Args:
            messages: 消息列表
            llm_adapter: LLM适配器（用于生成摘要）
            
        Returns:
            CompactionResult: 压缩结果
        """
        if not self.needs_compaction(messages):
            return CompactionResult(
                compact_needed=False,
                original_messages=len(messages),
                compacted_messages=len(messages),
                tokens_saved=0,
            )
        
        original_count = len(messages)
        original_tokens = self._estimate_tokens(messages)
        
        if self.enable_summary and llm_adapter:
            summary = self._generate_summary(messages, llm_adapter)
            new_messages = self._build_compacted_messages(messages, summary)
        else:
            new_messages = self._simple_compact(messages)
            summary = None
        
        compacted_tokens = self._estimate_tokens(new_messages)
        tokens_saved = original_tokens - compacted_tokens
        
        self._compaction_count += 1
        
        logger.info(
            f"[Compactor] 压缩上下文: {original_count}条 -> {len(new_messages)}条, "
            f"节省 {tokens_saved} tokens"
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
        """生成对话摘要"""
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
            if hasattr(llm_adapter, 'generate'):
                response = llm_adapter.generate(prompt)
                if hasattr(response, 'content'):
                    return response.content
                return str(response)
            else:
                return self._simple_summary(messages)
        except Exception as e:
            logger.error(f"[Compactor] 生成摘要失败: {e}")
            return self._simple_summary(messages)
    
    def _simple_summary(self, messages: List[Dict[str, Any]]) -> str:
        """简单摘要"""
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]
        
        summary = f"对话摘要：共 {len(user_messages)} 个用户消息，{len(assistant_messages)} 个助手回复。"
        
        if user_messages:
            first_user_msg = user_messages[0].get("content", "")[:100]
            summary += f"\n初始请求: {first_user_msg}..."
        
        return summary
    
    def _build_compacted_messages(
        self,
        messages: List[Dict[str, Any]],
        summary: str,
    ) -> List[Dict[str, Any]]:
        """构建压缩后的消息列表"""
        compacted = []
        
        if messages and messages[0].get("role") == "system":
            compacted.append(messages[0])
        
        compacted.append({
            "role": "system",
            "content": f"[上下文摘要]\n{summary}"
        })
        
        recent_messages = messages[-6:] if len(messages) > 6 else messages
        compacted.extend(recent_messages)
        
        return compacted
    
    def _simple_compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """简单压缩 - 保留最近的N条消息"""
        if messages and messages[0].get("role") == "system":
            return [messages[0]] + messages[-10:]
        return messages[-10:]
    
    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算Token数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(content) // 4
        return total
    
    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """格式化消息为文本"""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"[{role.upper()}] {content}")
        return "\n\n".join(lines)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "compaction_count": self._compaction_count,
            "max_tokens": self.max_tokens,
            "threshold_ratio": self.threshold_ratio,
        }