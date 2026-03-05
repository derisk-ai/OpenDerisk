"""
可视化调试工具

提供Part系统运行时的可视化调试和诊断能力
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from derisk.vis.parts import PartContainer, PartStatus, PartType, VisPart
from derisk.vis.reactive import Signal, Effect, Computed

logger = logging.getLogger(__name__)


@dataclass
class DebugEvent:
    """调试事件"""
    timestamp: datetime
    event_type: str
    source: str
    data: Dict[str, Any]
    duration_ms: Optional[float] = None


class VISDebugger:
    """
    VIS可视化调试器
    
    功能:
    1. 事件追踪 - 记录所有VIS相关事件
    2. 状态快照 - 捕获Part容器状态
    3. 性能分析 - 识别性能瓶颈
    4. 依赖可视化 - 展示Signal依赖关系
    5. 时间旅行 - 回放状态变化
    """
    
    def __init__(self, max_events: int = 10000):
        """
        初始化调试器
        
        Args:
            max_events: 最大事件记录数
        """
        self.max_events = max_events
        self._events: List[DebugEvent] = []
        self._snapshots: List[Dict[str, Any]] = []
        self._signal_registry: Dict[int, Signal] = {}
        self._effect_registry: Dict[int, Effect] = {}
        self._enabled = False
        self._event_counts: Dict[str, int] = defaultdict(int)
    
    def enable(self):
        """启用调试模式"""
        self._enabled = True
        logger.info("[Debugger] 调试模式已启用")
    
    def disable(self):
        """禁用调试模式"""
        self._enabled = False
        logger.info("[Debugger] 调试模式已禁用")
    
    def is_enabled(self) -> bool:
        """检查调试模式是否启用"""
        return self._enabled
    
    def record_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        duration_ms: Optional[float] = None
    ):
        """
        记录调试事件
        
        Args:
            event_type: 事件类型
            source: 事件来源
            data: 事件数据
            duration_ms: 持续时间(毫秒)
        """
        if not self._enabled:
            return
        
        event = DebugEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            source=source,
            data=data,
            duration_ms=duration_ms,
        )
        
        self._events.append(event)
        self._event_counts[event_type] += 1
        
        # 限制事件数量
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events:]
    
    def capture_snapshot(
        self,
        container: PartContainer,
        label: Optional[str] = None
    ) -> str:
        """
        捕获状态快照
        
        Args:
            container: Part容器
            label: 快照标签
            
        Returns:
            快照ID
        """
        snapshot_id = f"snapshot_{len(self._snapshots)}"
        
        snapshot = {
            "id": snapshot_id,
            "label": label or snapshot_id,
            "timestamp": datetime.now().isoformat(),
            "part_count": len(container),
            "parts": [
                {
                    "uid": p.uid,
                    "type": p.type.value if hasattr(p.type, 'value') else str(p.type),
                    "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
                    "content_length": len(p.content) if p.content else 0,
                }
                for p in container
            ],
            "statistics": {
                "by_type": self._count_by_type(container),
                "by_status": self._count_by_status(container),
            },
        }
        
        self._snapshots.append(snapshot)
        self.record_event("snapshot", "debugger", {"snapshot_id": snapshot_id})
        
        return snapshot_id
    
    def _count_by_type(self, container: PartContainer) -> Dict[str, int]:
        """按类型统计"""
        counts = defaultdict(int)
        for part in container:
            type_name = part.type.value if hasattr(part.type, 'value') else str(part.type)
            counts[type_name] += 1
        return dict(counts)
    
    def _count_by_status(self, container: PartContainer) -> Dict[str, int]:
        """按状态统计"""
        counts = defaultdict(int)
        for part in container:
            status_name = part.status.value if hasattr(part.status, 'value') else str(part.status)
            counts[status_name] += 1
        return dict(counts)
    
    def register_signal(self, signal: Signal, name: Optional[str] = None):
        """
        注册Signal到调试器
        
        Args:
            signal: Signal实例
            name: Signal名称
        """
        signal_id = id(signal)
        self._signal_registry[signal_id] = signal
        
        self.record_event(
            "signal_register",
            "debugger",
            {"signal_id": signal_id, "name": name}
        )
    
    def register_effect(self, effect: Effect, name: Optional[str] = None):
        """
        注册Effect到调试器
        
        Args:
            effect: Effect实例
            name: Effect名称
        """
        effect_id = id(effect)
        self._effect_registry[effect_id] = effect
        
        self.record_event(
            "effect_register",
            "debugger",
            {"effect_id": effect_id, "name": name}
        )
    
    def analyze_dependencies(self) -> Dict[str, Any]:
        """
        分析Signal-Effect依赖关系
        
        Returns:
            依赖关系图
        """
        graph = {
            "signals": [],
            "effects": [],
            "dependencies": [],
        }
        
        for signal_id, signal in self._signal_registry.items():
            graph["signals"].append({
                "id": signal_id,
                "value": str(signal.value)[:100],  # 限制长度
            })
        
        for effect_id, effect in self._effect_registry.items():
            deps = []
            for dep in effect.dependencies:
                dep_id = id(dep)
                deps.append(dep_id)
                graph["dependencies"].append({
                    "from": dep_id,
                    "to": effect_id,
                })
            
            graph["effects"].append({
                "id": effect_id,
                "dependencies": deps,
            })
        
        return graph
    
    def identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """
        识别性能瓶颈
        
        Returns:
            瓶颈列表
        """
        bottlenecks = []
        
        # 分析慢事件
        slow_events = [
            e for e in self._events
            if e.duration_ms and e.duration_ms > 100  # 超过100ms
        ]
        
        for event in slow_events:
            bottlenecks.append({
                "type": "slow_event",
                "event_type": event.event_type,
                "source": event.source,
                "duration_ms": event.duration_ms,
                "timestamp": event.timestamp.isoformat(),
            })
        
        # 分析高频事件
        for event_type, count in self._event_counts.items():
            if count > 1000:  # 超过1000次
                bottlenecks.append({
                    "type": "high_frequency",
                    "event_type": event_type,
                    "count": count,
                    "recommendation": f"考虑批量处理 {event_type} 事件",
                })
        
        return bottlenecks
    
    def time_travel_to(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        时间旅行到指定快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            快照数据
        """
        for snapshot in self._snapshots:
            if snapshot["id"] == snapshot_id:
                return snapshot
        return None
    
    def get_event_timeline(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取事件时间线
        
        Args:
            limit: 限制数量
            
        Returns:
            事件列表
        """
        events = self._events[-limit:]
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "type": e.event_type,
                "source": e.source,
                "duration_ms": e.duration_ms,
                "data_summary": {k: str(v)[:50] for k, v in e.data.items()},
            }
            for e in events
        ]
    
    def export_debug_info(self) -> Dict[str, Any]:
        """
        导出完整调试信息
        
        Returns:
            调试信息字典
        """
        return {
            "enabled": self._enabled,
            "event_count": len(self._events),
            "snapshot_count": len(self._snapshots),
            "signal_count": len(self._signal_registry),
            "effect_count": len(self._effect_registry),
            "event_counts": dict(self._event_counts),
            "bottlenecks": self.identify_bottlenecks(),
            "recent_events": self.get_event_timeline(50),
            "snapshots": self._snapshots[-10:],  # 最近10个快照
            "dependencies": self.analyze_dependencies(),
        }
    
    def clear(self):
        """清空调试数据"""
        self._events.clear()
        self._snapshots.clear()
        self._event_counts.clear()
        logger.info("[Debugger] 调试数据已清空")


# 全局调试器实例
_debugger: Optional[VISDebugger] = None


def get_debugger() -> VISDebugger:
    """获取全局调试器实例"""
    global _debugger
    if _debugger is None:
        _debugger = VISDebugger()
    return _debugger


def enable_debug():
    """启用调试模式"""
    get_debugger().enable()


def disable_debug():
    """禁用调试模式"""
    get_debugger().disable()