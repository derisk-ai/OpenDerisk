"""
Smart Checkpoint Manager - 智能检查点管理

实现自适应检查点策略，提供：
- 时间驱动检查点
- 步数驱动检查点
- 里程碑驱动检查点
- 自适应检查点（根据失败率动态调整）

此模块实现 P1 改进方案。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import pickle
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .state_machine import AgentState

logger = logging.getLogger(__name__)


class CheckpointStrategy(str, Enum):
    """检查点策略"""

    TIME_BASED = "time_based"  # 时间驱动
    STEP_BASED = "step_based"  # 步数驱动
    MILESTONE_BASED = "milestone"  # 里程碑驱动
    ADAPTIVE = "adaptive"  # 自适应


class CheckpointType(str, Enum):
    """检查点类型"""

    MANUAL = "manual"  # 手动检查点
    AUTOMATIC = "automatic"  # 自动检查点
    TASK_START = "task_start"  # 任务开始
    TASK_END = "task_end"  # 任务结束
    ERROR = "error"  # 错误时检查点
    MILESTONE = "milestone"  # 里程碑检查点
    STATE_CHANGE = "state_change"  # 状态变化时


@dataclass
class Checkpoint:
    """检查点"""

    checkpoint_id: str
    execution_id: str
    checkpoint_type: CheckpointType
    timestamp: datetime = field(default_factory=datetime.now)

    state: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    step_index: int = 0
    message: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)
    checksum: Optional[str] = None

    # 版本控制
    version: int = 1
    parent_checkpoint_id: Optional[str] = None

    # 压缩相关
    compressed: bool = False
    original_size: Optional[int] = None

    def compute_checksum(self) -> str:
        """计算校验和"""
        data = json.dumps(
            {
                "state": self.state,
                "context": self.context,
                "step_index": self.step_index,
                "version": self.version,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def validate(self) -> bool:
        """验证检查点完整性"""
        if not self.checksum:
            return True  # 无校验和，默认有效
        return self.checksum == self.compute_checksum()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "execution_id": self.execution_id,
            "checkpoint_type": self.checkpoint_type.value,
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "context": self.context,
            "step_index": self.step_index,
            "message": self.message,
            "metadata": self.metadata,
            "checksum": self.checksum,
            "version": self.version,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "compressed": self.compressed,
            "original_size": self.original_size,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """从字典创建"""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            execution_id=data["execution_id"],
            checkpoint_type=CheckpointType(data["checkpoint_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            state=data["state"],
            context=data["context"],
            step_index=data["step_index"],
            message=data.get("message"),
            metadata=data.get("metadata", {}),
            checksum=data.get("checksum"),
            version=data.get("version", 1),
            parent_checkpoint_id=data.get("parent_checkpoint_id"),
            compressed=data.get("compressed", False),
            original_size=data.get("original_size"),
        )


class CheckpointError(Exception):
    """检查点错误基类"""

    pass


class CheckpointNotFoundError(CheckpointError):
    """检查点未找到"""

    pass


class CheckpointCorruptedError(CheckpointError):
    """检查点损坏"""

    pass


class StateStore(ABC):
    """状态存储抽象基类"""

    @abstractmethod
    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存数据"""
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载数据"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除数据"""
        pass

    @abstractmethod
    async def list_keys(self, prefix: str) -> List[str]:
        """列出指定前缀的所有键"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        pass


class FileStateStore(StateStore):
    """文件系统状态存储"""

    def __init__(
        self,
        base_dir: str = ".agent_state",
        compress: bool = True,
        encryption_key: Optional[str] = None,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.compress = compress
        self.encryption_key = encryption_key

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存数据到文件"""
        try:
            file_path = self.base_dir / f"{key}.json"
            content = json.dumps(data, default=str, indent=2)

            if self.compress:
                content = gzip.compress(content.encode())
                file_path = self.base_dir / f"{key}.json.gz"

            if isinstance(content, bytes):
                file_path.write_bytes(content)
            else:
                file_path.write_text(content)

            return True
        except Exception as e:
            logger.error(f"[FileStateStore] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """从文件加载数据"""
        try:
            # 尝试压缩文件
            compressed_path = self.base_dir / f"{key}.json.gz"
            if compressed_path.exists():
                content = gzip.decompress(compressed_path.read_bytes())
                return json.loads(content.decode())

            # 尝试普通文件
            file_path = self.base_dir / f"{key}.json"
            if file_path.exists():
                return json.loads(file_path.read_text())

            return None
        except Exception as e:
            logger.error(f"[FileStateStore] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """删除文件"""
        try:
            for ext in [".json", ".json.gz"]:
                file_path = self.base_dir / f"{key}{ext}"
                if file_path.exists():
                    file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"[FileStateStore] Delete failed: {e}")
            return False

    async def list_keys(self, prefix: str) -> List[str]:
        """列出所有匹配前缀的键"""
        keys = []
        for pattern in [f"{prefix}*.json", f"{prefix}*.json.gz"]:
            for file_path in self.base_dir.glob(pattern):
                # 移除扩展名
                key = file_path.stem
                if key.endswith(".json"):
                    key = key[:-5]
                keys.append(key)
        return keys

    async def exists(self, key: str) -> bool:
        """检查文件是否存在"""
        return (self.base_dir / f"{key}.json").exists() or (
            self.base_dir / f"{key}.json.gz"
        ).exists()


class MemoryStateStore(StateStore):
    """内存状态存储（用于测试）"""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        self._store[key] = data
        return True

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)

    async def delete(self, key: str) -> bool:
        self._store.pop(key, None)
        return True

    async def list_keys(self, prefix: str) -> List[str]:
        return [k for k in self._store.keys() if k.startswith(prefix)]

    async def exists(self, key: str) -> bool:
        return key in self._store


class RedisStateStore(StateStore):
    """
    Redis 状态存储

    用于分布式场景，支持跨机器恢复。
    需要安装 redis 库。
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "agent:checkpoint:",
        ttl: int = 86400 * 7,  # 7天过期
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.ttl = ttl
        self._redis = None

    async def _get_redis(self):
        """获取 Redis 连接"""
        if self._redis is None:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(self.redis_url)
            except ImportError:
                raise RuntimeError(
                    "Redis support requires 'redis' package. "
                    "Install with: pip install redis"
                )
        return self._redis

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存到 Redis"""
        try:
            redis = await self._get_redis()
            full_key = f"{self.key_prefix}{key}"
            content = json.dumps(data, default=str)
            await redis.setex(full_key, self.ttl, content)
            return True
        except Exception as e:
            logger.error(f"[RedisStateStore] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """从 Redis 加载"""
        try:
            redis = await self._get_redis()
            full_key = f"{self.key_prefix}{key}"
            content = await redis.get(full_key)
            if content:
                return json.loads(content)
            return None
        except Exception as e:
            logger.error(f"[RedisStateStore] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """从 Redis 删除"""
        try:
            redis = await self._get_redis()
            full_key = f"{self.key_prefix}{key}"
            await redis.delete(full_key)
            return True
        except Exception as e:
            logger.error(f"[RedisStateStore] Delete failed: {e}")
            return False

    async def list_keys(self, prefix: str) -> List[str]:
        """列出所有匹配的键"""
        try:
            redis = await self._get_redis()
            pattern = f"{self.key_prefix}{prefix}*"
            keys = []
            async for key in redis.scan_iter(match=pattern):
                # 移除前缀
                keys.append(key.decode().removeprefix(self.key_prefix))
            return keys
        except Exception as e:
            logger.error(f"[RedisStateStore] List keys failed: {e}")
            return []

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            redis = await self._get_redis()
            full_key = f"{self.key_prefix}{key}"
            return await redis.exists(full_key) > 0
        except Exception as e:
            logger.error(f"[RedisStateStore] Exists check failed: {e}")
            return False


@dataclass
class CheckpointStats:
    """检查点统计信息"""

    total_checkpoints: int = 0
    total_size_bytes: int = 0
    oldest_checkpoint: Optional[datetime] = None
    newest_checkpoint: Optional[datetime] = None
    checkpoint_types: Dict[str, int] = field(default_factory=dict)
    avg_checkpoint_size: float = 0.0


class SmartCheckpointManager:
    """
    智能检查点管理器

    特性：
    1. 多种检查点策略（时间、步数、里程碑、自适应）
    2. 自适应频率调整（根据失败率动态调整）
    3. 版本控制和回滚
    4. 检查点压缩
    5. 完整性验证

    示例:
        manager = SmartCheckpointManager(
            strategy=CheckpointStrategy.ADAPTIVE,
            checkpoint_store=RedisStateStore()
        )

        # 判断是否需要检查点
        if await manager.should_checkpoint(step, state, context):
            checkpoint = await manager.create_checkpoint(...)

        # 恢复检查点
        state, context = await manager.restore_checkpoint(checkpoint_id)
    """

    def __init__(
        self,
        strategy: CheckpointStrategy = CheckpointStrategy.ADAPTIVE,
        checkpoint_store: Optional[StateStore] = None,
        max_checkpoints: int = 20,
        checkpoint_interval: int = 10,
        time_interval_seconds: int = 60,
        enable_compression: bool = True,
    ):
        """
        初始化智能检查点管理器

        Args:
            strategy: 检查点策略
            checkpoint_store: 状态存储
            max_checkpoints: 最大保存检查点数量
            checkpoint_interval: 步数检查点间隔
            time_interval_seconds: 时间检查点间隔（秒）
            enable_compression: 是否启用压缩
        """
        self.strategy = strategy
        self.store = checkpoint_store or FileStateStore()
        self.max_checkpoints = max_checkpoints
        self.checkpoint_interval = checkpoint_interval
        self.time_interval_seconds = time_interval_seconds
        self.enable_compression = enable_compression

        # 内部状态
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._last_checkpoint_time: Optional[datetime] = None
        self._last_checkpoint_step: int = 0

        # 自适应参数
        self._failure_count: int = 0
        self._success_count: int = 0
        self._recommended_interval: int = checkpoint_interval
        self._step_durations: List[float] = []

        logger.info(
            f"[SmartCheckpoint] Initialized with strategy={strategy.value}, "
            f"interval={checkpoint_interval}, max={max_checkpoints}"
        )

    @property
    def failure_rate(self) -> float:
        """计算失败率"""
        total = self._failure_count + self._success_count
        if total == 0:
            return 0.0
        return self._failure_count / total

    def record_success(self) -> None:
        """记录成功"""
        self._success_count += 1
        self._adjust_interval()

    def record_failure(self) -> None:
        """记录失败"""
        self._failure_count += 1
        self._adjust_interval()

    def _adjust_interval(self) -> None:
        """根据失败率调整检查点间隔"""
        rate = self.failure_rate

        if rate > 0.2:  # 失败率 > 20%
            # 更频繁的检查点
            self._recommended_interval = max(3, self._recommended_interval // 2)
            logger.info(
                f"[SmartCheckpoint] High failure rate ({rate:.1%}), "
                f"reduced interval to {self._recommended_interval}"
            )
        elif rate < 0.05 and self._recommended_interval < self.checkpoint_interval:
            # 失败率低，恢复默认间隔
            self._recommended_interval = min(
                self._recommended_interval + 2, self.checkpoint_interval
            )

    async def should_checkpoint(
        self, current_step: int, state: "AgentState", context: Dict[str, Any]
    ) -> bool:
        """
        智能判断是否需要检查点

        Args:
            current_step: 当前步数
            state: 当前状态
            context: 当前上下文

        Returns:
            是否需要创建检查点
        """
        from .state_machine import AgentState

        # 关键状态必须检查点
        if state in {AgentState.COMPLETED, AgentState.FAILED}:
            return True

        if self.strategy == CheckpointStrategy.TIME_BASED:
            return self._should_checkpoint_by_time()
        elif self.strategy == CheckpointStrategy.STEP_BASED:
            return self._should_checkpoint_by_step(current_step)
        elif self.strategy == CheckpointStrategy.MILESTONE_BASED:
            return self._should_checkpoint_by_milestone(state, context)
        else:  # ADAPTIVE
            return self._should_checkpoint_adaptive(current_step, state, context)

    def _should_checkpoint_by_time(self) -> bool:
        """时间驱动检查点判断"""
        if not self._last_checkpoint_time:
            return False

        elapsed = (datetime.now() - self._last_checkpoint_time).total_seconds()
        return elapsed >= self.time_interval_seconds

    def _should_checkpoint_by_step(self, current_step: int) -> bool:
        """步数驱动检查点判断"""
        if current_step - self._last_checkpoint_step >= self.checkpoint_interval:
            return True
        return False

    def _should_checkpoint_by_milestone(
        self, state: "AgentState", context: Dict[str, Any]
    ) -> bool:
        """里程碑驱动检查点判断"""
        # 在特定里程碑创建检查点
        milestones = context.get("milestones", [])
        current_milestone = context.get("current_milestone")

        if current_milestone and current_milestone not in milestones:
            return True

        return False

    def _should_checkpoint_adaptive(
        self, current_step: int, state: "AgentState", context: Dict[str, Any]
    ) -> bool:
        """
        自适应策略

        综合考虑：
        1. 步数间隔
        2. 失败率
        3. 步骤耗时
        4. 状态重要性
        """
        # 步数判断
        step_diff = current_step - self._last_checkpoint_step
        if step_diff >= self._recommended_interval:
            # 检查步骤耗时
            step_duration = context.get("step_duration", 0)

            # 如果步骤耗时较长，更频繁检查点
            if step_duration > 30:  # 单步超过 30 秒
                if step_diff >= max(3, self._recommended_interval // 2):
                    return True

            return True

        # 时间判断
        if self._should_checkpoint_by_time():
            return True

        # 里程碑判断
        if self._should_checkpoint_by_milestone(state, context):
            return True

        return False

    async def create_checkpoint(
        self,
        execution_id: str,
        checkpoint_type: CheckpointType,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        step_index: int = 0,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Checkpoint:
        """
        创建检查点

        Args:
            execution_id: 执行ID
            checkpoint_type: 检查点类型
            state: 状态数据
            context: 上下文数据
            step_index: 步骤索引
            message: 消息
            metadata: 元数据

        Returns:
            创建的检查点
        """
        import uuid

        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4().hex),
            execution_id=execution_id,
            checkpoint_type=checkpoint_type,
            state=state,
            context=context or {},
            step_index=step_index,
            message=message,
            metadata=metadata or {},
        )

        # 计算校验和
        checkpoint.checksum = checkpoint.compute_checksum()

        # 存储检查点
        await self.store.save(
            f"checkpoint_{checkpoint.checkpoint_id}", checkpoint.to_dict()
        )

        # 更新缓存
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        self._last_checkpoint_time = datetime.now()
        self._last_checkpoint_step = step_index

        # 清理旧检查点
        await self._cleanup_old_checkpoints(execution_id)

        logger.info(
            f"[SmartCheckpoint] Created checkpoint {checkpoint.checkpoint_id[:8]} "
            f"type={checkpoint_type.value} step={step_index}"
        )

        return checkpoint

    async def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """获取检查点"""
        # 先从缓存获取
        if checkpoint_id in self._checkpoints:
            return self._checkpoints[checkpoint_id]

        # 从存储获取
        data = await self.store.load(f"checkpoint_{checkpoint_id}")
        if data:
            checkpoint = Checkpoint.from_dict(data)
            self._checkpoints[checkpoint_id] = checkpoint
            return checkpoint

        return None

    async def get_latest_checkpoint(self, execution_id: str) -> Optional[Checkpoint]:
        """获取最新检查点"""
        keys = await self.store.list_keys(f"checkpoint_")

        checkpoints = []
        for key in keys:
            data = await self.store.load(key)
            if data and data.get("execution_id") == execution_id:
                checkpoints.append(Checkpoint.from_dict(data))

        if not checkpoints:
            return None

        # 按时间戳排序，返回最新的
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        return checkpoints[0]

    async def restore_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        恢复检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            恢复的状态数据，如果失败返回 None

        Raises:
            CheckpointNotFoundError: 检查点未找到
            CheckpointCorruptedError: 检查点损坏
        """
        checkpoint = await self.get_checkpoint(checkpoint_id)

        if not checkpoint:
            raise CheckpointNotFoundError(f"Checkpoint {checkpoint_id} not found")

        # 验证完整性
        if not checkpoint.validate():
            raise CheckpointCorruptedError(
                f"Checkpoint {checkpoint_id} is corrupted (checksum mismatch)"
            )

        logger.info(
            f"[SmartCheckpoint] Restored checkpoint {checkpoint_id[:8]} "
            f"at step {checkpoint.step_index}"
        )

        return {
            "state": checkpoint.state,
            "context": checkpoint.context,
            "step_index": checkpoint.step_index,
            "timestamp": checkpoint.timestamp,
        }

    async def list_checkpoints(self, execution_id: str) -> List[Checkpoint]:
        """列出所有检查点"""
        keys = await self.store.list_keys(f"checkpoint_")

        checkpoints = []
        for key in keys:
            data = await self.store.load(key)
            if data and data.get("execution_id") == execution_id:
                checkpoints.append(Checkpoint.from_dict(data))

        # 按时间戳排序
        checkpoints.sort(key=lambda c: c.timestamp)
        return checkpoints

    async def get_checkpoint_stats(self, execution_id: str) -> CheckpointStats:
        """获取检查点统计信息"""
        checkpoints = await self.list_checkpoints(execution_id)

        if not checkpoints:
            return CheckpointStats()

        total_size = 0
        types_count: Dict[str, int] = {}

        for cp in checkpoints:
            # 估算大小
            size = len(json.dumps(cp.to_dict(), default=str))
            total_size += size

            cp_type = cp.checkpoint_type.value
            types_count[cp_type] = types_count.get(cp_type, 0) + 1

        return CheckpointStats(
            total_checkpoints=len(checkpoints),
            total_size_bytes=total_size,
            oldest_checkpoint=checkpoints[0].timestamp,
            newest_checkpoint=checkpoints[-1].timestamp,
            checkpoint_types=types_count,
            avg_checkpoint_size=total_size / len(checkpoints),
        )

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """删除检查点"""
        await self.store.delete(f"checkpoint_{checkpoint_id}")
        self._checkpoints.pop(checkpoint_id, None)
        logger.info(f"[SmartCheckpoint] Deleted checkpoint {checkpoint_id[:8]}")
        return True

    async def _cleanup_old_checkpoints(self, execution_id: str) -> None:
        """清理旧检查点"""
        checkpoints = await self.list_checkpoints(execution_id)

        if len(checkpoints) > self.max_checkpoints:
            # 保留最新的 N 个
            to_remove = checkpoints[: -self.max_checkpoints]

            for cp in to_remove:
                await self.store.delete(f"checkpoint_{cp.checkpoint_id}")
                self._checkpoints.pop(cp.checkpoint_id, None)

            logger.info(
                f"[SmartCheckpoint] Cleaned up {len(to_remove)} old checkpoints"
            )

    def get_recommended_interval(self) -> int:
        """获取推荐的检查点间隔"""
        return self._recommended_interval

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            "strategy": self.strategy.value,
            "cached_checkpoints": len(self._checkpoints),
            "failure_rate": self.failure_rate,
            "recommended_interval": self._recommended_interval,
            "last_checkpoint_step": self._last_checkpoint_step,
            "last_checkpoint_time": self._last_checkpoint_time.isoformat()
            if self._last_checkpoint_time
            else None,
        }
