"""
响应式状态管理系统

提供类似SolidJS Signals的响应式能力
支持自动依赖追踪和状态变更通知
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Generic, List, Optional, Set, TypeVar, Union
from weakref import WeakSet

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Effect:
    """
    副作用 - 自动追踪依赖并在变化时重新执行
    
    示例:
        name = Signal("Alice")
        
        effect = Effect(lambda: print(f"Hello, {name.value}!"))
        # 输出: Hello, Alice!
        
        name.value = "Bob"
        # 自动输出: Hello, Bob!
    """
    
    _current_effect: Optional["Effect"] = None
    
    def __init__(self, fn: Callable[[], None]):
        self.fn = fn
        self.dependencies: Set[Signal] = set()
        self._disposed = False
        
        # 立即执行一次,收集依赖
        self._execute()
    
    def _execute(self):
        """执行副作用并收集依赖"""
        if self._disposed:
            return
        
        # 清除旧依赖
        old_deps = self.dependencies.copy()
        self.dependencies.clear()
        
        # 设置当前effect为this
        prev_effect = Effect._current_effect
        Effect._current_effect = self
        
        try:
            # 执行函数
            self.fn()
        except Exception as e:
            logger.error(f"Effect执行失败: {e}", exc_info=True)
        finally:
            Effect._current_effect = prev_effect
        
        # 取消订阅不再依赖的Signal
        for dep in old_deps:
            if dep not in self.dependencies:
                dep._unsubscribe(self)
        
        # 订阅新依赖
        for dep in self.dependencies:
            dep._subscribe(self)
    
    def _track(self, signal: "Signal"):
        """追踪Signal依赖"""
        self.dependencies.add(signal)
    
    def dispose(self):
        """释放资源"""
        if self._disposed:
            return
        
        self._disposed = True
        
        # 取消所有订阅
        for dep in self.dependencies:
            dep._unsubscribe(self)
        
        self.dependencies.clear()


class Signal(Generic[T]):
    """
    Signal - 响应式状态容器
    
    类似SolidJS的Signal,提供响应式状态管理:
    - 自动依赖追踪
    - 状态变更通知
    - 支持计算属性(Computed)
    
    示例:
        count = Signal(0)
        
        # 创建副作用
        effect = Effect(lambda: print(f"Count: {count.value}"))
        # 输出: Count: 0
        
        # 更新状态,自动触发副作用
        count.value = 1
        # 输出: Count: 1
        
        # 批量更新
        with batch():
            count.value = 2
            count.value = 3  # 只触发一次更新
    """
    
    def __init__(self, initial_value: T):
        self._value: T = initial_value
        self._subscribers: WeakSet[Effect] = WeakSet()
        self._async_subscribers: List[Callable[[T], None]] = []
        self._batch_depth = 0
        self._pending_value: Optional[T] = None
    
    @property
    def value(self) -> T:
        """获取当前值"""
        # 自动追踪依赖
        if Effect._current_effect is not None:
            Effect._current_effect._track(self)
        
        return self._value
    
    @value.setter
    def value(self, new_value: T):
        """设置新值"""
        if self._value == new_value:
            return
        
        # 批量更新模式
        if self._batch_depth > 0:
            self._pending_value = new_value
            return
        
        self._value = new_value
        self._notify_subscribers()
    
    def _subscribe(self, effect: Effect):
        """订阅effect"""
        self._subscribers.add(effect)
    
    def _unsubscribe(self, effect: Effect):
        """取消订阅"""
        self._subscribers.discard(effect)
    
    def subscribe(self, callback: Callable[[T], None]):
        """
        订阅值变化(用于异步回调)
        
        Args:
            callback: 回调函数,接收新值
        """
        self._async_subscribers.append(callback)
        return lambda: self._async_subscribers.remove(callback)
    
    async def subscribe_async(self, callback: Callable[[T], Any]):
        """
        订阅值变化(异步回调)
        
        Args:
            callback: 异步回调函数
        """
        def wrapper(value: T):
            asyncio.create_task(callback(value))
        
        return self.subscribe(wrapper)
    
    def _notify_subscribers(self):
        """通知所有订阅者"""
        # 通知Effect订阅者
        for effect in list(self._subscribers):
            try:
                effect._execute()
            except Exception as e:
                logger.error(f"通知Effect失败: {e}", exc_info=True)
        
        # 通知异步订阅者
        for callback in self._async_subscribers:
            try:
                callback(self._value)
            except Exception as e:
                logger.error(f"通知订阅者失败: {e}", exc_info=True)
    
    def update(self, fn: Callable[[T], T]):
        """
        使用函数更新值
        
        Args:
            fn: 转换函数,接收旧值,返回新值
        """
        self.value = fn(self._value)
    
    def __enter__(self):
        """进入批量更新模式"""
        self._batch_depth += 1
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出批量更新模式"""
        self._batch_depth -= 1
        
        if self._batch_depth == 0 and self._pending_value is not None:
            value = self._pending_value
            self._pending_value = None
            self.value = value
        
        return False


