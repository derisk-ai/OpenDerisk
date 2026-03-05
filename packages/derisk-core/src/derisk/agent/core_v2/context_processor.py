"""
ContextProcessor - 上下文处理器

根据策略配置处理上下文消息
支持截断、压缩、去重、保护等操作
"""

from typing import List, Dict, Any, Optional, Tuple, Callable
from pydantic import BaseModel
from datetime import datetime
import re
import hashlib
import logging
import asyncio

from derisk.agent.core_v2.task_scene import (
    ContextPolicy,
    TruncationPolicy,
    CompactionPolicy,
    DedupPolicy,
    TruncationStrategy,
    DedupStrategy,
)
from derisk.agent.core_v2.memory_compaction import (
    MemoryCompactor,
    MemoryMessage,
    MessageRole,
    CompactionStrategy,
    CompactionResult,
)

logger = logging.getLogger(__name__)


class ProcessResult(BaseModel):
    """处理结果"""
    original_count: int
    processed_count: int
    tokens_before: int = 0
    tokens_after: int = 0
    
    truncated_count: int = 0
    compacted_count: int = 0
    deduped_count: int = 0
    
    protected_blocks: int = 0
    processing_time_ms: float = 0
    
    actions: List[str] = []


class ProtectedBlock(BaseModel):
    """受保护的代码块"""
    block_id: str
    content: str
    block_type: str
    start_index: int
    end_index: int
    importance: float = 1.0


