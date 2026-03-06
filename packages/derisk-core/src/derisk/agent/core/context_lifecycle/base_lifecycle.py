"""
Base Lifecycle Manager - 通用生命周期管理基类

提供可复用的生命周期管理模式，支持快速扩展新的内容类型。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from .slot_manager import (
    ContextSlot,
    ContextSlotManager,
    EvictionPolicy,
    SlotState,
    SlotType,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ExitTrigger(str, Enum):
    """通用退出触发器"""
    COMPLETE = "complete"
    ERROR = "error"
    TIMEOUT = "timeout"
    MANUAL = "manual"
    PRESSURE = "pressure"
    REPLACEMENT = "replacement"


@dataclass
class ExitResult(Generic[T]):
    """通用退出结果"""
    name: str
    trigger: ExitTrigger
    summary: str
    tokens_freed: int = 0
    data: Optional[T] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentManifest(Generic[T]):
    """通用内容清单"""
    name: str
    content_type: SlotType
    description: str = ""
    priority: int = 5
    auto_load: bool = False
    auto_exit: bool = True
    sticky: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseLifecycleManager(ABC, Generic[T]):
    """
    生命周期管理基类
    
    提供统一的生命周期管理模式：
    - 加载/激活
    - 退出/卸载
    - 休眠/恢复
    - 使用统计
    
    扩展新类型只需实现：
    1. _create_compact_representation() - 压缩表示
    2. _generate_summary() - 生成摘要
    """
    
    def __init__(
        self,
        slot_manager: ContextSlotManager,
        slot_type: SlotType,
        content_type_name: str,
        max_active: int = 10,
        eviction_policy: EvictionPolicy = EvictionPolicy.LRU,
    ):
        self._slot_manager = slot_manager
        self._slot_type = slot_type
        self._content_type_name = content_type_name
        self._max_active = max_active
        self._eviction_policy = eviction_policy
        
        self._active: Dict[str, ContextSlot] = {}
        self._dormant: Dict[str, ContextSlot] = {}
        self._history: List[ExitResult] = []
        self._manifests: Dict[str, ContentManifest] = {}
        self._usage_stats: Dict[str, int] = {}
    
    def register_manifest(self, manifest: ContentManifest) -> None:
        """注册内容清单"""
        self._manifests[manifest.name] = manifest
        logger.debug(f"[{self._content_type_name}] Registered: {manifest.name}")
    
    async def load(
        self,
        name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextSlot:
        """加载内容到上下文"""
        if name in self._active:
            slot = self._active[name]
            slot.touch()
            return slot
        
        if name in self._dormant:
            return await self._reactivate(name)
        
        if len(self._active) >= self._max_active:
            await self._evict_lru()
        
        manifest = self._manifests.get(name)
        priority = manifest.priority if manifest else 5
        sticky = manifest.sticky if manifest else False
        
        slot = await self._slot_manager.allocate(
            slot_type=self._slot_type,
            content=content,
            source_name=name,
            metadata=metadata or {},
            eviction_policy=self._eviction_policy,
            priority=priority,
            sticky=sticky,
        )
        
        self._active[name] = slot
        logger.info(
            f"[{self._content_type_name}] Loaded: {name}, "
            f"active: {len(self._active)}/{self._max_active}"
        )
        
        return slot
    
    async def activate(self, name: str) -> Optional[ContextSlot]:
        """激活休眠的内容"""
        return await self._reactivate(name)
    
    async def _reactivate(self, name: str) -> Optional[ContextSlot]:
        """重新激活"""
        if name not in self._dormant:
            return None
        
        if len(self._active) >= self._max_active:
            await self._evict_lru()
        
        slot = self._dormant.pop(name)
        slot.state = SlotState.ACTIVE
        slot.touch()
        self._active[name] = slot
        
        logger.info(f"[{self._content_type_name}] Reactivated: {name}")
        return slot
    
    async def exit(
        self,
        name: str,
        trigger: ExitTrigger = ExitTrigger.COMPLETE,
        summary: Optional[str] = None,
        key_outputs: Optional[List[str]] = None,
    ) -> ExitResult:
        """退出并压缩"""
        if name not in self._active:
            return ExitResult(
                name=name,
                trigger=trigger,
                summary="Not active",
            )
        
        slot = self._active.pop(name)
        
        if not summary:
            summary = self._generate_summary(slot)
        
        compact_content = self._create_compact_representation(
            name=name,
            summary=summary,
            key_outputs=key_outputs or [],
        )
        
        tokens_freed = slot.token_count - len(compact_content) // 4
        
        slot.content = compact_content
        slot.token_count = len(compact_content) // 4
        slot.state = SlotState.DORMANT
        slot.exit_summary = summary
        
        self._slot_manager.update_slot_content(slot.slot_id, compact_content)
        self._dormant[name] = slot
        
        result = ExitResult(
            name=name,
            trigger=trigger,
            summary=summary,
            tokens_freed=max(0, tokens_freed),
            metadata={"key_outputs": key_outputs or []},
        )
        self._history.append(result)
        
        logger.info(
            f"[{self._content_type_name}] Exited: {name}, "
            f"tokens freed: {tokens_freed}"
        )
        
        return result
    
    async def unload(self, name: str) -> bool:
        """完全卸载"""
        if name in self._active:
            self._active.pop(name)
        if name in self._dormant:
            self._dormant.pop(name)
        
        result = await self._slot_manager.evict(
            slot_type=self._slot_type,
            source_name=name,
        )
        
        if result:
            logger.info(f"[{self._content_type_name}] Unloaded: {name}")
            return True
        return False
    
    def record_usage(self, name: str) -> None:
        """记录使用"""
        self._usage_stats[name] = self._usage_stats.get(name, 0) + 1
    
    async def _evict_lru(self) -> Optional[ExitResult]:
        """驱逐LRU"""
        if not self._active:
            return None
        
        lru_name = min(
            self._active.items(),
            key=lambda x: x[1].last_accessed.timestamp()
        )[0]
        
        manifest = self._manifests.get(lru_name)
        should_exit = manifest.auto_exit if manifest else True
        
        if should_exit:
            return await self.exit(
                name=lru_name,
                trigger=ExitTrigger.PRESSURE,
            )
        else:
            await self.unload(lru_name)
            return ExitResult(
                name=lru_name,
                trigger=ExitTrigger.PRESSURE,
                summary="Evicted without compression",
            )
    
    @abstractmethod
    def _create_compact_representation(
        self,
        name: str,
        summary: str,
        key_outputs: List[str],
    ) -> str:
        """创建压缩表示"""
        pass
    
    @abstractmethod
    def _generate_summary(self, slot: ContextSlot) -> str:
        """生成摘要"""
        pass
    
    def get_active(self) -> List[str]:
        """获取活跃列表"""
        return list(self._active.keys())
    
    def get_dormant(self) -> List[str]:
        """获取休眠列表"""
        return list(self._dormant.keys())
    
    def get_history(self) -> List[ExitResult]:
        """获取历史"""
        return self._history.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "content_type": self._content_type_name,
            "active_count": len(self._active),
            "dormant_count": len(self._dormant),
            "max_active": self._max_active,
            "total_manifests": len(self._manifests),
            "total_exits": len(self._history),
            "active_items": list(self._active.keys()),
            "usage_stats": dict(sorted(
                self._usage_stats.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
        }