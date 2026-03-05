"""
Part生命周期钩子系统

提供Part创建、更新、删除等生命周期的钩子回调
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from derisk.vis.parts import PartStatus, PartType, VisPart

logger = logging.getLogger(__name__)


class LifecycleEvent(str, Enum):
    """生命周期事件"""
    BEFORE_CREATE = "before_create"
    AFTER_CREATE = "after_create"
    BEFORE_UPDATE = "before_update"
    AFTER_UPDATE = "after_update"
    BEFORE_DELETE = "before_delete"
    AFTER_DELETE = "after_delete"
    ON_STATUS_CHANGE = "on_status_change"
    ON_ERROR = "on_error"
    ON_COMPLETE = "on_complete"


@dataclass
class HookContext:
    """钩子上下文"""
    event: LifecycleEvent
    part: Optional[VisPart] = None
    old_part: Optional[VisPart] = None
    changes: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def prevent_default(self):
        """阻止默认行为"""
        self.metadata["_prevent_default"] = True
    
    def is_prevented(self) -> bool:
        """检查是否被阻止"""
        return self.metadata.get("_prevent_default", False)


class PartHook(ABC):
    """Part生命周期钩子基类"""
    
    @property
    @abstractmethod
    def events(self) -> List[LifecycleEvent]:
        """订阅的事件列表"""
        pass
    
    @abstractmethod
    async def execute(self, context: HookContext) -> None:
        """执行钩子逻辑"""
        pass
    
    @property
    def priority(self) -> int:
        """优先级 (数字越小优先级越高)"""
        return 100
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return True


class LifecycleManager:
    """
    生命周期管理器
    
    管理Part的所有生命周期钩子
    """
    
    def __init__(self):
        self._hooks: Dict[LifecycleEvent, List[PartHook]] = {
            event: [] for event in LifecycleEvent
        }
        self._global_hooks: List[PartHook] = []
    
    def register(self, hook: PartHook):
        """
        注册钩子
        
        Args:
            hook: 钩子实例
        """
        for event in hook.events:
            self._hooks[event].append(hook)
            # 按优先级排序
            self._hooks[event].sort(key=lambda h: h.priority)
        
        logger.info(f"[Lifecycle] 注册钩子: {hook.__class__.__name__}")
    
    def unregister(self, hook: PartHook):
        """
        注销钩子
        
        Args:
            hook: 钩子实例
        """
        for event in hook.events:
            if hook in self._hooks[event]:
                self._hooks[event].remove(hook)
    
    async def trigger(
        self,
        event: LifecycleEvent,
        part: Optional[VisPart] = None,
        old_part: Optional[VisPart] = None,
        changes: Optional[Dict[str, Any]] = None,
        **metadata
    ) -> HookContext:
        """
        触发生命周期事件
        
        Args:
            event: 事件类型
            part: 当前Part
            old_part: 旧的Part
            changes: 变更内容
            **metadata: 额外元数据
            
        Returns:
            钩子上下文
        """
        context = HookContext(
            event=event,
            part=part,
            old_part=old_part,
            changes=changes or {},
            metadata=metadata,
        )
        
        # 执行钩子
        for hook in self._hooks[event]:
            if not hook.enabled:
                continue
            
            try:
                await hook.execute(context)
                
                # 检查是否阻止默认行为
                if context.is_prevented():
                    logger.debug(f"[Lifecycle] 钩子 {hook.__class__.__name__} 阻止了默认行为")
                    break
                    
            except Exception as e:
                logger.error(f"[Lifecycle] 钩子执行失败: {hook.__class__.__name__}, {e}")
        
        return context
    
    def get_hooks(self, event: LifecycleEvent) -> List[PartHook]:
        """获取指定事件的钩子列表"""
        return self._hooks[event]


# 预定义的钩子实现

class LoggingHook(PartHook):
    """日志记录钩子"""
    
    @property
    def events(self) -> List[LifecycleEvent]:
        return [
            LifecycleEvent.AFTER_CREATE,
            LifecycleEvent.AFTER_UPDATE,
            LifecycleEvent.AFTER_DELETE,
        ]
    
    async def execute(self, context: HookContext):
        part = context.part
        if not part:
            return
        
        logger.info(
            f"[Part] {context.event.value}: "
            f"type={part.type}, uid={part.uid}, status={part.status}"
        )


class MetricsHook(PartHook):
    """指标收集钩子"""
    
    def __init__(self):
        self._metrics = {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "errors": 0,
            "completed": 0,
        }
    
    @property
    def events(self) -> List[LifecycleEvent]:
        return [
            LifecycleEvent.AFTER_CREATE,
            LifecycleEvent.AFTER_UPDATE,
            LifecycleEvent.AFTER_DELETE,
            LifecycleEvent.ON_ERROR,
            LifecycleEvent.ON_COMPLETE,
        ]
    
    async def execute(self, context: HookContext):
        if context.event == LifecycleEvent.AFTER_CREATE:
            self._metrics["created"] += 1
        elif context.event == LifecycleEvent.AFTER_UPDATE:
            self._metrics["updated"] += 1
        elif context.event == LifecycleEvent.AFTER_DELETE:
            self._metrics["deleted"] += 1
        elif context.event == LifecycleEvent.ON_ERROR:
            self._metrics["errors"] += 1
        elif context.event == LifecycleEvent.ON_COMPLETE:
            self._metrics["completed"] += 1
    
    def get_metrics(self) -> Dict[str, int]:
        return self._metrics.copy()


class ValidationHook(PartHook):
    """验证钩子"""
    
    @property
    def events(self) -> List[LifecycleEvent]:
        return [
            LifecycleEvent.BEFORE_CREATE,
            LifecycleEvent.BEFORE_UPDATE,
        ]
    
    @property
    def priority(self) -> int:
        return 10  # 高优先级
    
    async def execute(self, context: HookContext):
        part = context.part
        if not part:
            return
        
        # 验证UID
        if not part.uid:
            logger.error("[Validation] Part缺少UID")
            context.prevent_default()
        
        # 验证内容
        if hasattr(part, 'content') and part.content:
            # 检查内容长度
            if len(part.content) > 1000000:  # 1MB
                logger.warning(f"[Validation] Part内容过长: {len(part.content)} bytes")


class CacheHook(PartHook):
    """缓存钩子"""
    
    def __init__(self):
        self._cache: Dict[str, VisPart] = {}
    
    @property
    def events(self) -> List[LifecycleEvent]:
        return [
            LifecycleEvent.AFTER_CREATE,
            LifecycleEvent.AFTER_UPDATE,
            LifecycleEvent.AFTER_DELETE,
        ]
    
    async def execute(self, context: HookContext):
        part = context.part
        if not part:
            return
        
        if context.event == LifecycleEvent.AFTER_DELETE:
            # 删除缓存
            if part.uid in self._cache:
                del self._cache[part.uid]
        else:
            # 更新缓存
            self._cache[part.uid] = part
    
    def get_cached(self, uid: str) -> Optional[VisPart]:
        """获取缓存的Part"""
        return self._cache.get(uid)


class AutoSaveHook(PartHook):
    """自动保存钩子"""
    
    def __init__(self, save_callback: Callable[[VisPart], None]):
        """
        初始化
        
        Args:
            save_callback: 保存回调函数
        """
        self._save_callback = save_callback
    
    @property
    def events(self) -> List[LifecycleEvent]:
        return [
            LifecycleEvent.ON_COMPLETE,
            LifecycleEvent.ON_ERROR,
        ]
    
    @property
    def priority(self) -> int:
        return 1000  # 低优先级,最后执行
    
    async def execute(self, context: HookContext):
        part = context.part
        if part:
            self._save_callback(part)


# 装饰器方式注册钩子

def lifecycle_hook(*events: LifecycleEvent, priority: int = 100):
    """
    钩子装饰器
    
    Args:
        *events: 订阅的事件
        priority: 优先级
    """
    def decorator(func: Callable):
        class FunctionHook(PartHook):
            @property
            def events(self) -> List[LifecycleEvent]:
                return list(events)
            
            @property
            def priority(self) -> int:
                return priority
            
            async def execute(self, context: HookContext):
                await func(context)
        
        # 创建钩子实例并注册
        hook = FunctionHook()
        get_lifecycle_manager().register(hook)
        
        return func
    
    return decorator


# 全局生命周期管理器
_lifecycle_manager: Optional[LifecycleManager] = None


def get_lifecycle_manager() -> LifecycleManager:
    """获取全局生命周期管理器"""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = LifecycleManager()
        
        # 注册默认钩子
        _lifecycle_manager.register(LoggingHook())
        _lifecycle_manager.register(MetricsHook())
        _lifecycle_manager.register(ValidationHook())
    
    return _lifecycle_manager