class ContextProcessor:
    """
    上下文处理器
    
    根据ContextPolicy对消息进行处理：
    1. 保护重要内容（代码块、思考链等）
    2. 去重
    3. 压缩
    4. 截断
    5. 恢复保护内容
    """
    
    CODE_BLOCK_PATTERN = re.compile(
        r'```[\w]*\n[\s\S]*?```|`[^`]+`',
        re.MULTILINE
    )
    THINKING_PATTERN = re.compile(
        r'<thinking>[\s\S]*?</thinking>',
        re.IGNORECASE
    )
    FILE_PATH_PATTERN = re.compile(
        r'(?:^|\s|[\'"])(/[a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+|[a-zA-Z]:\\[a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)',
        re.MULTILINE
    )
    
    def __init__(
        self,
        policy: ContextPolicy,
        llm_client: Optional[Any] = None,
        token_counter: Optional[Callable[[str], int]] = None,
    ):
        self.policy = policy
        self.llm_client = llm_client
        self.token_counter = token_counter or self._default_token_counter
        
        self._compactor: Optional[MemoryCompactor] = None
        self._protected_blocks: Dict[str, ProtectedBlock] = {}
        self._dedup_cache: Dict[str, str] = {}
    
    @property
    def compactor(self) -> MemoryCompactor:
        """延迟初始化压缩器"""
        if self._compactor is None:
            self._compactor = MemoryCompactor(
                llm_client=self.llm_client,
                max_messages=self.policy.compaction.trigger_threshold,
                keep_recent=self.policy.compaction.keep_recent_count,
                importance_threshold=self.policy.compaction.importance_threshold,
            )
        return self._compactor
    
    async def process(
        self,
        messages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], ProcessResult]:
        """处理消息列表"""
        start_time = datetime.now()
        result = ProcessResult(original_count=len(messages))
        
        if not messages:
            return messages, result
        
        processed = [self._copy_message(m) for m in messages]
        result.tokens_before = self._count_tokens(processed)
        
        if self.policy.truncation.file_path_protection:
            processed, count = self._protect_file_paths(processed)
            result.protected_blocks += count
            if count > 0:
                result.actions.append(f"protected {count} file paths")
        
        if self.policy.truncation.thinking_chain_protection:
            processed, count = self._protect_thinking_chains(processed)
            result.protected_blocks += count
            if count > 0:
                result.actions.append(f"protected {count} thinking chains")
        
        if self.policy.truncation.code_block_protection:
            processed, count = self._protect_code_blocks(processed)
            result.protected_blocks += count
            if count > 0:
                result.actions.append(f"protected {count} code blocks")
        
        if self.policy.dedup.enabled:
            processed, count = self._deduplicate(processed)
            result.deduped_count = count
            if count > 0:
                result.actions.append(f"deduped {count} messages")
        
        if (self.policy.enable_auto_compaction and 
            len(processed) > self.policy.compaction.trigger_threshold):
            processed, count, summary = await self._compact(processed, context)
            result.compacted_count = count
            if count > 0:
                result.actions.append(f"compacted {count} messages")
        
        if len(processed) > self._estimate_message_limit():
            processed, count = self._truncate(processed)
            result.truncated_count = count
            if count > 0:
                result.actions.append(f"truncated {count} messages")
        
        processed = self._restore_protected_content(processed)
        
        result.processed_count = len(processed)
        result.tokens_after = self._count_tokens(processed)
        result.processing_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.debug(
            f"[ContextProcessor] Processed {result.original_count} -> {result.processed_count} messages "
            f"({result.tokens_before} -> {result.tokens_after} tokens) in {result.processing_time_ms:.1f}ms"
        )
        
        return processed, result
    
    def _copy_message(self, msg: Dict) -> Dict:
        """深拷贝消息"""
        return {
            "role": msg.get("role"),
            "content": msg.get("content", ""),
            "name": msg.get("name"),
            "tool_calls": msg.get("tool_calls"),
            "tool_call_id": msg.get("tool_call_id"),
            "metadata": msg.get("metadata", {}).copy() if msg.get("metadata") else {},
        }
    
    def _count_tokens(self, messages: List[Dict]) -> int:
        """估算token数量"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.token_counter(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.token_counter(part["text"])
        return total
    
    def _default_token_counter(self, text: str) -> int:
        """默认token计数器（简单估算）"""
        return len(text) // 4
    
    def _protect_code_blocks(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """保护代码块"""
        count = 0
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            
            matches = list(self.CODE_BLOCK_PATTERN.finditer(content))
            if not matches:
                continue
            
            for match in reversed(matches):
                block_id = f"code_{i}_{len(self._protected_blocks)}"
                self._protected_blocks[block_id] = ProtectedBlock(
                    block_id=block_id,
                    content=match.group(),
                    block_type="code",
                    start_index=match.start(),
                    end_index=match.end(),
                )
                
                lines = match.group().split('\n')
                if len(lines) > self.policy.truncation.code_block_max_lines:
                    placeholder = f"[CODE_BLOCK:{block_id}:TRUNCATED]"
                else:
                    placeholder = f"[CODE_BLOCK:{block_id}]"
                
                content = content[:match.start()] + placeholder + content[match.end():]
                count += 1
            
            msg["content"] = content
        
        return messages, count
    
    def _protect_thinking_chains(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """保护思考链"""
        count = 0
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            
            matches = list(self.THINKING_PATTERN.finditer(content))
            if not matches:
                continue
            
            for match in reversed(matches):
                block_id = f"think_{i}_{len(self._protected_blocks)}"
                self._protected_blocks[block_id] = ProtectedBlock(
                    block_id=block_id,
                    content=match.group(),
                    block_type="thinking",
                    start_index=match.start(),
                    end_index=match.end(),
                )
                
                placeholder = f"[THINKING:{block_id}]"
                content = content[:match.start()] + placeholder + content[match.end():]
                count += 1
            
            msg["content"] = content
        
        return messages, count
    
    def _protect_file_paths(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """保护文件路径"""
        count = 0
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            
            matches = list(self.FILE_PATH_PATTERN.finditer(content))
            if not matches:
                continue
            
            for match in reversed(matches):
                block_id = f"path_{i}_{len(self._protected_blocks)}"
                self._protected_blocks[block_id] = ProtectedBlock(
                    block_id=block_id,
                    content=match.group().strip(),
                    block_type="file_path",
                    start_index=match.start(),
                    end_index=match.end(),
                )
                
                placeholder = f"[FILE_PATH:{block_id}]"
                content = content[:match.start()] + placeholder + content[match.end():]
                count += 1
            
            msg["content"] = content
        
        return messages, count
    
    def _restore_protected_content(self, messages: List[Dict]) -> List[Dict]:
        """恢复受保护的内容"""
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            
            for block_id, block in self._protected_blocks.items():
                placeholder_type = block.block_type
                if placeholder_type == "code":
                    placeholder = f"[CODE_BLOCK:{block_id}]"
                    truncated_placeholder = f"[CODE_BLOCK:{block_id}:TRUNCATED]"
                    if placeholder in content:
                        content = content.replace(placeholder, block.content)
                    elif truncated_placeholder in content:
                        lines = block.content.split('\n')
                        truncated = '\n'.join(
                            lines[:self.policy.truncation.code_block_max_lines]
                        ) + f"\n... (truncated, {len(lines)} lines total)"
                        content = content.replace(truncated_placeholder, truncated)
                elif placeholder_type == "thinking":
                    placeholder = f"[THINKING:{block_id}]"
                    if placeholder in content:
                        content = content.replace(placeholder, block.content)
                elif placeholder_type == "file_path":
                    placeholder = f"[FILE_PATH:{block_id}]"
                    if placeholder in content:
                        content = content.replace(placeholder, block.content)
            
            msg["content"] = content
        
        return messages
    
    def _deduplicate(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """去重"""
        if self.policy.dedup.strategy == DedupStrategy.NONE:
            return messages, 0
        
        deduped = []
        seen_hashes = set()
        count = 0
        
        window_size = self.policy.dedup.window_size
        
        for i, msg in enumerate(messages):
            if self.policy.dedup.preserve_first_occurrence:
                window = messages[max(0, i - window_size):i]
            else:
                window = messages[i+1:min(len(messages), i + window_size + 1)]
            
            content_hash = self._compute_content_hash(msg)
            
            is_duplicate = False
            if self.policy.dedup.strategy == DedupStrategy.EXACT:
                is_duplicate = content_hash in seen_hashes
            elif self.policy.dedup.strategy == DedupStrategy.SEMANTIC:
                is_duplicate = self._is_semantic_duplicate(msg, window)
            elif self.policy.dedup.strategy == DedupStrategy.SMART:
                is_duplicate = content_hash not in seen_hashes and self._is_likely_redundant(msg)
            
            if is_duplicate and not self._should_preserve(msg):
                count += 1
                continue
            
            if self.policy.dedup.preserve_first_occurrence:
                seen_hashes.add(content_hash)
            
            deduped.append(msg)
        
        return deduped, count
    
    def _compute_content_hash(self, msg: Dict) -> str:
        """计算内容哈希"""
        content = msg.get("content", "")
        if isinstance(content, str):
            normalized = content.strip().lower()
        else:
            normalized = str(content)
        
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _is_semantic_duplicate(self, msg: Dict, window: List[Dict]) -> bool:
        """判断是否语义重复"""
        msg_content = msg.get("content", "")
        if not isinstance(msg_content, str):
            return False
        
        msg_words = set(msg_content.lower().split())
        if len(msg_words) < 5:
            return False
        
        for w_msg in window:
            w_content = w_msg.get("content", "")
            if not isinstance(w_content, str):
                continue
            
            w_words = set(w_content.lower().split())
            if not w_words:
                continue
            
            intersection = len(msg_words & w_words)
            union = len(msg_words | w_words)
            
            if union > 0 and intersection / union >= self.policy.dedup.similarity_threshold:
                return True
        
        return False
    
    def _is_likely_redundant(self, msg: Dict) -> bool:
        """判断是否可能是冗余消息"""
        content = msg.get("content", "")
        if not isinstance(content, str):
            return False
        
        short_threshold = 50
        if len(content) < short_threshold:
            role = msg.get("role", "")
            if role in ["assistant", "tool"]:
                return True
        
        return False
    
    def _should_preserve(self, msg: Dict) -> bool:
        """判断消息是否应该保留"""
        role = msg.get("role", "")
        
        if self.policy.compaction.preserve_user_questions and role == "user":
            return True
        if self.policy.compaction.preserve_error_messages:
            content = msg.get("content", "")
            if isinstance(content, str) and ("error" in content.lower() or "错误" in content):
                return True
        if self.policy.compaction.preserve_tool_results and role == "tool":
            return True
        
        return False
    
    async def _compact(
        self,
        messages: List[Dict],
        context: Optional[Dict] = None,
    ) -> Tuple[List[Dict], int, str]:
        """压缩消息"""
        memory_messages = self._to_memory_messages(messages)
        
        result = await self.compactor.compact(
            messages=memory_messages,
            target_count=self.policy.compaction.target_message_count,
            strategy=self._map_compaction_strategy(),
        )
        
        compacted = self._from_memory_messages(result.kept_messages)
        
        return compacted, result.original_count - result.compacted_count, result.summary
    
    def _to_memory_messages(self, messages: List[Dict]) -> List[MemoryMessage]:
        """转换为MemoryMessage格式"""
        memory_messages = []
        for i, msg in enumerate(messages):
            role_str = msg.get("role", "user")
            role_map = {
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "system": MessageRole.SYSTEM,
                "tool": MessageRole.FUNCTION,
            }
            
            memory_messages.append(MemoryMessage(
                id=msg.get("id", f"msg_{i}"),
                role=role_map.get(role_str, MessageRole.USER),
                content=msg.get("content", ""),
                metadata=msg,
            ))
        
        return memory_messages
    
    def _from_memory_messages(self, memory_messages: List[MemoryMessage]) -> List[Dict]:
        """从MemoryMessage格式转换回来"""
        messages = []
        for mm in memory_messages:
            if mm.is_summarized:
                messages.append({
                    "role": "system",
                    "content": mm.content,
                    "metadata": mm.metadata,
                })
            elif mm.metadata:
                msg = mm.metadata.get("metadata", mm.metadata)
                if isinstance(msg, dict):
                    messages.append(msg)
                else:
                    messages.append({
                        "role": mm.role,
                        "content": mm.content,
                    })
            else:
                messages.append({
                    "role": mm.role,
                    "content": mm.content,
                })
        
        return messages
    
    def _map_compaction_strategy(self) -> CompactionStrategy:
        """映射压缩策略"""
        strategy_map = {
            "llm_summary": CompactionStrategy.LLM_SUMMARY,
            "sliding_window": CompactionStrategy.SLIDING_WINDOW,
            "importance_based": CompactionStrategy.IMPORTANCE_BASED,
            "hybrid": CompactionStrategy.HYBRID,
        }
        return strategy_map.get(
            self.policy.compaction.strategy,
            CompactionStrategy.HYBRID
        )
    
    def _estimate_message_limit(self) -> int:
        """估算消息数量限制"""
        budget = self.policy.token_budget
        avg_tokens_per_message = 200
        return budget.history_budget // avg_tokens_per_message
    
    def _truncate(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """截断消息"""
        strategy = self.policy.truncation.strategy
        original_count = len(messages)
        
        if strategy == TruncationStrategy.AGGRESSIVE:
            return self._truncate_aggressive(messages)
        elif strategy == TruncationStrategy.CONSERVATIVE:
            return self._truncate_conservative(messages)
        elif strategy == TruncationStrategy.ADAPTIVE:
            return self._truncate_adaptive(messages)
        elif strategy == TruncationStrategy.CODE_AWARE:
            return self._truncate_code_aware(messages)
        else:
            return self._truncate_balanced(messages)
    
    def _truncate_aggressive(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """激进截断"""
        limit = self._estimate_message_limit()
        limit = int(limit * 0.6)
        
        if len(messages) <= limit:
            return messages, 0
        
        if self.policy.truncation.preserve_system_messages:
            system_msgs = [m for m in messages if m.get("role") == "system"]
            other_msgs = [m for m in messages if m.get("role") != "system"]
        else:
            system_msgs = []
            other_msgs = messages
        
        recent_count = max(1, int(len(other_msgs) * 0.3))
        recent = other_msgs[-recent_count:]
        
        if self.policy.truncation.preserve_first_user_message:
            first_user = next(
                (m for m in other_msgs if m.get("role") == "user"),
                None
            )
            if first_user and first_user not in recent:
                recent.insert(0, first_user)
        
        truncated = system_msgs + recent
        return truncated, original_count - len(truncated)
    
    def _truncate_balanced(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """平衡截断"""
        limit = self._estimate_message_limit()
        
        if len(messages) <= limit:
            return messages, 0
        
        keep_ratio = self.policy.truncation.preserve_recent_ratio
        
        if self.policy.truncation.preserve_system_messages:
            system_msgs = [m for m in messages if m.get("role") == "system"]
            other_msgs = [m for m in messages if m.get("role") != "system"]
        else:
            system_msgs = []
            other_msgs = messages
        
        recent_count = max(1, int(len(other_msgs) * keep_ratio))
        mid_count = int((limit - len(system_msgs) - recent_count) / 2)
        
        recent = other_msgs[-recent_count:]
        early = other_msgs[:mid_count] if mid_count > 0 else []
        
        if self.policy.truncation.preserve_first_user_message:
            first_user = next(
                (m for m in other_msgs if m.get("role") == "user"),
                None
            )
            if first_user and first_user not in early:
                early.insert(0, first_user)
        
        truncated = system_msgs + early + recent
        return truncated, original_count - len(truncated)
    
    def _truncate_conservative(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """保守截断"""
        limit = self._estimate_message_limit()
        limit = int(limit * 1.2)
        
        if len(messages) <= limit:
            return messages, 0
        
        keep_ratio = self.policy.truncation.preserve_recent_ratio * 1.5
        
        if self.policy.truncation.preserve_system_messages:
            system_msgs = [m for m in messages if m.get("role") == "system"]
            other_msgs = [m for m in messages if m.get("role") != "system"]
        else:
            system_msgs = []
            other_msgs = messages
        
        recent_count = int(len(other_msgs) * min(keep_ratio, 0.5))
        recent = other_msgs[-recent_count:]
        early = other_msgs[:-recent_count][:limit - len(system_msgs) - recent_count]
        
        if self.policy.truncation.preserve_first_user_message:
            first_user = next(
                (m for m in other_msgs if m.get("role") == "user"),
                None
            )
            if first_user and first_user not in early:
                early.insert(0, first_user)
        
        truncated = system_msgs + early + recent
        return truncated, original_count - len(truncated)
    
    def _truncate_adaptive(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """自适应截断"""
        code_block_count = sum(
            1 for m in messages 
            if self.CODE_BLOCK_PATTERN.search(str(m.get("content", "")))
        )
        
        code_ratio = code_block_count / len(messages) if messages else 0
        
        if code_ratio > 0.3:
            return self._truncate_code_aware(messages)
        elif code_ratio > 0.1:
            return self._truncate_balanced(messages)
        else:
            return self._truncate_conservative(messages)
    
    def _truncate_code_aware(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """代码感知截断"""
        limit = self._estimate_message_limit()
        
        if len(messages) <= limit:
            return messages, 0
        
        code_messages = []
        other_messages = []
        
        for m in messages:
            content = str(m.get("content", ""))
            if self.CODE_BLOCK_PATTERN.search(content):
                code_messages.append(m)
            else:
                other_messages.append(m)
        
        if len(code_messages) > limit * 0.7:
            code_limit = int(limit * 0.7)
            other_limit = limit - code_limit
            
            code_kept = code_messages[-code_limit:]
            other_kept = other_messages[-other_limit:] if other_messages else []
        else:
            code_kept = code_messages
            other_limit = limit - len(code_kept)
            other_kept = other_messages[-other_limit:] if other_messages else []
        
        def get_index(msg):
            try:
                return messages.index(msg)
            except ValueError:
                return len(messages)
        
        all_kept = set(get_index(m) for m in code_kept + other_kept)
        
        if self.policy.truncation.preserve_system_messages:
            for i, m in enumerate(messages):
                if m.get("role") == "system":
                    all_kept.add(i)
        
        if self.policy.truncation.preserve_first_user_message:
            for i, m in enumerate(messages):
                if m.get("role") == "user":
                    all_kept.add(i)
                    break
        
        truncated = [messages[i] for i in sorted(all_kept)]
        return truncated, len(messages) - len(truncated)
    
    def clear_cache(self):
        """清除缓存"""
        self._protected_blocks.clear()
        self._dedup_cache.clear()


class ContextProcessorFactory:
    """上下文处理器工厂"""
    
    _instances: Dict[str, ContextProcessor] = {}
    
    @classmethod
    def get(cls, policy: ContextPolicy, llm_client: Optional[Any] = None) -> ContextProcessor:
        """获取或创建处理器"""
        key = f"{policy.truncation.strategy}_{policy.compaction.strategy}_{id(llm_client)}"
        
        if key not in cls._instances:
            cls._instances[key] = ContextProcessor(policy, llm_client)
        
        return cls._instances[key]
    
    @classmethod
    def clear(cls):
        """清除所有实例"""
        cls._instances.clear()