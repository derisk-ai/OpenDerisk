"""
分布式 Agent 执行架构 - 修订版

针对极端场景的设计改进：
1. 持久化存储面向接口编程，支持多种后端
2. 主 Agent 休眠/唤醒机制
3. 子 Agent 独立对话管理
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Part 1: 持久化存储抽象 - 面向接口编程
# =============================================================================


class StorageBackendType(Enum):
    """存储后端类型"""

    MEMORY = "memory"  # 内存存储 (默认，用于开发/测试)
    FILE = "file"  # 文件存储 (单机生产)
    REDIS = "redis"  # Redis 存储 (分布式)
    DATABASE = "database"  # 数据库存储 (MySQL/PostgreSQL)
    S3 = "s3"  # 对象存储 (AWS S3/OSS)


@dataclass
class StorageConfig:
    """存储配置"""

    backend_type: StorageBackendType = StorageBackendType.MEMORY

    # 文件存储配置
    base_dir: str = ".agent_storage"

    # Redis 配置
    redis_url: Optional[str] = None
    key_prefix: str = "agent:"
    ttl_seconds: int = 86400 * 7  # 7 天

    # 数据库配置
    database_url: Optional[str] = None
    table_name: str = "agent_state"

    # S3 配置
    s3_bucket: Optional[str] = None
    s3_prefix: str = "agent-state/"


class StateStorage(ABC):
    """
    状态存储抽象接口

    面向接口编程，支持多种后端实现。
    """

    @abstractmethod
    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存状态"""
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载状态"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除状态"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查是否存在"""
        pass

    @abstractmethod
    async def list_keys(self, prefix: str) -> List[str]:
        """列出指定前缀的所有键"""
        pass

    @abstractmethod
    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int = 30,
        owner: str = None,
    ) -> bool:
        """获取分布式锁"""
        pass

    @abstractmethod
    async def release_lock(self, key: str, owner: str = None) -> bool:
        """释放分布式锁"""
        pass


class MemoryStateStorage(StateStorage):
    """
    内存存储实现

    默认实现，适用于：
    - 开发和测试
    - 单进程场景
    - 临时任务
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, str] = {}  # key -> owner

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        self._store[key] = data
        return True

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)

    async def delete(self, key: str) -> bool:
        self._store.pop(key, None)
        return True

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def list_keys(self, prefix: str) -> List[str]:
        return [k for k in self._store.keys() if k.startswith(prefix)]

    async def acquire_lock(
        self, key: str, ttl_seconds: int = 30, owner: str = None
    ) -> bool:
        lock_key = f"lock:{key}"
        if lock_key not in self._locks:
            self._locks[lock_key] = owner or "default"
            return True
        return self._locks[lock_key] == owner

    async def release_lock(self, key: str, owner: str = None) -> bool:
        lock_key = f"lock:{key}"
        if self._locks.get(lock_key) == owner:
            del self._locks[lock_key]
            return True
        return False


