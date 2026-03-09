"""
四层上下文压缩架构 - Layer 4: 跨轮次对话历史压缩

该模块实现了第四层压缩机制，专门处理多轮对话历史的压缩和管理。

架构设计：
- Layer 1: Truncation (单个工具输出截断)
- Layer 2: Pruning (同一轮内历史修剪)  
- Layer 3: Compaction (同一轮内会话压缩)
- Layer 4: Multi-Turn History (跨轮次对话历史压缩) <- 本模块

工作流程：
1. 历史轮次：用户提问 + WorkLog摘要 + 答案摘要（压缩存储）
2. 当前轮次：原生Function Call模式，tool messages直接传递
3. memory变量：仅注入历史轮次的压缩摘要
"""

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union

from derisk.agent import ActionOutput
from derisk.agent.core.memory.gpts.base import GptsMessage

logger = logging.getLogger(__name__)


class ConversationRoundStatus(Enum):
    """对话轮次状态"""
    ACTIVE = "active"           # 当前活跃轮次
    COMPLETED = "completed"     # 已完成，待压缩
    COMPRESSED = "compressed"   # 已压缩存档
    ARCHIVED = "archived"       # 已归档到长期存储


@dataclass
class WorkLogSummary:
    """WorkLog 摘要信息"""
    tool_count: int = 0
    key_tools: List[str] = field(default_factory=list)
    key_findings: str = ""
    execution_time_ms: int = 0
    success_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_count": self.tool_count,
            "key_tools": self.key_tools,
            "key_findings": self.key_findings,
            "execution_time_ms": self.execution_time_ms,
            "success_rate": self.success_rate,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkLogSummary":
        return cls(
            tool_count=data.get("tool_count", 0),
            key_tools=data.get("key_tools", []),
            key_findings=data.get("key_findings", ""),
            execution_time_ms=data.get("execution_time_ms", 0),
            success_rate=data.get("success_rate", 0.0),
        )


@dataclass
class ConversationRound:
    """
    对话轮次
    
    表示一个完整的用户-AI交互轮次，包含：
    - 用户提问
    - WorkLog（工具执行记录）
    - AI回答
    """
    round_id: str
    conv_id: str
    session_id: str
    
    # 用户提问
    user_question: str = ""
    user_context: Dict[str, Any] = field(default_factory=dict)
    
    # WorkLog（工具执行记录）
    work_log_entries: List[Dict[str, Any]] = field(default_factory=list)
    work_log_summary: Optional[WorkLogSummary] = None
    
    # AI回答
    ai_response: str = ""
    ai_thinking: str = ""
    
    # 元数据
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: ConversationRoundStatus = ConversationRoundStatus.ACTIVE
    
    # 压缩后存储
    compressed_content: Optional[str] = None
    compression_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def mark_completed(self):
        """标记轮次完成"""
        self.status = ConversationRoundStatus.COMPLETED
        self.completed_at = time.time()
    
    def mark_compressed(self, compressed_content: str, metadata: Dict[str, Any]):
        """标记已压缩"""
        self.status = ConversationRoundStatus.COMPRESSED
        self.compressed_content = compressed_content
        self.compression_metadata = metadata
        # 清除原始数据以节省内存
        self.work_log_entries.clear()
    
    def to_prompt_format(self, include_full_content: bool = False) -> str:
        """
        转换为 prompt 格式
        
        Args:
            include_full_content: 是否包含完整内容（而非摘要）
        
        Returns:
            格式化后的文本
        """
        if self.status == ConversationRoundStatus.COMPRESSED and not include_full_content:
            # 返回压缩摘要
            return self.compressed_content or "[轮次内容已压缩]"
        
        lines = [
            f"=== 第 {self.round_id} 轮对话 ===",
            f"",
            f"**用户**: {self.user_question[:200]}{'...' if len(self.user_question) > 200 else ''}",
            f"",
        ]
        
        # WorkLog 摘要
        if self.work_log_summary:
            lines.extend([
                f"**执行摘要**:",
                f"- 工具调用: {self.work_log_summary.tool_count} 次",
                f"- 主要工具: {', '.join(self.work_log_summary.key_tools[:5])}",
                f"- 成功率: {self.work_log_summary.success_rate:.1%}",
                f"",
            ])
        
        # 关键发现
        if self.work_log_summary and self.work_log_summary.key_findings:
            lines.extend([
                f"**关键发现**: {self.work_log_summary.key_findings[:300]}",
                f"",
            ])
        
        # AI 回答摘要
        if self.ai_response:
            response_preview = self.ai_response[:300]
            lines.extend([
                f"**AI回答**: {response_preview}{'...' if len(self.ai_response) > 300 else ''}",
            ])
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_id": self.round_id,
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "user_question": self.user_question,
            "user_context": self.user_context,
            "work_log_summary": self.work_log_summary.to_dict() if self.work_log_summary else None,
            "ai_response": self.ai_response,
            "ai_thinking": self.ai_thinking,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "compressed_content": self.compressed_content,
            "compression_metadata": self.compression_metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationRound":
        round_obj = cls(
            round_id=data["round_id"],
            conv_id=data["conv_id"],
            session_id=data["session_id"],
            user_question=data.get("user_question", ""),
            user_context=data.get("user_context", {}),
            work_log_summary=WorkLogSummary.from_dict(data["work_log_summary"]) if data.get("work_log_summary") else None,
            ai_response=data.get("ai_response", ""),
            ai_thinking=data.get("ai_thinking", ""),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
            status=ConversationRoundStatus(data.get("status", "active")),
            compressed_content=data.get("compressed_content"),
            compression_metadata=data.get("compression_metadata", {}),
        )
        return round_obj


