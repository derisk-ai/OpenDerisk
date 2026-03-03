"""
MemoryCompaction - 记忆压缩机制

实现长对话的自动压缩和关键信息提取
支持LLM摘要生成、重要性评分、记忆保留策略
"""

from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import json
import asyncio
import logging
import re

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    FUNCTION = "function"


class MemoryMessage(BaseModel):
    """记忆消息"""
    id: str
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    importance_score: float = 0.5
    has_critical_info: bool = False
    is_summarized: bool = False
    
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class CompactionStrategy(str, Enum):
    """压缩策略"""
    LLM_SUMMARY = "llm_summary"
    SLIDING_WINDOW = "sliding_window"
    IMPORTANCE_BASED = "importance_based"
    HYBRID = "hybrid"


class KeyInfo(BaseModel):
    """关键信息"""
    key: str
    value: str
    category: str  # "fact", "decision", "action", "constraint", "preference"
    importance: float = 0.5
    source_message_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class CompactionResult(BaseModel):
    """压缩结果"""
    original_count: int
    compacted_count: int
    summary: str
    key_infos: List[KeyInfo] = Field(default_factory=list)
    kept_messages: List[MemoryMessage] = Field(default_factory=list)
    tokens_saved: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class ImportanceScorer:
    """重要性评分器"""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
    
    def score_message(self, message: MemoryMessage) -> float:
        """
        计算消息重要性分数
        
        Args:
            message: 消息
            
        Returns:
            float: 重要性分数 (0-1)
        """
        score = 0.5
        
        score += self._score_by_role(message.role)
        score += self._score_by_content(message.content)
        
        if message.has_critical_info:
            score += 0.3
        
        return min(1.0, max(0.0, score))
    
    def _score_by_role(self, role: MessageRole) -> float:
        """根据角色评分"""
        scores = {
            MessageRole.SYSTEM: 0.3,
            MessageRole.USER: 0.1,
            MessageRole.ASSISTANT: 0.05,
            MessageRole.FUNCTION: 0.0,
        }
        return scores.get(role, 0.0)
    
    def _score_by_content(self, content: str) -> float:
        """根据内容评分"""
        score = 0.0
        
        keywords = [
            "important", "critical", "关键", "重要",
            "remember", "note", "记住", "注意",
            "must", "should", "必须", "应该",
            "error", "warning", "错误", "警告",
            "decision", "决定", "选择", "decision",
            "result", "结果", "outcome",
        ]
        
        for keyword in keywords:
            if keyword.lower() in content.lower():
                score += 0.05
        
        patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'https?://[^\s]+',
            r'\$[\d,]+',
        ]
        
        for pattern in patterns:
            if re.search(pattern, content):
                score += 0.1
                break
        
        if len(content) > 500:
            score += 0.05
        elif len(content) < 20:
            score -= 0.05
        
        return min(0.2, score)
    
    async def score_with_llm(self, messages: List[MemoryMessage]) -> List[float]:
        """使用LLM评分"""
        if not self.llm_client:
            return [0.5] * len(messages)
        
        try:
            prompt = self._build_scoring_prompt(messages)
            from .llm_utils import call_llm
            response = await call_llm(self.llm_client, prompt)
            
            if response is None:
                return [0.5] * len(messages)
            
            scores = self._parse_llm_scores(response, len(messages))
            return scores
        except Exception as e:
            logger.error(f"[ImportanceScorer] LLM评分失败: {e}")
            return [0.5] * len(messages)
    
    def _build_scoring_prompt(self, messages: List[MemoryMessage]) -> str:
        """构建评分Prompt"""
        lines = ["请为以下消息的重要性打分（0-1分）：\n"]
        
        for i, msg in enumerate(messages):
            content_preview = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            lines.append(f"{i+1}. [{msg.role}] {content_preview}")
        
        lines.append("\n请以JSON数组格式返回分数列表，例如：[0.8, 0.3, 0.9, ...]")
        
        return "\n".join(lines)
    
    def _parse_llm_scores(self, response: str, count: int) -> List[float]:
        """解析LLM评分响应"""
        try:
            match = re.search(r'\[[\d\s.,]+\]', response)
            if match:
                scores = json.loads(match.group())
                return [float(s) for s in scores[:count]]
        except Exception:
            pass
        
        return [0.5] * count


