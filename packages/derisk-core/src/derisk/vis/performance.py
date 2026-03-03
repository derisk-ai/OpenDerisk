"""
性能监控和优化系统

提供可视化性能监控、虚拟滚动等高级特性
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    render_count: int = 0
    total_render_time: float = 0.0
    avg_render_time: float = 0.0
    max_render_time: float = 0.0
    min_render_time: float = float('inf')
    
    update_count: int = 0
    total_update_time: float = 0.0
    avg_update_time: float = 0.0
    
    part_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    def record_render(self, duration: float):
        """记录渲染时间"""
        self.render_count += 1
        self.total_render_time += duration
        self.avg_render_time = self.total_render_time / self.render_count
        self.max_render_time = max(self.max_render_time, duration)
        self.min_render_time = min(self.min_render_time, duration)
    
    def record_update(self, duration: float):
        """记录更新时间"""
        self.update_count += 1
        self.total_update_time += duration
        self.avg_update_time = self.total_update_time / self.update_count
    
    def record_cache_hit(self):
        """记录缓存命中"""
        self.cache_hits += 1
    
    def record_cache_miss(self):
        """记录缓存未命中"""
        self.cache_misses += 1
    
    def get_fps(self) -> float:
        """获取FPS"""
        if self.total_render_time > 0:
            return self.render_count / self.total_render_time
        return 0.0
    
    def get_cache_hit_rate(self) -> float:
        """获取缓存命中率"""
        total = self.cache_hits + self.cache_misses
        if total > 0:
            return self.cache_hits / total
        return 0.0


class PerformanceMonitor:
    """
    性能监控器
    
    监控可视化渲染性能
    """
    
    def __init__(self):
        self._metrics = PerformanceMetrics()
        self._render_times: List[float] = []
        self._max_samples = 100
        
        # 性能阈值
        self.fps_warning_threshold = 30  # FPS低于30警告
        self.fps_error_threshold = 15    # FPS低于15错误
    
    def start_render(self) -> float:
        """开始渲染计时"""
        return time.perf_counter()
    
    def end_render(self, start_time: float):
        """结束渲染计时"""
        duration = time.perf_counter() - start_time
        self._metrics.record_render(duration)
        
        # 记录最近N次渲染
        self._render_times.append(duration)
        if len(self._render_times) > self._max_samples:
            self._render_times = self._render_times[-self._max_samples:]
        
        # 检查性能
        fps = self._metrics.get_fps()
        if fps < self.fps_error_threshold:
            logger.error(f"[Performance] FPS过低: {fps:.1f}, 渲染时间: {duration:.3f}s")
        elif fps < self.fps_warning_threshold:
            logger.warning(f"[Performance] FPS警告: {fps:.1f}, 渲染时间: {duration:.3f}s")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return {
            "render": {
                "count": self._metrics.render_count,
                "avg_time": f"{self._metrics.avg_render_time * 1000:.2f}ms",
                "max_time": f"{self._metrics.max_render_time * 1000:.2f}ms",
                "min_time": f"{self._metrics.min_render_time * 1000:.2f}ms" if self._metrics.min_render_time != float('inf') else "N/A",
                "fps": f"{self._metrics.get_fps():.1f}",
            },
            "update": {
                "count": self._metrics.update_count,
                "avg_time": f"{self._metrics.avg_update_time * 1000:.2f}ms",
            },
            "cache": {
                "hits": self._metrics.cache_hits,
                "misses": self._metrics.cache_misses,
                "hit_rate": f"{self._metrics.get_cache_hit_rate() * 100:.1f}%",
            },
            "parts": {
                "count": self._metrics.part_count,
            }
        }
    
    def check_performance(self) -> Dict[str, Any]:
        """检查性能状态"""
        fps = self._metrics.get_fps()
        cache_rate = self._metrics.get_cache_hit_rate()
        
        issues = []
        
        if fps < self.fps_error_threshold:
            issues.append({
                "level": "error",
                "message": f"FPS过低({fps:.1f}),严重影响用户体验",
                "suggestion": "考虑启用虚拟滚动或减少Part数量"
            })
        elif fps < self.fps_warning_threshold:
            issues.append({
                "level": "warning",
                "message": f"FPS较低({fps:.1f}),可能影响用户体验",
                "suggestion": "考虑优化渲染性能"
            })
        
        if cache_rate < 0.5:
            issues.append({
                "level": "warning",
                "message": f"缓存命中率低({cache_rate * 100:.1f}%)",
                "suggestion": "检查Part的UID管理策略"
            })
        
        return {
            "fps": fps,
            "cache_rate": cache_rate,
            "issues": issues,
            "status": "good" if not issues else ("warning" if any(i["level"] == "warning" for i in issues) else "error")
        }


# 全局性能监控器
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


class VirtualScroller:
    """
    虚拟滚动管理器
    
    用于处理大量Part的高效渲染
    """
    
    def __init__(self, viewport_size: int = 20, overscan: int = 5):
        """
        初始化虚拟滚动
        
        Args:
            viewport_size: 视口大小(可见Part数量)
            overscan: 预渲染数量(避免滚动时白屏)
        """
        self.viewport_size = viewport_size
        self.overscan = overscan
        
        self._total_items = 0
        self._scroll_position = 0
        self._visible_range = (0, viewport_size)
    
    def update_scroll_position(self, position: int):
        """
        更新滚动位置
        
        Args:
            position: 当前滚动位置(像素或索引)
        """
        self._scroll_position = position
        self._update_visible_range()
    
    def set_total_items(self, total: int):
        """设置总项目数"""
        self._total_items = total
        self._update_visible_range()
    
    def _update_visible_range(self):
        """更新可见范围"""
        # 计算起始索引
        start = max(0, self._scroll_position - self.overscan)
        
        # 计算结束索引
        end = min(
            self._total_items,
            self._scroll_position + self.viewport_size + self.overscan
        )
        
        self._visible_range = (start, end)
    
    def get_visible_range(self) -> tuple:
        """获取可见范围"""
        return self._visible_range
    
    def get_visible_indices(self) -> List[int]:
        """获取可见索引列表"""
        start, end = self._visible_range
        return list(range(start, end))
    
    def is_item_visible(self, index: int) -> bool:
        """检查项目是否可见"""
        start, end = self._visible_range
        return start <= index < end
    
    def get_scroll_info(self) -> Dict[str, Any]:
        """获取滚动信息"""
        return {
            "total_items": self._total_items,
            "viewport_size": self.viewport_size,
            "scroll_position": self._scroll_position,
            "visible_range": self._visible_range,
            "visible_count": self._visible_range[1] - self._visible_range[0],
        }


class RenderCache:
    """
    渲染缓存
    
    缓存已渲染的Part,避免重复渲染
    """
    
    def __init__(self, max_size: int = 100):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存数量
        """
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size
        self._access_order: List[str] = []
        
        self._monitor = get_performance_monitor()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键(Part UID)
            
        Returns:
            缓存值或None
        """
        if key in self._cache:
            self._monitor._metrics.record_cache_hit()
            
            # 更新访问顺序
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            return self._cache[key]
        
        self._monitor._metrics.record_cache_miss()
        return None
    
    def set(self, key: str, value: Any):
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        # 如果缓存已满,移除最久未使用的
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]
        
        self._cache[key] = value
        
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
    
    def invalidate(self, key: str):
        """失效缓存"""
        if key in self._cache:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._access_order.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_rate": f"{self._monitor._metrics.get_cache_hit_rate() * 100:.1f}%",
        }