class Computed(Generic[T]):
    """
    Computed - 计算属性
    
    基于其他Signal自动计算值,具有缓存特性
    
    示例:
        first_name = Signal("John")
        last_name = Signal("Doe")
        
        full_name = Computed(lambda: f"{first_name.value} {last_name.value}")
        
        print(full_name.value)  # "John Doe"
        
        first_name.value = "Jane"
        print(full_name.value)  # "Jane Doe" (自动重新计算)
    """
    
    def __init__(self, fn: Callable[[], T]):
        self._fn = fn
        self._cached_value: Optional[T] = None
        self._dirty = True
        self._signal = Signal(None)
        
        # 创建Effect追踪依赖
        self._effect = Effect(self._recompute)
    
    def _recompute(self):
        """重新计算值"""
        self._dirty = True
        self._signal.value = None  # 触发通知
    
    @property
    def value(self) -> T:
        """获取计算值"""
        if self._dirty:
            self._cached_value = self._fn()
            self._dirty = False
        
        return self._cached_value
    
    def dispose(self):
        """释放资源"""
        self._effect.dispose()


class BatchManager:
    """
    批量更新管理器
    
    用于批量更新多个Signal,避免多次触发副作用
    
    示例:
        a = Signal(1)
        b = Signal(2)
        
        with batch():
            a.value = 10
            b.value = 20
            # 所有更新在退出时统一触发
    """
    
    _depth = 0
    _pending_signals: Set[Signal] = set()
    
    @classmethod
    def enter(cls):
        """进入批量更新"""
        cls._depth += 1
    
    @classmethod
    def exit(cls):
        """退出批量更新"""
        cls._depth -= 1
        
        if cls._depth == 0:
            # 触发所有pending的Signal
            signals = cls._pending_signals.copy()
            cls._pending_signals.clear()
            
            for signal in signals:
                signal._notify_subscribers()
    
    @classmethod
    def track_signal(cls, signal: Signal):
        """追踪需要更新的Signal"""
        if cls._depth > 0:
            cls._pending_signals.add(signal)
            return True
        return False


def batch():
    """
    批量更新上下文管理器
    
    示例:
        with batch():
            signal1.value = 1
            signal2.value = 2
    """
    return _BatchContext()


class _BatchContext:
    """批量更新上下文"""
    
    def __enter__(self):
        BatchManager.enter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        BatchManager.exit()
        return False


class ReactiveDict(Generic[T]):
    """
    响应式字典 - 每个key对应一个Signal
    
    示例:
        state = ReactiveDict({"count": 0, "name": "Alice"})
        
        Effect(lambda: print(f"Count: {state.get('count')}"))
        
        state.set("count", 1)  # 触发副作用
    """
    
    def __init__(self, initial: Optional[dict] = None):
        self._signals: dict = {}
        
        if initial:
            for key, value in initial.items():
                self._signals[key] = Signal(value)
    
    def get(self, key: str, default: T = None) -> T:
        """获取值"""
        if key not in self._signals:
            return default
        return self._signals[key].value
    
    def set(self, key: str, value: T):
        """设置值"""
        if key not in self._signals:
            self._signals[key] = Signal(value)
        else:
            self._signals[key].value = value
    
    def delete(self, key: str):
        """删除key"""
        if key in self._signals:
            del self._signals[key]
    
    def keys(self):
        """获取所有key"""
        return self._signals.keys()
    
    def values(self):
        """获取所有值"""
        return [s.value for s in self._signals.values()]
    
    def items(self):
        """获取所有键值对"""
        return [(k, s.value) for k, s in self._signals.items()]
    
    def subscribe(self, key: str, callback: Callable[[T], None]):
        """
        订阅特定key的变化
        
        Args:
            key: 要订阅的key
            callback: 回调函数
            
        Returns:
            取消订阅函数
        """
        if key not in self._signals:
            self._signals[key] = Signal(None)
        
        return self._signals[key].subscribe(callback)
    
    def to_dict(self) -> dict:
        """转换为普通字典"""
        return {k: s.value for k, s in self._signals.items()}


class ReactiveList(Generic[T]):
    """
    响应式列表 - 支持响应式操作
    
    示例:
        items = ReactiveList([1, 2, 3])
        
        Effect(lambda: print(f"Length: {len(items)}"))
        
        items.append(4)  # 触发副作用
    """
    
    def __init__(self, initial: Optional[List[T]] = None):
        self._items: List[T] = initial or []
        self._change_signal = Signal(0)
    
    def __len__(self) -> int:
        Effect._current_effect and Effect._current_effect._track(self._change_signal)
        return len(self._items)
    
    def __getitem__(self, index: int) -> T:
        return self._items[index]
    
    def __setitem__(self, index: int, value: T):
        self._items[index] = value
        self._change_signal.value += 1
    
    def append(self, item: T):
        """添加元素"""
        self._items.append(item)
        self._change_signal.value += 1
    
    def remove(self, item: T):
        """移除元素"""
        self._items.remove(item)
        self._change_signal.value += 1
    
    def pop(self, index: int = -1) -> T:
        """弹出元素"""
        item = self._items.pop(index)
        self._change_signal.value += 1
        return item
    
    def clear(self):
        """清空列表"""
        self._items.clear()
        self._change_signal.value += 1
    
    def to_list(self) -> List[T]:
        """转换为普通列表"""
        return self._items.copy()
    
    def __iter__(self):
        return iter(self._items)