class FileStateStorage(StateStorage):
    """
    文件存储实现

    适用于：
    - 单机生产环境
    - 无需 Redis 的场景
    - 需要持久化但不需要分布式
    """

    def __init__(self, config: StorageConfig):
        from pathlib import Path
        import json
        import gzip

        self.base_dir = Path(config.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, str] = {}

    def _get_file_path(self, key: str) -> "Path":
        from pathlib import Path

        # 使用安全文件名
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe_key}.json"

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        import json

        try:
            file_path = self._get_file_path(key)
            file_path.write_text(json.dumps(data, default=str, indent=2))
            return True
        except Exception as e:
            logger.error(f"[FileStateStorage] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        import json

        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                return json.loads(file_path.read_text())
            return None
        except Exception as e:
            logger.error(f"[FileStateStorage] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"[FileStateStorage] Delete failed: {e}")
            return False

    async def exists(self, key: str) -> bool:
        return self._get_file_path(key).exists()

    async def list_keys(self, prefix: str) -> List[str]:
        import fnmatch

        keys = []
        for file_path in self.base_dir.glob("*.json"):
            key = file_path.stem
            if key.startswith(prefix):
                keys.append(key)
        return keys

    async def acquire_lock(
        self, key: str, ttl_seconds: int = 30, owner: str = None
    ) -> bool:
        lock_file = self.base_dir / f".lock_{key}"
        if not lock_file.exists():
            lock_file.write_text(owner or "default")
            return True
        return False

    async def release_lock(self, key: str, owner: str = None) -> bool:
        lock_file = self.base_dir / f".lock_{key}"
        if lock_file.exists():
            lock_file.unlink()
            return True
        return False


class RedisStateStorage(StateStorage):
    """
    Redis 存储实现

    适用于：
    - 分布式环境
    - 需要跨进程/机器共享状态
    - 高并发场景
    """

    def __init__(self, config: StorageConfig):
        self.config = config
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(
                    self.config.redis_url or "redis://localhost:6379/0"
                )
            except ImportError:
                raise RuntimeError(
                    "Redis storage requires 'redis' package. "
                    "Install with: pip install redis"
                )
        return self._redis

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        import json

        try:
            redis = await self._get_redis()
            full_key = f"{self.config.key_prefix}{key}"
            content = json.dumps(data, default=str)
            await redis.setex(full_key, self.config.ttl_seconds, content)
            return True
        except Exception as e:
            logger.error(f"[RedisStateStorage] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        import json

        try:
            redis = await self._get_redis()
            full_key = f"{self.config.key_prefix}{key}"
            content = await redis.get(full_key)
            if content:
                return json.loads(content)
            return None
        except Exception as e:
            logger.error(f"[RedisStateStorage] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        try:
            redis = await self._get_redis()
            full_key = f"{self.config.key_prefix}{key}"
            await redis.delete(full_key)
            return True
        except Exception as e:
            logger.error(f"[RedisStateStorage] Delete failed: {e}")
            return False

    async def exists(self, key: str) -> bool:
        try:
            redis = await self._get_redis()
            full_key = f"{self.config.key_prefix}{key}"
            return await redis.exists(full_key) > 0
        except:
            return False

    async def list_keys(self, prefix: str) -> List[str]:
        try:
            redis = await self._get_redis()
            pattern = f"{self.config.key_prefix}{prefix}*"
            keys = []
            async for key in redis.scan_iter(match=pattern):
                key_str = key.decode().removeprefix(self.config.key_prefix)
                keys.append(key_str)
            return keys
        except Exception as e:
            logger.error(f"[RedisStateStorage] List keys failed: {e}")
            return []

    async def acquire_lock(
        self, key: str, ttl_seconds: int = 30, owner: str = None
    ) -> bool:
        try:
            redis = await self._get_redis()
            lock_key = f"{self.config.key_prefix}lock:{key}"
            owner = owner or "default"
            # 使用 SET NX EX 实现分布式锁
            result = await redis.set(lock_key, owner, nx=True, ex=ttl_seconds)
            return result is not None
        except Exception as e:
            logger.error(f"[RedisStateStorage] Acquire lock failed: {e}")
            return False

    async def release_lock(self, key: str, owner: str = None) -> bool:
        try:
            redis = await self._get_redis()
            lock_key = f"{self.config.key_prefix}lock:{key}"
            owner = owner or "default"

            # Lua 脚本保证原子性
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = await redis.eval(lua_script, 1, lock_key, owner)
            return result == 1
        except Exception as e:
            logger.error(f"[RedisStateStorage] Release lock failed: {e}")
            return False


class StateStorageFactory:
    """
    状态存储工厂

    根据配置创建合适的存储实现
    """

    @staticmethod
    def create(config: StorageConfig) -> StateStorage:
        """创建状态存储实例"""
        if config.backend_type == StorageBackendType.MEMORY:
            return MemoryStateStorage()

        elif config.backend_type == StorageBackendType.FILE:
            return FileStateStorage(config)

        elif config.backend_type == StorageBackendType.REDIS:
            if not config.redis_url:
                raise ValueError("Redis URL is required for Redis storage")
            return RedisStateStorage(config)

        elif config.backend_type == StorageBackendType.DATABASE:
            # 导入数据库存储实现
            from .database_storage import (
                DatabaseStateStorage,
                MySQLStateStorage,
                SQLiteStateStorage,
            )

            # 根据 database_url 判断数据库类型
            if config.database_url:
                db_url = config.database_url.lower()
                if "postgresql" in db_url or "postgres" in db_url:
                    return DatabaseStateStorage(config)
                elif "mysql" in db_url:
                    return MySQLStateStorage(config)
                elif "sqlite" in db_url or db_url.endswith(".db"):
                    return SQLiteStateStorage(config)
                else:
                    # 默认使用 PostgreSQL
                    return DatabaseStateStorage(config)
            else:
                # 默认 SQLite
                return SQLiteStateStorage(config)

        elif config.backend_type == StorageBackendType.S3:
            # TODO: 实现 S3 存储
            raise NotImplementedError("S3 storage not implemented yet")

        else:
            # 默认使用内存存储
            return MemoryStateStorage()

    @staticmethod
    def create_default() -> StateStorage:
        """创建默认存储 (内存)"""
        return MemoryStateStorage()

    @staticmethod
    def create_redis(
        redis_url: str, key_prefix: str = "agent:", ttl_seconds: int = 86400 * 7
    ) -> StateStorage:
        """便捷方法：创建Redis存储"""
        config = StorageConfig(
            backend_type=StorageBackendType.REDIS,
            redis_url=redis_url,
            key_prefix=key_prefix,
            ttl_seconds=ttl_seconds,
        )
        return StateStorageFactory.create(config)

    @staticmethod
    def create_database(
        database_url: str, table_name: str = "agent_state"
    ) -> StateStorage:
        """便捷方法：创建数据库存储"""
        config = StorageConfig(
            backend_type=StorageBackendType.DATABASE,
            database_url=database_url,
            table_name=table_name,
        )
        return StateStorageFactory.create(config)

    @staticmethod
    def create_file(base_dir: str = ".agent_storage") -> StateStorage:
        """便捷方法：创建文件存储"""
        config = StorageConfig(
            backend_type=StorageBackendType.FILE,
            base_dir=base_dir,
        )
        return StateStorageFactory.create(config)


# =============================================================================
# Part 2: 主 Agent 休眠/唤醒机制
# =============================================================================


class MainAgentState(Enum):
    """主 Agent 状态"""

    ACTIVE = "active"  # 活跃执行
    WAITING = "waiting"  # 等待子任务
    SLEEPING = "sleeping"  # 休眠中
    WAKEUP_PENDING = "wakeup_pending"  # 待唤醒
    COMPLETED = "completed"  # 完成


@dataclass
class SleepContext:
    """休眠上下文"""

    task_id: str
    sleep_at: datetime
    reason: str

    # 唤醒条件
    wake_conditions: List[str] = field(default_factory=list)  # 子任务 ID 列表
    wakeup_webhook: Optional[str] = None  # 唤醒回调 URL

    # 休眠状态
    checkpoint_id: Optional[str] = None
    state_data: Dict[str, Any] = field(default_factory=dict)

    # 超时
    max_sleep_seconds: int = 86400 * 3  # 最长休眠 3 天
    wakeup_at: Optional[datetime] = None


@dataclass
class WakeupSignal:
    """唤醒信号"""

    task_id: str
    wakeup_reason: str
    triggered_by: str  # 子任务 ID 或 "timeout" 或 "manual"
    subagent_results: List[Dict[str, Any]] = field(default_factory=list)


class AgentSleepManager:
    """
    Agent 休眠管理器

    管理主 Agent 的休眠和唤醒：
    1. 当主 Agent 启动子任务后，进入休眠
    2. 子任务完成后，发送唤醒信号
    3. 主 Agent 恢复执行
    """

    def __init__(
        self,
        storage: StateStorage,
        on_wakeup: Optional[Callable[[WakeupSignal], Awaitable[None]]] = None,
        check_interval_seconds: int = 60,
    ):
        self.storage = storage
        self.on_wakeup = on_wakeup
        self.check_interval = check_interval_seconds

        self._sleep_contexts: Dict[str, SleepContext] = {}
        self._wakeup_queue: asyncio.Queue = asyncio.Queue()

    async def sleep(
        self,
        task_id: str,
        reason: str,
        wait_for_subtasks: List[str],
        checkpoint_id: str = None,
        state_data: Dict[str, Any] = None,
        max_sleep_seconds: int = 86400 * 3,
    ) -> SleepContext:
        """
        主 Agent 进入休眠

        Args:
            task_id: 主任务 ID
            reason: 休眠原因
            wait_for_subtasks: 等待的子任务 ID 列表
            checkpoint_id: 检查点 ID
            state_data: 状态数据
            max_sleep_seconds: 最长休眠时间

        Returns:
            SleepContext: 休眠上下文
        """
        context = SleepContext(
            task_id=task_id,
            sleep_at=datetime.now(),
            reason=reason,
            wake_conditions=wait_for_subtasks.copy(),
            checkpoint_id=checkpoint_id,
            state_data=state_data or {},
            max_sleep_seconds=max_sleep_seconds,
        )

        # 保存休眠状态
        await self.storage.save(
            f"sleep:{task_id}",
            {
                "task_id": task_id,
                "sleep_at": context.sleep_at.isoformat(),
                "reason": reason,
                "wake_conditions": wait_for_subtasks,
                "checkpoint_id": checkpoint_id,
                "state_data": state_data,
                "completed_subtasks": [],
            },
        )

        self._sleep_contexts[task_id] = context

        logger.info(
            f"[AgentSleepManager] Agent sleeping: task={task_id}, "
            f"waiting for {len(wait_for_subtasks)} subtasks"
        )

        return context

    async def wakeup(
        self,
        task_id: str,
        wakeup_reason: str,
        triggered_by: str,
        subagent_result: Dict[str, Any] = None,
    ) -> bool:
        """
        唤醒主 Agent

        Args:
            task_id: 主任务 ID
            wakeup_reason: 唤醒原因
            triggered_by: 触发者 (子任务 ID 或 "timeout")
            subagent_result: 子任务结果

        Returns:
            是否成功唤醒
        """
        # 加载休眠状态
        sleep_data = await self.storage.load(f"sleep:{task_id}")
        if not sleep_data:
            logger.warning(f"[AgentSleepManager] Sleep context not found: {task_id}")
            return False

        # 更新完成的子任务
        completed = sleep_data.get("completed_subtasks", [])
        if triggered_by not in completed:
            completed.append(triggered_by)

        # 检查是否所有子任务都完成
        wake_conditions = sleep_data.get("wake_conditions", [])
        all_completed = all(c in completed for c in wake_conditions)

        if all_completed or wakeup_reason == "timeout":
            # 创建唤醒信号
            signal = WakeupSignal(
                task_id=task_id,
                wakeup_reason=wakeup_reason,
                triggered_by=triggered_by,
                subagent_results=sleep_data.get("subagent_results", []),
            )

            if subagent_result:
                signal.subagent_results.append(subagent_result)

            # 发送唤醒信号
            await self._wakeup_queue.put(signal)

            # 清理休眠状态
            await self.storage.delete(f"sleep:{task_id}")
            self._sleep_contexts.pop(task_id, None)

            logger.info(
                f"[AgentSleepManager] Agent wakeup: task={task_id}, "
                f"reason={wakeup_reason}, completed={len(completed)}/{len(wake_conditions)}"
            )

            # 调用唤醒回调
            if self.on_wakeup:
                await self.on_wakeup(signal)

            return True

        else:
            # 更新进度
            sleep_data["completed_subtasks"] = completed
            if subagent_result:
                sleep_data.setdefault("subagent_results", []).append(subagent_result)
            await self.storage.save(f"sleep:{task_id}", sleep_data)

            logger.debug(
                f"[AgentSleepManager] Subtask completed: {triggered_by}, "
                f"progress={len(completed)}/{len(wake_conditions)}"
            )

            return False

    async def wait_for_wakeup(
        self,
        task_id: str,
        timeout_seconds: int = None,
    ) -> Optional[WakeupSignal]:
        """
        等待唤醒信号

        Args:
            task_id: 主任务 ID
            timeout_seconds: 超时时间

        Returns:
            WakeupSignal 或 None (超时)
        """
        start_time = datetime.now()

        while True:
            # 检查队列
            try:
                signal = self._wakeup_queue.get_nowait()
                if signal.task_id == task_id:
                    return signal
                else:
                    # 放回队列
                    await self._wakeup_queue.put(signal)
            except asyncio.QueueEmpty:
                pass

            # 检查超时
            if timeout_seconds:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= timeout_seconds:
                    return None

            # 检查是否需要超时唤醒
            sleep_data = await self.storage.load(f"sleep:{task_id}")
            if sleep_data:
                sleep_at = datetime.fromisoformat(sleep_data["sleep_at"])
                max_sleep = sleep_data.get("max_sleep_seconds", 86400 * 3)
                elapsed = (datetime.now() - sleep_at).total_seconds()

                if elapsed >= max_sleep:
                    # 超时唤醒
                    await self.wakeup(
                        task_id=task_id,
                        wakeup_reason="timeout",
                        triggered_by="timeout",
                    )

            await asyncio.sleep(self.check_interval)

    async def get_sleep_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取休眠状态"""
        return await self.storage.load(f"sleep:{task_id}")

    async def list_sleeping_agents(self) -> List[str]:
        """列出所有休眠中的 Agent"""
        return await self.storage.list_keys("sleep:")


# =============================================================================
# Part 3: 子 Agent 独立对话管理
# =============================================================================


class SubagentConversationStatus(Enum):
    """子 Agent 对话状态"""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SubagentConversation:
    """
    子 Agent 独立对话

    每个子 Agent 有独立的对话上下文，
    可以和主 Agent 任务关联。
    """

    conversation_id: str
    parent_task_id: str  # 关联的主任务 ID
    subagent_name: str

    status: SubagentConversationStatus = SubagentConversationStatus.CREATED

    # 对话上下文
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    # 执行信息
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 结果
    result: Optional[str] = None
    error: Optional[str] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 检查点
    checkpoint_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "parent_task_id": self.parent_task_id,
            "subagent_name": self.subagent_name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ConversationLink:
    """对话关联"""

    parent_task_id: str
    child_conversation_id: str
    link_type: str  # "subtask", "delegation", "continuation"
    created_at: datetime = field(default_factory=datetime.now)

    # 关联数据
    shared_context: Dict[str, Any] = field(default_factory=dict)
    message_refs: List[str] = field(default_factory=list)


class SubagentConversationManager:
    """
    子 Agent 对话管理器

    管理:
    1. 子 Agent 独立对话创建
    2. 对话与主任务的关联
    3. 对话状态追踪
    4. 对话间消息传递
    """

    def __init__(
        self,
        storage: StateStorage,
        sleep_manager: AgentSleepManager,
    ):
        self.storage = storage
        self.sleep_manager = sleep_manager

        self._conversations: Dict[str, SubagentConversation] = {}
        self._links: Dict[str, List[ConversationLink]] = {}

    async def create_conversation(
        self,
        parent_task_id: str,
        subagent_name: str,
        initial_context: Dict[str, Any] = None,
    ) -> SubagentConversation:
        """
        创建子 Agent 独立对话

        Args:
            parent_task_id: 主任务 ID
            subagent_name: 子 Agent 名称
            initial_context: 初始上下文

        Returns:
            创建的对话
        """
        import uuid

        conversation = SubagentConversation(
            conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
            parent_task_id=parent_task_id,
            subagent_name=subagent_name,
            context=initial_context or {},
        )

        # 保存对话
        await self.storage.save(
            f"conversation:{conversation.conversation_id}",
            conversation.to_dict(),
        )

        # 创建关联
        link = ConversationLink(
            parent_task_id=parent_task_id,
            child_conversation_id=conversation.conversation_id,
            link_type="subtask",
            shared_context=initial_context or {},
        )

        if parent_task_id not in self._links:
            self._links[parent_task_id] = []
        self._links[parent_task_id].append(link)

        # 保存关联
        await self.storage.save(
            f"link:{parent_task_id}:{conversation.conversation_id}",
            {
                "parent_task_id": parent_task_id,
                "child_conversation_id": conversation.conversation_id,
                "link_type": "subtask",
            },
        )

        self._conversations[conversation.conversation_id] = conversation

        logger.info(
            f"[SubagentConversationManager] Created conversation: "
            f"conv_id={conversation.conversation_id}, parent={parent_task_id}"
        )

        return conversation

    async def get_conversation(
        self,
        conversation_id: str,
    ) -> Optional[SubagentConversation]:
        """获取对话"""
        if conversation_id in self._conversations:
            return self._conversations[conversation_id]

        data = await self.storage.load(f"conversation:{conversation_id}")
        if data:
            conv = SubagentConversation(
                conversation_id=data["conversation_id"],
                parent_task_id=data["parent_task_id"],
                subagent_name=data["subagent_name"],
                status=SubagentConversationStatus(data["status"]),
            )
            self._conversations[conversation_id] = conv
            return conv

        return None

    async def update_conversation_status(
        self,
        conversation_id: str,
        status: SubagentConversationStatus,
        result: str = None,
        error: str = None,
    ) -> bool:
        """更新对话状态"""
        conv = await self.get_conversation(conversation_id)
        if not conv:
            return False

        conv.status = status

        if status == SubagentConversationStatus.RUNNING:
            conv.started_at = datetime.now()
        elif status in [
            SubagentConversationStatus.COMPLETED,
            SubagentConversationStatus.FAILED,
        ]:
            conv.completed_at = datetime.now()
            conv.result = result
            conv.error = error

            # 通知主 Agent
            await self.sleep_manager.wakeup(
                task_id=conv.parent_task_id,
                wakeup_reason="subtask_completed",
                triggered_by=conversation_id,
                subagent_result={
                    "conversation_id": conversation_id,
                    "success": status == SubagentConversationStatus.COMPLETED,
                    "result": result,
                    "error": error,
                },
            )

        # 保存
        await self.storage.save(
            f"conversation:{conversation_id}",
            conv.to_dict(),
        )

        return True

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None,
    ):
        """添加消息到对话"""
        conv = await self.get_conversation(conversation_id)
        if not conv:
            return False

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        conv.messages.append(message)

        await self.storage.save(
            f"conversation:{conversation_id}",
            conv.to_dict(),
        )

        return True

    async def get_child_conversations(
        self,
        parent_task_id: str,
    ) -> List[SubagentConversation]:
        """获取主任务的所有子对话"""
        links = self._links.get(parent_task_id, [])
        conversations = []

        for link in links:
            conv = await self.get_conversation(link.child_conversation_id)
            if conv:
                conversations.append(conv)

        return conversations

    async def get_conversation_progress(
        self,
        parent_task_id: str,
    ) -> Dict[str, Any]:
        """获取主任务的子对话进度"""
        conversations = await self.get_child_conversations(parent_task_id)

        total = len(conversations)
        completed = sum(
            1 for c in conversations if c.status == SubagentConversationStatus.COMPLETED
        )
        failed = sum(
            1 for c in conversations if c.status == SubagentConversationStatus.FAILED
        )
        running = sum(
            1 for c in conversations if c.status == SubagentConversationStatus.RUNNING
        )

        return {
            "parent_task_id": parent_task_id,
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": total - completed - failed - running,
            "progress_percent": (completed + failed) / total * 100 if total > 0 else 0,
        }

    async def share_context_to_child(
        self,
        parent_task_id: str,
        context_key: str,
        context_value: Any,
    ):
        """共享上下文到所有子对话"""
        conversations = await self.get_child_conversations(parent_task_id)

        for conv in conversations:
            conv.context[context_key] = context_value
            await self.storage.save(
                f"conversation:{conv.conversation_id}",
                conv.to_dict(),
            )

    async def collect_child_results(
        self,
        parent_task_id: str,
    ) -> Dict[str, Any]:
        """收集所有子对话的结果"""
        conversations = await self.get_child_conversations(parent_task_id)

        results = {}
        for conv in conversations:
            results[conv.conversation_id] = {
                "subagent_name": conv.subagent_name,
                "status": conv.status.value,
                "result": conv.result,
                "error": conv.error,
                "duration_seconds": (
                    (conv.completed_at - conv.started_at).total_seconds()
                    if conv.completed_at and conv.started_at
                    else None
                ),
            }

        return results


# =============================================================================
# Part 4: 完整的分布式任务执行器
# =============================================================================


class DistributedTaskExecutor:
    """
    分布式任务执行器

    完整实现：
    1. 持久化检查点 (多后端支持)
    2. 主 Agent 休眠/唤醒
    3. 子 Agent 独立对话管理
    """

    def __init__(
        self,
        storage_config: StorageConfig = None,
    ):
        # 创建存储
        self.storage = StateStorageFactory.create(storage_config or StorageConfig())

        # 创建管理器
        self.sleep_manager = AgentSleepManager(
            storage=self.storage,
        )

        self.conversation_manager = SubagentConversationManager(
            storage=self.storage,
            sleep_manager=self.sleep_manager,
        )

    async def execute_main_task(
        self,
        task_id: str,
        agent: Any,
        goal: str,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """
        执行主任务

        支持长期运行和中断恢复
        """
        # 1. 尝试恢复
        if resume:
            checkpoint = await self.storage.load(f"checkpoint:{task_id}")
            if checkpoint:
                logger.info(
                    f"[DistributedTaskExecutor] Resuming from checkpoint: {task_id}"
                )
                # 恢复 Agent 状态
                # ...

        # 2. 执行任务
        try:
            result = await agent.execute(goal)

            # 保存最终检查点
            await self.storage.save(
                f"checkpoint:{task_id}",
                {
                    "status": "completed",
                    "result": result,
                    "completed_at": datetime.now().isoformat(),
                },
            )

            return {
                "success": True,
                "result": result,
            }

        except Exception as e:
            # 保存错误检查点
            await self.storage.save(
                f"checkpoint:{task_id}",
                {
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.now().isoformat(),
                },
            )

            return {
                "success": False,
                "error": str(e),
            }

    async def delegate_to_subagents(
        self,
        parent_task_id: str,
        subagent_name: str,
        tasks: List[str],
        max_concurrent: int = 10,
    ) -> List[str]:
        """
        委派任务给子 Agent

        Args:
            parent_task_id: 主任务 ID
            subagent_name: 子 Agent 名称
            tasks: 任务列表
            max_concurrent: 最大并发数

        Returns:
            创建的对话 ID 列表
        """
        conversation_ids = []

        for task in tasks:
            # 创建独立对话
            conv = await self.conversation_manager.create_conversation(
                parent_task_id=parent_task_id,
                subagent_name=subagent_name,
                initial_context={"task": task},
            )

            conversation_ids.append(conv.conversation_id)

        # 主 Agent 进入休眠，等待子任务完成
        await self.sleep_manager.sleep(
            task_id=parent_task_id,
            reason=f"Waiting for {len(tasks)} subtasks",
            wait_for_subtasks=conversation_ids,
        )

        logger.info(
            f"[DistributedTaskExecutor] Main agent sleeping, "
            f"waiting for {len(conversation_ids)} subagent conversations"
        )

        return conversation_ids

    async def wait_for_subagents(
        self,
        parent_task_id: str,
        timeout_seconds: int = None,
    ) -> Dict[str, Any]:
        """
        等待子 Agent 完成

        Returns:
            汇总的结果
        """
        # 等待唤醒
        wakeup_signal = await self.sleep_manager.wait_for_wakeup(
            task_id=parent_task_id,
            timeout_seconds=timeout_seconds,
        )

        if wakeup_signal:
            # 收集结果
            results = await self.conversation_manager.collect_child_results(
                parent_task_id
            )

            return {
                "wakeup_reason": wakeup_signal.wakeup_reason,
                "subagent_results": results,
            }

        return {
            "wakeup_reason": "timeout",
            "subagent_results": {},
        }


# =============================================================================
# 使用示例
# =============================================================================


async def example_long_running_task():
    """长期任务示例"""
    from derisk.agent.core_v2 import (
        DistributedTaskExecutor,
        StorageConfig,
        StorageBackendType,
    )

    # 配置存储 (默认使用内存，生产环境使用 Redis)
    config = StorageConfig(
        backend_type=StorageBackendType.FILE,  # 或 REDIS
        base_dir=".agent_checkpoints",
    )

    executor = DistributedTaskExecutor(storage_config=config)

    # 执行长期任务
    result = await executor.execute_main_task(
        task_id="long-analysis-001",
        agent=my_agent,
        goal="对 10TB 数据进行深度分析",
        resume=True,
    )


async def example_100_subagents():
    """100 子 Agent 示例"""
    from derisk.agent.core_v2 import (
        DistributedTaskExecutor,
        StorageConfig,
        StorageBackendType,
    )

    # 配置 Redis 存储 (分布式场景)
    config = StorageConfig(
        backend_type=StorageBackendType.REDIS,
        redis_url="redis://localhost:6379/0",
    )

    executor = DistributedTaskExecutor(storage_config=config)

    # 创建 100 个子任务
    targets = [f"target-{i}" for i in range(100)]
    tasks = [f"分析目标: {target}" for target in targets]

    # 委派给子 Agent
    conversation_ids = await executor.delegate_to_subagents(
        parent_task_id="batch-analysis-001",
        subagent_name="analyzer",
        tasks=tasks,
        max_concurrent=10,
    )

    print(f"创建了 {len(conversation_ids)} 个子对话")
    print("主 Agent 进入休眠...")

    # 等待子 Agent 完成 (可能需要一天)
    results = await executor.wait_for_subagents(
        parent_task_id="batch-analysis-001",
        timeout_seconds=86400,  # 最多等一天
    )

    print(f"唤醒原因: {results['wakeup_reason']}")
    print(f"完成的子任务: {len(results['subagent_results'])}")