class KeyInfoExtractor:
    """关键信息提取器"""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
    
    async def extract(self, messages: List[MemoryMessage]) -> List[KeyInfo]:
        """
        提取关键信息
        
        Args:
            messages: 消息列表
            
        Returns:
            List[KeyInfo]: 关键信息列表
        """
        if not self.llm_client:
            return self._extract_by_rules(messages)
        
        try:
            prompt = self._build_extraction_prompt(messages)
            from .llm_utils import call_llm
            response = await call_llm(self.llm_client, prompt)
            
            if response is None:
                return self._extract_by_rules(messages)
            
            key_infos = self._parse_extraction_response(response, messages)
            return key_infos
        except Exception as e:
            logger.error(f"[KeyInfoExtractor] LLM提取失败: {e}")
            return self._extract_by_rules(messages)
    
    def _extract_by_rules(self, messages: List[MemoryMessage]) -> List[KeyInfo]:
        """基于规则提取关键信息"""
        key_infos = []
        
        patterns = {
            "fact": [
                r'(我|用户|我们)的(\w+)是\s*[：:]\s*([^\n]+)',
                r'(name|名字|名称)\s*[是为：:]\s*([^\n]+)',
                r'(email|邮箱)\s*[是为：:]\s*([^\n]+)',
            ],
            "decision": [
                r'(决定|选择|选择使用)\s*[：:]\s*([^\n]+)',
                r'(最终方案|解决方案)\s*[是为：:]\s*([^\n]+)',
            ],
            "constraint": [
                r'(必须|应该|需要|requirement)\s*[：:]\s*([^\n]+)',
                r'(限制|约束|constraint)\s*[是为：:]\s*([^\n]+)',
            ],
        }
        
        for msg in messages:
            matches = []
            for category, pattern_list in patterns.items():
                for pattern in pattern_list:
                    found = re.findall(pattern, msg.content, re.IGNORECASE)
                    for match in found:
                        if isinstance(match, tuple):
                            matches.append((category, " ".join(match)))
                        else:
                            matches.append((category, match))
            
            for category, value in matches:
                key_infos.append(KeyInfo(
                    key=f"{category}_{len(key_infos)}",
                    value=value,
                    category=category,
                    source_message_id=msg.id,
                ))
        
        return key_infos
    
    def _build_extraction_prompt(self, messages: List[MemoryMessage]) -> str:
        """构建提取Prompt"""
        lines = ["请从以下对话中提取关键信息：\n"]
        
        for i, msg in enumerate(messages):
            lines.append(f"{i+1}. [{msg.role}] {msg.content}")
        
        lines.append("""
请以JSON格式返回关键信息列表：
[
    {"key": "关键信息名称", "value": "值", "category": "fact/decision/action/constraint/preference", "importance": 0.8}
]
""")
        
        return "\n".join(lines)
    
    def _parse_extraction_response(
        self,
        response: str,
        messages: List[MemoryMessage]
    ) -> List[KeyInfo]:
        """解析提取响应"""
        try:
            match = re.search(r'\[[\s\S]*?\]', response)
            if match:
                items = json.loads(match.group())
                
                key_infos = []
                for item in items[:10]:
                    source_id = None
                    for msg in messages:
                        if item.get("value", "") in msg.content:
                            source_id = msg.id
                            break
                    
                    key_infos.append(KeyInfo(
                        key=item.get("key", ""),
                        value=item.get("value", ""),
                        category=item.get("category", "fact"),
                        importance=item.get("importance", 0.5),
                        source_message_id=source_id,
                    ))
                
                return key_infos
        except Exception as e:
            logger.error(f"[KeyInfoExtractor] 解析失败: {e}")
        
        return self._extract_by_rules(messages)