@dataclass
class Layer4CompressionConfig:
    """Layer 4 压缩配置"""
    
    # 触发压缩的阈值
    max_rounds_before_compression: int = 3  # 保留最近3轮不压缩
    max_total_rounds: int = 10  # 最多保留10轮历史
    
    # 压缩参数
    compression_token_threshold: int = 8000  # 超过此token数触发压缩
    chars_per_token: int = 4
    
    # 摘要长度限制
    max_question_summary_length: int = 200
    max_response_summary_length: int = 300
    max_findings_length: int = 300
    
    # 存储配置
    enable_persistent_storage: bool = True
    storage_key_prefix: str = "layer4_history"


class ConversationHistoryStorage(Protocol):
    """对话历史存储接口"""
    
    async def save_round(self, session_id: str, round_data: ConversationRound) -> bool:
        """保存对话轮次"""
        ...
    
    async def load_rounds(self, session_id: str, limit: Optional[int] = None) -> List[ConversationRound]:
        """加载对话轮次列表"""
        ...
    
    async def update_round(self, session_id: str, round_data: ConversationRound) -> bool:
        """更新对话轮次"""
        ...
    
    async def delete_session_history(self, session_id: str) -> bool:
        """删除会话历史"""
        ...


class ConversationHistoryManager:
    """
    对话历史管理器（Layer 4 压缩实现）
    
    职责：
    1. 管理多轮对话历史
    2. 对历史轮次进行压缩
    3. 提供压缩后的历史摘要供 prompt 使用
    4. 区分"历史轮次"（已压缩）和"当前轮次"（原生Function Call）
    """
    
    def __init__(
        self,
        session_id: str,
        storage: Optional[ConversationHistoryStorage] = None,
        config: Optional[Layer4CompressionConfig] = None,
    ):
        self.session_id = session_id
        self.storage = storage
        self.config = config or Layer4CompressionConfig()
        
        # 内存缓存
        self._rounds: Dict[str, ConversationRound] = {}
        self._current_round: Optional[ConversationRound] = None
        self._round_order: List[str] = []
        
        # 锁
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """初始化，加载历史数据"""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            if self.storage:
                try:
                    rounds = await self.storage.load_rounds(
                        self.session_id, 
                        limit=self.config.max_total_rounds
                    )
                    for round_obj in rounds:
                        self._rounds[round_obj.round_id] = round_obj
                        self._round_order.append(round_obj.round_id)
                    logger.info(f"Loaded {len(rounds)} conversation rounds for session {self.session_id}")
                except Exception as e:
                    logger.warning(f"Failed to load conversation history: {e}")
            
            self._initialized = True
    
    async def start_new_round(self, user_question: str, user_context: Optional[Dict] = None) -> ConversationRound:
        """
        开始新一轮对话
        
        Args:
            user_question: 用户提问
            user_context: 用户上下文
        
        Returns:
            新创建的对话轮次
        """
        await self.initialize()
        
        async with self._lock:
            # 先完成当前轮次
            if self._current_round:
                await self._complete_current_round()
            
            # 创建新轮次
            round_id = f"round_{int(time.time())}_{len(self._round_order)}"
            new_round = ConversationRound(
                round_id=round_id,
                conv_id=f"{self.session_id}_{round_id}",
                session_id=self.session_id,
                user_question=user_question,
                user_context=user_context or {},
                status=ConversationRoundStatus.ACTIVE,
            )
            
            self._current_round = new_round
            self._rounds[round_id] = new_round
            self._round_order.append(round_id)
            
            logger.info(f"Started new conversation round: {round_id}")
            return new_round
    
    async def update_current_round_worklog(self, worklog_entries: List[Dict[str, Any]], summary: Optional[WorkLogSummary] = None):
        """
        更新当前轮次的 WorkLog
        
        Args:
            worklog_entries: WorkLog 条目列表
            summary: WorkLog 摘要
        """
        if not self._current_round:
            logger.warning("No active round to update worklog")
            return
        
        async with self._lock:
            self._current_round.work_log_entries.extend(worklog_entries)
            if summary:
                self._current_round.work_log_summary = summary
    
    async def complete_current_round(self, ai_response: str, ai_thinking: str = ""):
        """
        完成当前轮次
        
        Args:
            ai_response: AI 回答
            ai_thinking: AI 思考过程
        """
        if not self._current_round:
            logger.warning("No active round to complete")
            return
        
        async with self._lock:
            self._current_round.ai_response = ai_response
            self._current_round.ai_thinking = ai_thinking
            self._current_round.mark_completed()
            
            # 保存到存储
            if self.storage:
                try:
                    await self.storage.save_round(self.session_id, self._current_round)
                except Exception as e:
                    logger.error(f"Failed to save completed round: {e}")
            
            # 触发压缩检查
            await self._check_and_compress_history()
            
            logger.info(f"Completed conversation round: {self._current_round.round_id}")
            self._current_round = None
    
    async def _complete_current_round(self):
        """内部方法：完成当前轮次（用于开始新轮次前）"""
        if self._current_round:
            self._current_round.mark_completed()
            if self.storage:
                try:
                    await self.storage.save_round(self.session_id, self._current_round)
                except Exception as e:
                    logger.error(f"Failed to save round: {e}")
    
    async def _check_and_compress_history(self):
        """检查并压缩历史"""
        # 获取需要压缩的轮次（保留最近的 N 轮）
        if len(self._round_order) <= self.config.max_rounds_before_compression:
            return
        
        rounds_to_compress = self._round_order[:-self.config.max_rounds_before_compression]
        
        for round_id in rounds_to_compress:
            round_obj = self._rounds.get(round_id)
            if round_obj and round_obj.status == ConversationRoundStatus.COMPLETED:
                await self._compress_round(round_obj)
    
    async def _compress_round(self, round_obj: ConversationRound):
        """
        压缩单个轮次
        
        生成简洁的摘要替代完整内容
        """
        try:
            # 生成摘要
            summary_lines = [
                f"[第 {round_obj.round_id} 轮]",
                f"Q: {round_obj.user_question[:self.config.max_question_summary_length]}{'...' if len(round_obj.user_question) > self.config.max_question_summary_length else ''}",
            ]
            
            if round_obj.work_log_summary:
                wls = round_obj.work_log_summary
                summary_lines.append(f"Tools: {wls.tool_count} calls ({', '.join(wls.key_tools[:3])})")
                if wls.key_findings:
                    findings = wls.key_findings[:self.config.max_findings_length]
                    summary_lines.append(f"Findings: {findings}{'...' if len(wls.key_findings) > self.config.max_findings_length else ''}")
            
            if round_obj.ai_response:
                response = round_obj.ai_response[:self.config.max_response_summary_length]
                summary_lines.append(f"A: {response}{'...' if len(round_obj.ai_response) > self.config.max_response_summary_length else ''}")
            
            compressed_content = "\n".join(summary_lines)
            
            # 标记为已压缩
            metadata = {
                "compressed_at": time.time(),
                "original_question_length": len(round_obj.user_question),
                "original_response_length": len(round_obj.ai_response),
                "compression_ratio": len(compressed_content) / max(len(round_obj.user_question) + len(round_obj.ai_response), 1),
            }
            
            round_obj.mark_compressed(compressed_content, metadata)
            
            # 更新存储
            if self.storage:
                await self.storage.update_round(self.session_id, round_obj)
            
            logger.info(f"Compressed conversation round: {round_obj.round_id}")
            
        except Exception as e:
            logger.error(f"Failed to compress round {round_obj.round_id}: {e}")
    
    async def get_history_for_prompt(
        self, 
        max_rounds: Optional[int] = None,
        include_current: bool = False,
    ) -> str:
        """
        获取用于 prompt 的历史记录
        
        Args:
            max_rounds: 最大轮次数（None表示使用配置）
            include_current: 是否包含当前轮次
        
        Returns:
            格式化后的历史文本
        """
        await self.initialize()
        
        async with self._lock:
            max_count = max_rounds or self.config.max_total_rounds
            
            # 获取要显示的轮次（最新的 N 个）
            round_ids = self._round_order[-max_count:]
            
            if not round_ids:
                return ""
            
            lines = ["## 历史对话记录", ""]
            
            for round_id in round_ids:
                round_obj = self._rounds.get(round_id)
                if not round_obj:
                    continue
                
                # 跳过当前轮次（除非明确要求包含）
                if round_obj == self._current_round and not include_current:
                    continue
                
                # 获取格式化内容
                round_text = round_obj.to_prompt_format(include_full_content=False)
                lines.append(round_text)
                lines.append("")
            
            return "\n".join(lines)
    
    async def get_current_round_summary(self) -> Optional[str]:
        """获取当前轮次的摘要（用于调试）"""
        if not self._current_round:
            return None
        return self._current_round.to_prompt_format(include_full_content=True)
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        await self.initialize()
        
        async with self._lock:
            total = len(self._rounds)
            compressed = sum(1 for r in self._rounds.values() if r.status == ConversationRoundStatus.COMPRESSED)
            active = sum(1 for r in self._rounds.values() if r.status == ConversationRoundStatus.ACTIVE)
            completed = sum(1 for r in self._rounds.values() if r.status == ConversationRoundStatus.COMPLETED)
            
            return {
                "total_rounds": total,
                "active_rounds": active,
                "completed_rounds": completed,
                "compressed_rounds": compressed,
                "current_round_id": self._current_round.round_id if self._current_round else None,
                "session_id": self.session_id,
            }
    
    async def clear_history(self):
        """清除历史记录"""
        async with self._lock:
            self._rounds.clear()
            self._round_order.clear()
            self._current_round = None
            
            if self.storage:
                await self.storage.delete_session_history(self.session_id)
            
            logger.info(f"Cleared conversation history for session {self.session_id}")


