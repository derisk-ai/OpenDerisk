"""
Hierarchical Memory Manager - 分层记忆管理系统

实现三层记忆架构：
- Working Memory (工作记忆): 当前任务相关的短期记忆
- Episodic Memory (情景记忆): 近期任务的中期记忆
- Semantic Memory (语义记忆): 长期知识存储

此模块实现 P2 改进方案。
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .smart_checkpoint import StateStore

logger = logging.getLogger(__name__)


class MemoryLayer(Enum):
    """
    记忆层级

    借鉴人类记忆系统的三层架构：
    1. WORKING - 工作记忆：容量有限，快速访问，当前任务相关
    2. EPISODIC - 情景记忆：中期存储，保存事件序列
    3. SEMANTIC - 语义记忆：长期存储，抽象知识
    """

    WORKING = "working"  # 工作记忆（当前任务）
    EPISODIC = "episodic"  # 情景记忆（近期任务）
    SEMANTIC = "semantic"  # 语义记忆（长期知识）

    def next_layer(self) -> Optional["MemoryLayer"]:
        """获取下一层级"""
        order = [MemoryLayer.WORKING, MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC]
        try:
            idx = order.index(self)
            if idx < len(order) - 1:
                return order[idx + 1]
        except ValueError:
            pass
        return None

    def prev_layer(self) -> Optional["MemoryLayer"]:
        """获取上一层级"""
        order = [MemoryLayer.WORKING, MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC]
        try:
            idx = order.index(self)
            if idx > 0:
                return order[idx - 1]
        except ValueError:
            pass
        return None


class MemoryType(Enum):
    """记忆类型"""

    CONVERSATION = "conversation"  # 对话记录
    ACTION = "action"  # 行动记录
    DECISION = "decision"  # 决策记录
    OBSERVATION = "observation"  # 观察结果
    ERROR = "error"  # 错误信息
    INSIGHT = "insight"  # 洞察发现
    SUMMARY = "summary"  # 摘要信息
    KNOWLEDGE = "knowledge"  # 知识条目


@dataclass
class MemoryEntry:
    """
    记忆条目

    存储单个记忆单元，包含：
    - 内容
    - 重要性分数
    - 时间戳
    - 元数据
    - 嵌入向量（可选）
    """

    id: str
    content: str
    memory_type: MemoryType
    layer: MemoryLayer

    # 重要性评分 (0.0 - 1.0)
    importance: float = 0.5

    # 时间相关
    timestamp: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 关联信息
    source_id: Optional[str] = None  # 来源记忆ID
    related_ids: List[str] = field(default_factory=list)

    # 嵌入向量（用于语义检索）
    embedding: Optional[List[float]] = None

    # Token 估算
    token_count: Optional[int] = None

    def __post_init__(self):
        if self.token_count is None:
            # 简单估算：约 4 个字符 = 1 token
            self.token_count = len(self.content) // 4

    def touch(self) -> None:
        """更新访问时间和计数"""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def compute_relevance(self, query: str) -> float:
        """
        计算与查询的相关性

        简单实现：基于关键词匹配
        实际应用中可以使用向量相似度
        """
        query_words = set(query.lower().split())
        content_words = set(self.content.lower().split())

        if not query_words:
            return 0.0

        overlap = len(query_words & content_words)
        return overlap / len(query_words)

    def compute_recency_score(self, now: Optional[datetime] = None) -> float:
        """计算时间新鲜度分数"""
        now = now or datetime.now()
        age_seconds = (now - self.timestamp).total_seconds()

        # 指数衰减
        # 1小时：~0.9, 1天：~0.5, 1周：~0.1
        decay_rate = 0.00001  # 每秒衰减率
        return float(self.importance * (1.0 / (1.0 + decay_rate * age_seconds)))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "layer": self.layer.value,
            "importance": self.importance,
            "timestamp": self.timestamp.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
            "source_id": self.source_id,
            "related_ids": self.related_ids,
            "token_count": self.token_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """从字典创建"""
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            layer=MemoryLayer(data["layer"]),
            importance=data.get("importance", 0.5),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
            source_id=data.get("source_id"),
            related_ids=data.get("related_ids", []),
            token_count=data.get("token_count"),
        )


@dataclass
class MemoryStats:
    """记忆统计信息"""

    total_entries: int = 0
    total_tokens: int = 0
    layer_counts: Dict[str, int] = field(default_factory=dict)
    type_counts: Dict[str, int] = field(default_factory=dict)
    avg_importance: float = 0.0
    oldest_entry: Optional[datetime] = None
    newest_entry: Optional[datetime] = None


class MemoryCompressor(ABC):
    """记忆压缩器抽象基类"""

    @abstractmethod
    async def compress(self, entries: List[MemoryEntry]) -> MemoryEntry:
        """压缩多个记忆条目为一个摘要"""
        pass


class SimpleMemoryCompressor(MemoryCompressor):
    """简单的记忆压缩器"""

    async def compress(self, entries: List[MemoryEntry]) -> MemoryEntry:
        """将多个条目压缩为一个摘要条目"""
        if not entries:
            raise ValueError("Cannot compress empty list")

        # 生成摘要内容
        content_parts = []
        for entry in entries[:10]:  # 最多取10条
            content_parts.append(f"- [{entry.memory_type.value}] {entry.content[:200]}")

        summary_content = f"压缩了 {len(entries)} 条记忆:\n" + "\n".join(content_parts)

        # 计算平均重要性
        avg_importance = sum(e.importance for e in entries) / len(entries)

        # 创建摘要条目
        return MemoryEntry(
            id=str(uuid.uuid4().hex),
            content=summary_content,
            memory_type=MemoryType.SUMMARY,
            layer=entries[0].layer.next_layer() or MemoryLayer.SEMANTIC,
            importance=avg_importance,
            metadata={
                "compressed_count": len(entries),
                "source_types": list(set(e.memory_type.value for e in entries)),
            },
            related_ids=[e.id for e in entries],
        )


class HierarchicalMemoryManager:
    """
    分层记忆管理器

    管理三层记忆系统：
    1. Working Memory: 当前任务相关，容量小，快速访问
    2. Episodic Memory: 近期事件序列，中等容量
    3. Semantic Memory: 长期知识，大容量

    自动处理：
    - 记忆降级（容量溢出时）
    - 记忆压缩（层级转换时）
    - 记忆检索（相关性查询）

    示例:
        manager = HierarchicalMemoryManager(
            working_memory_tokens=8000,
            episodic_memory_tokens=32000,
            semantic_memory_tokens=128000,
        )

        # 添加记忆
        memory_id = await manager.add_memory(
            content="用户要求分析日志",
            memory_type=MemoryType.CONVERSATION,
            importance=0.8
        )

        # 检索相关记忆
        relevant = await manager.retrieve_relevant(
            query="日志分析",
            max_tokens=4000
        )
    """

    def __init__(
        self,
        working_memory_tokens: int = 8000,
        episodic_memory_tokens: int = 32000,
        semantic_memory_tokens: int = 128000,
        compressor: Optional[MemoryCompressor] = None,
        embedding_func: Optional[Callable[[str], List[float]]] = None,
        state_store: Optional["StateStore"] = None,
    ):
        """
        初始化分层记忆管理器

        Args:
            working_memory_tokens: 工作记忆容量（tokens）
            episodic_memory_tokens: 情景记忆容量（tokens）
            semantic_memory_tokens: 语义记忆容量（tokens）
            compressor: 记忆压缩器
            embedding_func: 嵌入向量生成函数
            state_store: 状态存储（持久化）
        """
        self.token_limits = {
            MemoryLayer.WORKING: working_memory_tokens,
            MemoryLayer.EPISODIC: episodic_memory_tokens,
            MemoryLayer.SEMANTIC: semantic_memory_tokens,
        }

        # 各层记忆存储
        self.memories: Dict[MemoryLayer, List[MemoryEntry]] = {
            MemoryLayer.WORKING: [],
            MemoryLayer.EPISODIC: [],
            MemoryLayer.SEMANTIC: [],
        }

        # ID 索引
        self._id_index: Dict[str, MemoryEntry] = {}

        self.compressor = compressor or SimpleMemoryCompressor()
        self.embedding_func = embedding_func
        self.state_store = state_store

        # 统计信息
        self._stats = MemoryStats()

        logger.info(
            f"[HierarchicalMemory] Initialized with limits: "
            f"working={working_memory_tokens}, episodic={episodic_memory_tokens}, "
            f"semantic={semantic_memory_tokens}"
        )

    async def add_memory(
        self,
        content: str,
        memory_type: MemoryType,
        importance: float = 0.5,
        layer: MemoryLayer = MemoryLayer.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        source_id: Optional[str] = None,
    ) -> str:
        """
        添加记忆

        Args:
            content: 记忆内容
            memory_type: 记忆类型
            importance: 重要性 (0.0-1.0)
            layer: 记忆层级
            metadata: 元数据
            source_id: 来源记忆ID

        Returns:
            记忆ID
        """
        # 创建记忆条目
        entry = MemoryEntry(
            id=str(uuid.uuid4().hex),
            content=content,
            memory_type=memory_type,
            layer=layer,
            importance=max(0.0, min(1.0, importance)),
            metadata=metadata or {},
            source_id=source_id,
        )

        # 生成嵌入向量
        if self.embedding_func:
            try:
                entry.embedding = self.embedding_func(content)
            except Exception as e:
                logger.warning(f"[HierarchicalMemory] Embedding generation failed: {e}")

        # 添加到对应层级
        self.memories[layer].append(entry)
        self._id_index[entry.id] = entry

        # 更新统计
        self._update_stats()

        logger.debug(
            f"[HierarchicalMemory] Added memory {entry.id[:8]} "
            f"type={memory_type.value} layer={layer.value}"
        )

        # 检查是否需要降级
        await self._evict_if_needed(layer)

        return entry.id

    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """获取记忆条目"""
        entry = self._id_index.get(memory_id)
        if entry:
            entry.touch()
        return entry

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """更新记忆条目"""
        entry = self._id_index.get(memory_id)
        if not entry:
            return False

        if content is not None:
            entry.content = content
            entry.token_count = len(content) // 4

        if importance is not None:
            entry.importance = max(0.0, min(1.0, importance))

        if metadata is not None:
            entry.metadata.update(metadata)

        return True

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆条目"""
        entry = self._id_index.pop(memory_id, None)
        if not entry:
            return False

        # 从层级列表中移除
        if entry in self.memories[entry.layer]:
            self.memories[entry.layer].remove(entry)

        self._update_stats()
        return True

    async def retrieve_relevant(
        self,
        query: str,
        max_tokens: int = 4000,
        layers: Optional[List[MemoryLayer]] = None,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> List[MemoryEntry]:
        """
        检索相关记忆

        Args:
            query: 查询字符串
            max_tokens: 最大返回 tokens
            layers: 限定层级
            memory_types: 限定类型

        Returns:
            相关记忆列表
        """
        # 确定搜索层级
        search_layers = layers or list(MemoryLayer)

        # 收集候选记忆
        candidates = []
        for layer in search_layers:
            for entry in self.memories[layer]:
                # 类型过滤
                if memory_types and entry.memory_type not in memory_types:
                    continue
                candidates.append(entry)

        # 计算相关性分数
        now = datetime.now()
        scored_entries = []
        for entry in candidates:
            # 综合分数 = 相关性 * 重要性 * 新鲜度
            relevance = entry.compute_relevance(query)
            recency = entry.compute_recency_score(now)
            score = relevance * 0.5 + entry.importance * 0.3 + recency * 0.2
            scored_entries.append((score, entry))

        # 按分数排序
        scored_entries.sort(key=lambda x: x[0], reverse=True)

        # 按 token 限制截断
        result = []
        current_tokens = 0
        for score, entry in scored_entries:
            entry_tokens = entry.token_count or 0
            if current_tokens + entry_tokens <= max_tokens:
                entry.touch()  # 更新访问时间
                result.append(entry)
                current_tokens += entry_tokens
            else:
                break

        logger.debug(
            f"[HierarchicalMemory] Retrieved {len(result)} memories "
            f"({current_tokens} tokens) for query: {query[:50]}..."
        )

        return result

    async def get_recent(
        self,
        count: int = 10,
        layer: Optional[MemoryLayer] = None,
    ) -> List[MemoryEntry]:
        """获取最近记忆"""
        if layer:
            entries = self.memories[layer]
        else:
            entries = []
            for layer_entries in self.memories.values():
                entries.extend(layer_entries)

        # 按时间排序
        sorted_entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)

        result = sorted_entries[:count]
        for entry in result:
            entry.touch()

        return result

    async def clear_layer(self, layer: MemoryLayer) -> int:
        """清空指定层级的记忆"""
        count = len(self.memories[layer])

        # 从索引中移除
        for entry in self.memories[layer]:
            self._id_index.pop(entry.id, None)

        # 清空列表
        self.memories[layer] = []

        self._update_stats()

        logger.info(f"[HierarchicalMemory] Cleared {count} memories from {layer.value}")
        return count

    async def promote_memory(self, memory_id: str) -> bool:
        """将记忆提升到更高层级"""
        entry = self._id_index.get(memory_id)
        if not entry:
            return False

        prev_layer = entry.layer.prev_layer()
        if not prev_layer:
            return False  # 已经是最高层级

        # 从当前层级移除
        self.memories[entry.layer].remove(entry)

        # 添加到新层级
        entry.layer = prev_layer
        self.memories[prev_layer].append(entry)

        logger.debug(
            f"[HierarchicalMemory] Promoted memory {memory_id[:8]} "
            f"from {entry.layer.value} to {prev_layer.value}"
        )

        return True

    async def demote_memory(self, memory_id: str) -> bool:
        """将记忆降级到更低层级"""
        entry = self._id_index.get(memory_id)
        if not entry:
            return False

        next_layer = entry.layer.next_layer()
        if not next_layer:
            return False  # 已经是最低层级

        # 从当前层级移除
        self.memories[entry.layer].remove(entry)

        # 添加到新层级
        entry.layer = next_layer
        self.memories[next_layer].append(entry)

        logger.debug(
            f"[HierarchicalMemory] Demoted memory {memory_id[:8]} "
            f"from {entry.layer.value} to {next_layer.value}"
        )

        # 检查新层级是否溢出
        await self._evict_if_needed(next_layer)

        return True

    async def _evict_if_needed(self, layer: MemoryLayer) -> None:
        """层级溢出时进行降级或压缩"""
        current_tokens = self._count_tokens(layer)
        limit = self.token_limits[layer]

        if current_tokens <= limit:
            return

        logger.warning(
            f"[HierarchicalMemory] Layer {layer.value} overflow: "
            f"{current_tokens}/{limit} tokens"
        )

        if layer == MemoryLayer.WORKING:
            # 工作记忆 -> 情景记忆
            await self._evict_to_next_layer(layer, current_tokens - limit)

        elif layer == MemoryLayer.EPISODIC:
            # 情景记忆 -> 语义记忆（压缩后）
            await self._evict_to_next_layer(layer, current_tokens - limit)

        else:  # SEMANTIC
            # 语义记忆满了，删除最不重要的
            await self._evict_from_semantic(current_tokens - limit)

    async def _evict_to_next_layer(
        self, layer: MemoryLayer, tokens_to_free: int
    ) -> None:
        """将记忆降级到下一层级"""
        next_layer = layer.next_layer()
        if not next_layer:
            return

        # 按重要性排序，选择要降级的记忆
        entries = sorted(self.memories[layer], key=lambda e: e.importance)

        freed_tokens = 0
        to_move = []

        for entry in entries:
            if freed_tokens >= tokens_to_free:
                break

            freed_tokens += entry.token_count or 0
            to_move.append(entry)

        # 批量压缩后移动
        if to_move:
            try:
                # 尝试压缩
                compressed = await self.compressor.compress(to_move)
                compressed.layer = next_layer

                # 移动到下一层级
                self.memories[next_layer].append(compressed)
                self._id_index[compressed.id] = compressed

                # 从当前层级移除
                for entry in to_move:
                    self.memories[layer].remove(entry)
                    self._id_index.pop(entry.id, None)

                logger.info(
                    f"[HierarchicalMemory] Compressed {len(to_move)} memories "
                    f"from {layer.value} to {next_layer.value}"
                )

            except Exception as e:
                logger.error(f"[HierarchicalMemory] Compression failed: {e}")

                # 降级失败，直接移动
                for entry in to_move:
                    self.memories[layer].remove(entry)
                    entry.layer = next_layer
                    self.memories[next_layer].append(entry)

        # 递归检查下一层级
        await self._evict_if_needed(next_layer)

    async def _evict_from_semantic(self, tokens_to_free: int) -> None:
        """从语义记忆中删除最不重要的条目"""
        entries = sorted(
            self.memories[MemoryLayer.SEMANTIC],
            key=lambda e: (e.importance, e.access_count),
        )

        freed_tokens = 0
        for entry in entries:
            if freed_tokens >= tokens_to_free:
                break

            freed_tokens += entry.token_count or 0
            self.memories[MemoryLayer.SEMANTIC].remove(entry)
            self._id_index.pop(entry.id, None)

        logger.warning(
            f"[HierarchicalMemory] Evicted memories from semantic layer, "
            f"freed {freed_tokens} tokens"
        )

    def _count_tokens(self, layer: MemoryLayer) -> int:
        """计算层级总 tokens"""
        return sum(e.token_count or 0 for e in self.memories[layer])

    def _update_stats(self) -> None:
        """更新统计信息"""
        total_entries = 0
        total_tokens = 0
        layer_counts = {}
        type_counts = {}
        importance_sum = 0.0
        oldest = None
        newest = None

        for layer, entries in self.memories.items():
            layer_counts[layer.value] = len(entries)
            total_entries += len(entries)

            for entry in entries:
                total_tokens += entry.token_count or 0
                importance_sum += entry.importance

                t = entry.memory_type.value
                type_counts[t] = type_counts.get(t, 0) + 1

                if oldest is None or entry.timestamp < oldest:
                    oldest = entry.timestamp
                if newest is None or entry.timestamp > newest:
                    newest = entry.timestamp

        self._stats = MemoryStats(
            total_entries=total_entries,
            total_tokens=total_tokens,
            layer_counts=layer_counts,
            type_counts=type_counts,
            avg_importance=importance_sum / total_entries if total_entries > 0 else 0.0,
            oldest_entry=oldest,
            newest_entry=newest,
        )

    def get_stats(self) -> MemoryStats:
        """获取统计信息"""
        return self._stats

    def get_layer_usage(self) -> Dict[str, Dict[str, Any]]:
        """获取各层级使用情况"""
        usage = {}
        for layer in MemoryLayer:
            current = self._count_tokens(layer)
            limit = self.token_limits[layer]
            usage[layer.value] = {
                "current_tokens": current,
                "limit_tokens": limit,
                "usage_percent": (current / limit * 100) if limit > 0 else 0,
                "entry_count": len(self.memories[layer]),
            }
        return usage

    async def save_state(self) -> bool:
        """保存状态到存储"""
        if not self.state_store:
            return False

        try:
            data = {
                "memories": {
                    layer.value: [e.to_dict() for e in entries]
                    for layer, entries in self.memories.items()
                },
                "stats": self._stats.__dict__,
            }

            await self.state_store.save("hierarchical_memory", data)
            logger.info("[HierarchicalMemory] State saved")
            return True

        except Exception as e:
            logger.error(f"[HierarchicalMemory] Save failed: {e}")
            return False

    async def load_state(self) -> bool:
        """从存储加载状态"""
        if not self.state_store:
            return False

        try:
            data = await self.state_store.load("hierarchical_memory")
            if not data:
                return False

            # 恢复记忆
            for layer_value, entries_data in data.get("memories", {}).items():
                layer = MemoryLayer(layer_value)
                self.memories[layer] = [MemoryEntry.from_dict(e) for e in entries_data]

                # 重建索引
                for entry in self.memories[layer]:
                    self._id_index[entry.id] = entry

            self._update_stats()
            logger.info("[HierarchicalMemory] State loaded")
            return True

        except Exception as e:
            logger.error(f"[HierarchicalMemory] Load failed: {e}")
            return False