class SummaryGenerator:
    """摘要生成器"""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
    
    async def generate(
        self,
        messages: List[MemoryMessage],
        style: str = "concise"
    ) -> str:
        """
        生成摘要
        
        Args:
            messages: 消息列表
            style: 摘要风格 (concise/detailed/thematic)
            
        Returns:
            str: 摘要文本
        """
        if not self.llm_client:
            return self._generate_simple_summary(messages)
        
        try:
            prompt = self._build_summary_prompt(messages, style)
            from .llm_utils import call_llm
            response = await call_llm(self.llm_client, prompt)
            return response.strip() if response else self._generate_simple_summary(messages)
        except Exception as e:
            logger.error(f"[SummaryGenerator] 摘要生成失败: {e}")
            return self._generate_simple_summary(messages)
    
    def _generate_simple_summary(self, messages: List[MemoryMessage]) -> str:
        """生成简单摘要"""
        if not messages:
            return "无对话记录"
        
        user_count = sum(1 for m in messages if m.role == MessageRole.USER)
        assistant_count = sum(1 for m in messages if m.role == MessageRole.ASSISTANT)
        
        return f"对话摘要：共{len(messages)}条消息，其中用户{user_count}条，助手{assistant_count}条。"
    
    def _build_summary_prompt(
        self,
        messages: List[MemoryMessage],
        style: str
    ) -> str:
        """构建摘要Prompt"""
        style_prompts = {
            "concise": "请用简洁的语言总结以下对话的核心内容（2-3句话）：",
            "detailed": "请详细总结以下对话的主要内容和关键信息：",
            "thematic": "请按主题总结以下对话的各个要点：",
        }
        
        lines = [style_prompts.get(style, style_prompts["concise"]), ""]
        
        for msg in messages:
            role_name = {"user": "用户", "assistant": "助手", "system": "系统"}.get(msg.role, msg.role)
            lines.append(f"{role_name}: {msg.content}")
        
        return "\n".join(lines)


