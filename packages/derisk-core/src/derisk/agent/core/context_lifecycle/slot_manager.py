"""
Context Slot Manager - 上下文槽位管理器

管理上下文中的所有内容槽位，支持Token预算控制和驱逐策略。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SlotType(str, Enum):
    """槽位类型"""
    SYSTEM = "system"
    SKILL = "skill"
    TOOL = "tool"
    RESOURCE = "resource"
    MEMORY = "memory"


class SlotState(str, Enum):
    """槽位状态"""
    EMPTY = "empty"
    ACTIVE = "active"
    DORMANT = "dormant"
    EVICTED = "evicted"


class EvictionPolicy(str, Enum):
    """驱逐策略"""
    LRU = "lru"
    LFU = "lfu"
    PRIORITY = "priority"
    MANUAL = "manual"


@dataclass
class ContextSlot:
    """上下文槽位"""
    slot_id: str
    slot_type: SlotType
    state: SlotState = SlotState.EMPTY
    
    content: Optional[str] = None
    content_hash: Optional[str] = None
    token_count: int = 0
    
    source_name: Optional[str] = None
    source_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    
    eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    priority: int = 5
    sticky: bool = False
    
    exit_summary: Optional[str] = None
    
    def touch(self) -> None:
        """更新访问时间和计数"""
        self.last_accessed = datetime.now()
        self.access_count += 1
    
    def should_evict(self, policy: EvictionPolicy) -> bool:
        """判断是否应该被驱逐"""
        if self.sticky or self.slot_type == SlotType.SYSTEM:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "slot_id": self.slot_id,
            "slot_type": self.slot_type.value,
            "state": self.state.value,
            "source_name": self.source_name,
            "token_count": self.token_count,
            "priority": self.priority,
            "sticky": self.sticky,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat(),
        }


class ContextSlotManager:
    """
    上下文槽位管理器
    
    核心功能:
    1. 分配和管理上下文槽位
    2. Token预算管理
    3. 驱逐策略执行
    4. 槽位状态追踪
    """
    
    def __init__(
        self,
        max_slots: int = 50,
        token_budget: int = 100000,
        default_eviction_policy: EvictionPolicy = EvictionPolicy.LRU,
    ):
        self._max_slots = max_slots
        self._token_budget = token_budget
        self._default_policy = default_eviction_policy
        
        self._slots: OrderedDict[str, ContextSlot] = OrderedDict()
        self._name_index: Dict[str, str] = {}
        
        self._total_tokens = 0
        self._tokens_by_type: Dict[SlotType, int] = {}
    
    async def allocate(
        self,
        slot_type: SlotType,
        content: str,
        source_name: Optional[str] = None,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        eviction_policy: Optional[EvictionPolicy] = None,
        priority: int = 5,
        sticky: bool = False,
    ) -> ContextSlot:
        """分配槽位"""
        content_tokens = self._estimate_tokens(content)
        
        if self._total_tokens + content_tokens > self._token_budget:
            await self._evict_for_budget(content_tokens)
        
        if len(self._slots) >= self._max_slots:
            await self._evict_for_slots()
        
        slot_id = self._generate_slot_id()
        slot = ContextSlot(
            slot_id=slot_id,
            slot_type=slot_type,
            state=SlotState.ACTIVE,
            content=content,
            content_hash=self._hash_content(content),
            token_count=content_tokens,
            source_name=source_name,
            source_id=source_id,
            metadata=metadata or {},
            eviction_policy=eviction_policy or self._default_policy,
            priority=priority,
            sticky=sticky,
        )
        
        self._slots[slot_id] = slot
        if source_name:
            self._name_index[source_name] = slot_id
        
        self._total_tokens += content_tokens
        self._tokens_by_type[slot_type] = \
            self._tokens_by_type.get(slot_type, 0) + content_tokens
        
        logger.debug(
            f"[SlotManager] Allocated slot {slot_id} "
            f"for {source_name or 'unnamed'}, tokens: {content_tokens}"
        )
        
        return slot
    
    def get_slot(self, slot_id: str) -> Optional[ContextSlot]:
        """获取槽位"""
        slot = self._slots.get(slot_id)
        if slot:
            slot.touch()
        return slot
    
    def get_slot_by_name(
        self,
        name: str,
        slot_type: Optional[SlotType] = None
    ) -> Optional[ContextSlot]:
        """按名称获取槽位"""
        slot_id = self._name_index.get(name)
        if slot_id:
            slot = self._slots.get(slot_id)
            if slot and (slot_type is None or slot.slot_type == slot_type):
                slot.touch()
                return slot
        return None
    
    async def evict(
        self,
        slot_type: Optional[SlotType] = None,
        source_name: Optional[str] = None,
        slot_id: Optional[str] = None,
    ) -> Optional[ContextSlot]:
        """驱逐指定槽位"""
        target_slot = None
        
        if slot_id:
            target_slot = self._slots.get(slot_id)
        elif source_name:
            target_slot = self.get_slot_by_name(source_name, slot_type)
        
        if not target_slot:
            return None
        
        if target_slot.sticky:
            logger.warning(f"[SlotManager] Cannot evict sticky slot: {target_slot.slot_id}")
            return None
        
        return await self._do_evict(target_slot)
    
    async def _do_evict(self, slot: ContextSlot) -> ContextSlot:
        """执行驱逐"""
        self._total_tokens -= slot.token_count
        if slot.slot_type in self._tokens_by_type:
            self._tokens_by_type[slot.slot_type] -= slot.token_count
        
        if slot.source_name:
            self._name_index.pop(slot.source_name, None)
        
        slot.state = SlotState.EVICTED
        evicted_slot = self._slots.pop(slot.slot_id)
        
        logger.info(
            f"[SlotManager] Evicted slot {slot.slot_id} "
            f"({slot.source_name}), freed {slot.token_count} tokens"
        )
        
        return evicted_slot
    
    async def _evict_for_budget(self, required_tokens: int):
        """为预算驱逐"""
        tokens_needed = self._total_tokens + required_tokens - self._token_budget
        
        candidates = [
            s for s in self._slots.values()
            if s.should_evict(self._default_policy)
        ]
        
        candidates.sort(
            key=lambda s: (s.priority, s.last_accessed.timestamp())
        )
        
        freed = 0
        for slot in candidates:
            if freed >= tokens_needed:
                break
            await self._do_evict(slot)
            freed += slot.token_count
    
    async def _evict_for_slots(self):
        """为槽位数量驱逐"""
        candidates = [
            s for s in self._slots.values()
            if s.should_evict(self._default_policy)
        ]
        
        candidates.sort(
            key=lambda s: (s.priority, s.last_accessed.timestamp())
        )
        
        if candidates:
            await self._do_evict(candidates[0])
    
    def update_slot_content(
        self,
        slot_id: str,
        new_content: str,
    ) -> bool:
        """更新槽位内容"""
        slot = self._slots.get(slot_id)
        if not slot:
            return False
        
        old_tokens = slot.token_count
        new_tokens = self._estimate_tokens(new_content)
        
        slot.content = new_content
        slot.content_hash = self._hash_content(new_content)
        slot.token_count = new_tokens
        slot.touch()
        
        self._total_tokens = self._total_tokens - old_tokens + new_tokens
        self._tokens_by_type[slot.slot_type] = \
            self._tokens_by_type.get(slot.slot_type, 0) - old_tokens + new_tokens
        
        return True
    
    def set_slot_dormant(self, source_name: str) -> bool:
        """将槽位设置为休眠状态"""
        slot = self.get_slot_by_name(source_name)
        if slot:
            slot.state = SlotState.DORMANT
            return True
        return False
    
    def reactivate_slot(self, source_name: str) -> Optional[ContextSlot]:
        """重新激活休眠的槽位"""
        slot = self.get_slot_by_name(source_name)
        if slot and slot.state == SlotState.DORMANT:
            slot.state = SlotState.ACTIVE
            slot.touch()
            return slot
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_slots": len(self._slots),
            "max_slots": self._max_slots,
            "total_tokens": self._total_tokens,
            "token_budget": self._token_budget,
            "token_usage_ratio": self._total_tokens / self._token_budget if self._token_budget > 0 else 0,
            "tokens_by_type": {t.value: v for t, v in self._tokens_by_type.items()},
            "slots_by_type": {
                t.value: len([s for s in self._slots.values() if s.slot_type == t])
                for t in SlotType
            },
        }
    
    def list_slots(
        self,
        slot_type: Optional[SlotType] = None,
        state: Optional[SlotState] = None,
    ) -> List[ContextSlot]:
        """列出槽位"""
        result = []
        for slot in self._slots.values():
            if slot_type and slot.slot_type != slot_type:
                continue
            if state and slot.state != state:
                continue
            result.append(slot)
        return result
    
    def clear_all(self, keep_system: bool = True):
        """清除所有槽位"""
        to_remove = []
        for slot_id, slot in self._slots.items():
            if keep_system and slot.slot_type == SlotType.SYSTEM:
                continue
            to_remove.append(slot_id)
        
        for slot_id in to_remove:
            self._slots.pop(slot_id, None)
        
        self._name_index.clear()
        
        if keep_system:
            for slot in self._slots.values():
                if slot.source_name:
                    self._name_index[slot.source_name] = slot.slot_id
        
        self._total_tokens = sum(s.token_count for s in self._slots.values())
        self._tokens_by_type.clear()
        for slot in self._slots.values():
            self._tokens_by_type[slot.slot_type] = \
                self._tokens_by_type.get(slot.slot_type, 0) + slot.token_count
    
    def _estimate_tokens(self, content: str) -> int:
        """估算token数量"""
        return len(content) // 4
    
    def _hash_content(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _generate_slot_id(self) -> str:
        """生成槽位ID"""
        return f"slot_{uuid.uuid4().hex[:8]}"