# 全局管理器缓存
_history_managers: Dict[str, ConversationHistoryManager] = {}
_manager_lock = asyncio.Lock()


async def get_conversation_history_manager(
    session_id: str,
    storage: Optional[ConversationHistoryStorage] = None,
    config: Optional[Layer4CompressionConfig] = None,
) -> ConversationHistoryManager:
    """
    获取或创建对话历史管理器（单例模式）
    
    Args:
        session_id: 会话ID
        storage: 存储接口
        config: 配置
    
    Returns:
        ConversationHistoryManager 实例
    """
    async with _manager_lock:
        if session_id not in _history_managers:
            manager = ConversationHistoryManager(
                session_id=session_id,
                storage=storage,
                config=config,
            )
            await manager.initialize()
            _history_managers[session_id] = manager
            logger.info(f"Created new ConversationHistoryManager for session {session_id}")
        
        return _history_managers[session_id]


def clear_history_manager_cache(session_id: Optional[str] = None):
    """
    清除历史管理器缓存
    
    Args:
        session_id: 指定会话ID（None表示清除所有）
    """
    global _history_managers
    if session_id:
        _history_managers.pop(session_id, None)
        logger.info(f"Cleared history manager cache for session {session_id}")
    else:
        _history_managers.clear()
        logger.info("Cleared all history manager cache")