class MemoryCompactor:
    """
    记忆压缩器
    
    职责：
    1. 压缩长对话
    2. 保留关键信息
    3. 生成摘要
    4. 管理记忆窗口
    
    示例:
        compactor = MemoryCompactor(llm_client=client)
        
        result = await compactor.compact(
            messages=messages,
            target_count=10,
            strategy=CompactionStrategy.HYBRID
        )
        
        print(f"压缩后消息数: {result.compacted_count}")
        print(f"摘要: {result.summary}")
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        max_messages: int = 50,
        keep_recent: int = 5,
        importance_threshold: float = 0.7
    ):
        self.llm_client = llm_client
        self.max_messages = max_messages
        self.keep_recent = keep_recent
        self.importance_threshold = importance_threshold
        
        self.scorer = ImportanceScorer(llm_client)
        self.extractor = KeyInfoExtractor(llm_client)
        self.summarizer = SummaryGenerator(llm_client)
    
    async def compact(
        self,
        messages: List[MemoryMessage],
        target_count: Optional[int] = None,
        strategy: CompactionStrategy = CompactionStrategy.HYBRID
    ) -> CompactionResult:
        """
        压缩消息
        
        Args:
            messages: 原始消息列表
            target_count: 目标消息数
            strategy: 压缩策略
            
        Returns:
            CompactionResult: 压缩结果
        """
        target_count = target_count or self.max_messages
        
        if len(messages) <= target_count:
            return CompactionResult(
                original_count=len(messages),
                compacted_count=len(messages),
                summary="消息数量未超过阈值，无需压缩",
                kept_messages=messages
            )
        
        logger.info(
            f"[MemoryCompactor] 开始压缩: {len(messages)} -> {target_count} "
            f"(strategy={strategy})"
        )
        
        if strategy == CompactionStrategy.LLM_SUMMARY:
            return await self._compact_by_llm_summary(messages, target_count)
        elif strategy == CompactionStrategy.SLIDING_WINDOW:
            return self._compact_by_sliding_window(messages, target_count)
        elif strategy == CompactionStrategy.IMPORTANCE_BASED:
            return await self._compact_by_importance(messages, target_count)
        else:
            return await self._compact_hybrid(messages, target_count)
    
    async def _compact_by_llm_summary(
        self,
        messages: List[MemoryMessage],
        target_count: int
    ) -> CompactionResult:
        """LLM摘要压缩"""
        to_summarize = messages[:-self.keep_recent]
        to_keep = messages[-self.keep_recent:]
        
        summary = await self.summarizer.generate(to_summarize)
        key_infos = await self.extractor.extract(to_summarize)
        
        summary_msg = MemoryMessage(
            id="summary-1",
            role=MessageRole.SYSTEM,
            content=f"[历史对话摘要]\n{summary}",
            is_summarized=True,
            importance_score=1.0,
            metadata={"key_infos": [ki.dict() for ki in key_infos]}
        )
        
        return CompactionResult(
            original_count=len(messages),
            compacted_count=len(to_keep) + 1,
            summary=summary,
            key_infos=key_infos,
            kept_messages=[summary_msg] + to_keep,
            tokens_saved=self._estimate_tokens_saved(messages, [summary_msg] + to_keep)
        )
    
    def _compact_by_sliding_window(
        self,
        messages: List[MemoryMessage],
        target_count: int
    ) -> CompactionResult:
        """滑动窗口压缩"""
        kept_messages = messages[-target_count:]
        
        removed_messages = messages[:-target_count]
        removed_summary = f"已移除 {len(removed_messages)} 条早期消息"
        
        return CompactionResult(
            original_count=len(messages),
            compacted_count=len(kept_messages),
            summary=removed_summary,
            kept_messages=kept_messages,
            tokens_saved=self._estimate_tokens_saved(messages, kept_messages)
        )
    
    async def _compact_by_importance(
        self,
        messages: List[MemoryMessage],
        target_count: int
    ) -> CompactionResult:
        """基于重要性压缩"""
        for msg in messages:
            msg.importance_score = self.scorer.score_message(msg)
        
        sorted_messages = sorted(
            enumerate(messages),
            key=lambda x: x[1].importance_score,
            reverse=True
        )
        
        recent_indices = set(range(len(messages) - self.keep_recent, len(messages)))
        keep_indices = set()
        
        for idx, msg in sorted_messages:
            if len(keep_indices) >= target_count:
                break
            
            if msg.importance_score >= self.importance_threshold or idx in recent_indices:
                keep_indices.add(idx)
        
        for i in range(len(messages) - 1, -1, -1):
            if len(keep_indices) >= target_count:
                break
            keep_indices.add(i)
        
        kept_messages = [messages[i] for i in sorted(keep_indices)]
        
        return CompactionResult(
            original_count=len(messages),
            compacted_count=len(kept_messages),
            summary=f"基于重要性保留了{len(kept_messages)}条关键消息",
            kept_messages=kept_messages,
            tokens_saved=self._estimate_tokens_saved(messages, kept_messages)
        )
    
    async def _compact_hybrid(
        self,
        messages: List[MemoryMessage],
        target_count: int
    ) -> CompactionResult:
        """混合压缩策略"""
        to_summarize_count = len(messages) - self.keep_recent - 2
        to_summarize = messages[:to_summarize_count]
        to_keep = messages[to_summarize_count:]
        
        for msg in to_summarize:
            msg.importance_score = self.scorer.score_message(msg)
        
        high_importance = [
            msg for msg in to_summarize
            if msg.importance_score >= self.importance_threshold
        ]
        
        summary = await self.summarizer.generate(to_summarize)
        key_infos = await self.extractor.extract(to_summarize)
        
        summary_msg = MemoryMessage(
            id="summary-1",
            role=MessageRole.SYSTEM,
            content=f"[历史对话摘要]\n{summary}",
            is_summarized=True,
            importance_score=1.0,
            metadata={"key_infos": [ki.dict() for ki in key_infos]}
        )
        
        kept_messages = [summary_msg] + high_importance[:3] + to_keep
        
        return CompactionResult(
            original_count=len(messages),
            compacted_count=len(kept_messages),
            summary=summary,
            key_infos=key_infos,
            kept_messages=kept_messages,
            tokens_saved=self._estimate_tokens_saved(messages, kept_messages)
        )
    
    def _estimate_tokens_saved(
        self,
        original: List[MemoryMessage],
        compacted: List[MemoryMessage]
    ) -> int:
        """估算节省的Token数"""
        original_chars = sum(len(m.content) for m in original)
        compacted_chars = sum(len(m.content) for m in compacted)
        
        return max(0, (original_chars - compacted_chars) // 4)


class MemoryCompactionManager:
    """
    记忆压缩管理器
    
    示例:
        manager = MemoryCompactionManager(llm_client=client)
        
        # 添加消息
        manager.add_message(session_id, message)
        
        # 检查并压缩
        if manager.should_compact(session_id):
            result = await manager.compact_session(session_id)
