"""
性能基准测试套件

提供全面的VIS性能测试和基准
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from derisk.vis.parts import (
    PartContainer,
    PartStatus,
    PartType,
    TextPart,
    CodePart,
    ToolUsePart,
)
from derisk.vis.reactive import Signal, Effect, batch

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    name: str
    iterations: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    std_dev: float
    ops_per_second: float
    memory_peak_mb: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_time_ms": self.total_time * 1000,
            "avg_time_ms": self.avg_time * 1000,
            "min_time_ms": self.min_time * 1000,
            "max_time_ms": self.max_time * 1000,
            "std_dev_ms": self.std_dev * 1000,
            "ops_per_second": self.ops_per_second,
            "memory_peak_mb": self.memory_peak_mb,
        }


class PerformanceBenchmark:
    """
    VIS性能基准测试套件
    
    测试项目:
    1. Part创建性能
    2. Part更新性能
    3. 响应式更新性能
    4. 容器操作性能
    5. 序列化性能
    """
    
    def __init__(self):
        self._results: List[BenchmarkResult] = []
    
    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """运行所有基准测试"""
        logger.info("[Benchmark] 开始运行所有性能基准测试...")
        
        # 运行各项测试
        await self.benchmark_part_creation()
        await self.benchmark_part_update()
        await self.benchmark_reactive_updates()
        await self.benchmark_container_operations()
        await self.benchmark_serialization()
        await self.benchmark_large_scale_rendering()
        
        # 汇总结果
        summary = self._generate_summary()
        
        logger.info(f"[Benchmark] 完成! 总计 {len(self._results)} 项测试")
        return summary
    
    async def benchmark_part_creation(
        self,
        iterations: int = 10000
    ) -> BenchmarkResult:
        """
        Part创建性能测试
        
        Args:
            iterations: 迭代次数
        """
        logger.info(f"[Benchmark] Part创建测试: {iterations} 次")
        
        times = []
        
        # TextPart创建
        for _ in range(iterations):
            start = time.perf_counter()
            TextPart.create(content="Hello, World!")
            times.append(time.perf_counter() - start)
        
        result = self._calculate_result("Part创建 (TextPart)", times, iterations)
        self._results.append(result)
        
        return result
    
    async def benchmark_part_update(
        self,
        iterations: int = 10000
    ) -> BenchmarkResult:
        """
        Part更新性能测试
        
        Args:
            iterations: 迭代次数
        """
        logger.info(f"[Benchmark] Part更新测试: {iterations} 次")
        
        # 创建流式Part
        part = TextPart.create(content="", streaming=True)
        
        times = []
        for i in range(iterations):
            start = time.perf_counter()
            part = part.append(f"chunk_{i}")
            times.append(time.perf_counter() - start)
        
        result = self._calculate_result("Part更新 (append)", times, iterations)
        self._results.append(result)
        
        return result
    
    async def benchmark_reactive_updates(
        self,
        iterations: int = 10000
    ) -> BenchmarkResult:
        """
        响应式更新性能测试
        
        Args:
            iterations: 迭代次数
        """
        logger.info(f"[Benchmark] 响应式更新测试: {iterations} 次")
        
        signal = Signal(0)
        
        times = []
        for i in range(iterations):
            start = time.perf_counter()
            signal.value = i
            times.append(time.perf_counter() - start)
        
        result = self._calculate_result("Signal更新", times, iterations)
        self._results.append(result)
        
        return result
    
    async def benchmark_container_operations(
        self,
        iterations: int = 5000
    ) -> Dict[str, BenchmarkResult]:
        """
        容器操作性能测试
        
        Args:
            iterations: 迭代次数
        """
        logger.info(f"[Benchmark] 容器操作测试: {iterations} 次")
        
        results = {}
        
        # 添加操作
        container = PartContainer()
        add_times = []
        for i in range(iterations):
            part = TextPart.create(content=f"Part {i}")
            start = time.perf_counter()
            container.add_part(part)
            add_times.append(time.perf_counter() - start)
        
        results["add"] = self._calculate_result("容器添加", add_times, iterations)
        self._results.append(results["add"])
        
        # 查找操作
        get_times = []
        for part in container:
            start = time.perf_counter()
            container.get_part(part.uid)
            get_times.append(time.perf_counter() - start)
        
        results["get"] = self._calculate_result("容器查找", get_times, iterations)
        self._results.append(results["get"])
        
        return results
    
    async def benchmark_serialization(
        self,
        iterations: int = 5000
    ) -> BenchmarkResult:
        """
        序列化性能测试
        
        Args:
            iterations: 迭代次数
        """
        logger.info(f"[Benchmark] 序列化测试: {iterations} 次")
        
        parts = [
            TextPart.create(content=f"Part {i}")
            for i in range(100)
        ]
        
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            [p.to_vis_dict() for p in parts]
            times.append(time.perf_counter() - start)
        
        result = self._calculate_result("Part序列化 (100个)", times, iterations)
        self._results.append(result)
        
        return result
    
    async def benchmark_large_scale_rendering(
        self,
        part_count: int = 10000
    ) -> BenchmarkResult:
        """
        大规模渲染测试
        
        Args:
            part_count: Part数量
        """
        logger.info(f"[Benchmark] 大规模渲染测试: {part_count} 个Part")
        
        # 创建大量Part
        start = time.perf_counter()
        container = PartContainer()
        for i in range(part_count):
            part = TextPart.create(content=f"Part {i}" * 10)
            container.add_part(part)
        
        creation_time = time.perf_counter() - start
        
        # 序列化
        start = time.perf_counter()
        vis_data = container.to_list()
        serialization_time = time.perf_counter() - start
        
        result = BenchmarkResult(
            name="大规模渲染",
            iterations=part_count,
            total_time=creation_time + serialization_time,
            avg_time=(creation_time + serialization_time) / part_count,
            min_time=0,
            max_time=creation_time,
            std_dev=0,
            ops_per_second=part_count / (creation_time + serialization_time),
        )
        
        self._results.append(result)
        
        logger.info(f"[Benchmark] 大规模渲染: 创建 {creation_time:.3f}s, 序列化 {serialization_time:.3f}s")
        
        return result
    
    def _calculate_result(
        self,
        name: str,
        times: List[float],
        iterations: int
    ) -> BenchmarkResult:
        """计算基准测试结果"""
        total_time = sum(times)
        avg_time = total_time / iterations
        min_time = min(times)
        max_time = max(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0
        ops_per_second = iterations / total_time if total_time > 0 else 0
        
        return BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time=total_time,
            avg_time=avg_time,
            min_time=min_time,
            max_time=max_time,
            std_dev=std_dev,
            ops_per_second=ops_per_second,
        )
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成测试摘要"""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self._results),
            "results": [r.to_dict() for r in self._results],
            "summary": {
                "total_time_ms": sum(r.total_time for r in self._results) * 1000,
                "avg_ops_per_second": statistics.mean([r.ops_per_second for r in self._results]),
            },
            "recommendations": self._generate_recommendations(),
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成性能优化建议"""
        recommendations = []
        
        for result in self._results:
            if result.avg_time > 0.001:  # 大于1ms
                recommendations.append(
                    f"{result.name}: 平均耗时 {result.avg_time * 1000:.2f}ms, "
                    f"建议优化以提升性能"
                )
            
            if result.ops_per_second < 10000:
                recommendations.append(
                    f"{result.name}: 吞吐量 {result.ops_per_second:.0f} ops/s, "
                    f"建议使用批量操作提升性能"
                )
        
        if not recommendations:
            recommendations.append("所有测试性能良好!")
        
        return recommendations


# 预定义的性能基准
PERFORMANCE_TARGETS = {
    "part_creation": {
        "target_ops_per_second": 50000,
        "max_avg_time_ms": 0.05,
    },
    "part_update": {
        "target_ops_per_second": 100000,
        "max_avg_time_ms": 0.01,
    },
    "signal_update": {
        "target_ops_per_second": 200000,
        "max_avg_time_ms": 0.005,
    },
    "container_add": {
        "target_ops_per_second": 100000,
        "max_avg_time_ms": 0.01,
    },
    "serialization": {
        "target_ops_per_second": 10000,
        "max_avg_time_ms": 0.1,
    },
}


async def run_performance_tests():
    """运行性能测试"""
    benchmark = PerformanceBenchmark()
    return await benchmark.run_all_benchmarks()


if __name__ == "__main__":
    asyncio.run(run_performance_tests())