"""
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        compactor: Optional[MemoryCompactor] = None,
        auto_compact: bool = True,
        compact_threshold: int = 40
    ):
        self.llm_client = llm_client
        self.compactor = compactor or MemoryCompactor(llm_client)
        self.auto_compact = auto_compact
        self.compact_threshold = compact_threshold
        
        self._sessions: Dict[str, List[MemoryMessage]] = {}
        self._key_infos: Dict[str, List[KeyInfo]] = {}
        self._compaction_history: Dict[str, List[CompactionResult]] = {}
    
    def add_message(self, session_id: str, message: MemoryMessage):
        """添加消息"""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        self._sessions[session_id].append(message)
    
    def get_messages(self, session_id: str) -> List[MemoryMessage]:
        """获取消息"""
        return self._sessions.get(session_id, [])
    
    def should_compact(self, session_id: str) -> bool:
        """是否需要压缩"""
        messages = self._sessions.get(session_id, [])
        return len(messages) >= self.compact_threshold
    
    async def compact_session(
        self,
        session_id: str,
        strategy: CompactionStrategy = CompactionStrategy.HYBRID
    ) -> CompactionResult:
        """压缩会话"""
        messages = self._sessions.get(session_id, [])
        
        if not messages:
            return CompactionResult(
                original_count=0,
                compacted_count=0,
                summary="无消息"
            )
        
        result = await self.compactor.compact(messages, strategy=strategy)
        
        self._sessions[session_id] = result.kept_messages
        self._key_infos[session_id] = result.key_infos
        
        if session_id not in self._compaction_history:
            self._compaction_history[session_id] = []
        self._compaction_history[session_id].append(result)
        
        logger.info(
            f"[MemoryCompactionManager] 会话 {session_id[:8]} 压缩完成: "
            f"{result.original_count} -> {result.compacted_count} messages"
        )
        
        return result
    
    def get_key_infos(self, session_id: str) -> List[KeyInfo]:
        """获取关键信息"""
        return self._key_infos.get(session_id, [])
    
    def clear_session(self, session_id: str):
        """清除会话"""
        self._sessions.pop(session_id, None)
        self._key_infos.pop(session_id, None)
        self._compaction_history.pop(session_id, None)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_messages = sum(len(msgs) for msgs in self._sessions.values())
        total_compactions = sum(
            len(history) for history in self._compaction_history.values()
        )
        
        return {
            "active_sessions": len(self._sessions),
            "total_messages": total_messages,
            "total_compactions": total_compactions,
            "sessions": {
                sid: {
                    "message_count": len(msgs),
                    "key_info_count": len(self._key_infos.get(sid, [])),
                    "compaction_count": len(self._compaction_history.get(sid, []))
                }
                for sid, msgs in self._sessions.items()
            }
        }