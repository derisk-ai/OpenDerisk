"""
Distributed State Store - 分布式状态存储

支持 Redis 等分布式存储后端，解决多节点部署问题
"""

from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class DistributedStateStore(ABC):
    """分布式状态存储抽象接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """发布消息到频道"""
        pass
    
    @abstractmethod
    async def subscribe(self, channel: str) -> "DistributedSubscription":
        """订阅频道"""
        pass
    
    @abstractmethod
    async def list_push(self, key: str, value: Any) -> int:
        """推送到列表"""
        pass
    
    @abstractmethod
    async def list_pop(self, key: str) -> Optional[Any]:
        """从列表弹出"""
        pass
    
    @abstractmethod
    async def list_range(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表范围"""
        pass
    
    @abstractmethod
    async def list_length(self, key: str) -> int:
        """获取列表长度"""
        pass


class DistributedSubscription(ABC):
    """分布式订阅接口"""
    
    @abstractmethod
    async def get_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """获取消息"""
        pass
    
    @abstractmethod
    async def unsubscribe(self):
        """取消订阅"""
        pass


class RedisStateStore(DistributedStateStore):
    """Redis 分布式状态存储"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
    
    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self._redis_url)
            except ImportError:
                raise RuntimeError("redis package not installed. Run: pip install redis")
        return self._redis
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        r = await self._get_redis()
        value = await r.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        r = await self._get_redis()
        data = json.dumps(value)
        if ttl:
            await r.setex(key, ttl, data)
        else:
            await r.set(key, data)
        return True
    
    async def delete(self, key: str) -> bool:
        r = await self._get_redis()
        result = await r.delete(key)
        return result > 0
    
    async def exists(self, key: str) -> bool:
        r = await self._get_redis()
        return await r.exists(key) > 0
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        r = await self._get_redis()
        await r.publish(channel, json.dumps(message))
        return True
    
    async def subscribe(self, channel: str) -> "RedisSubscription":
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        return RedisSubscription(pubsub, channel)
    
    async def list_push(self, key: str, value: Any) -> int:
        r = await self._get_redis()
        data = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        return await r.rpush(key, data)
    
    async def list_pop(self, key: str) -> Optional[Any]:
        r = await self._get_redis()
        value = await r.lpop(key)
        if value:
            try:
                return json.loads(value)
            except:
                return value
        return None
    
    async def list_range(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        r = await self._get_redis()
        values = await r.lrange(key, start, end)
        result = []
        for v in values:
            try:
                result.append(json.loads(v))
            except:
                result.append(v)
        return result
    
    async def list_length(self, key: str) -> int:
        r = await self._get_redis()
        return await r.llen(key)


class RedisSubscription(DistributedSubscription):
    """Redis 订阅实现"""
    
    def __init__(self, pubsub, channel: str):
        self._pubsub = pubsub
        self._channel = channel
    
    async def get_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            message = await self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=timeout
            )
            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                return json.loads(data)
        except Exception as e:
            logger.error(f"[RedisSubscription] Error getting message: {e}")
        return None
    
    async def unsubscribe(self):
        await self._pubsub.unsubscribe(self._channel)
        await self._pubsub.close()


class MemoryDistributedStore(DistributedStateStore):
    """内存分布式存储（单节点开发/测试用）"""
    
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._lists: Dict[str, List[Any]] = {}
        self._channels: Dict[str, List[asyncio.Queue]] = {}
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)
    
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        self._store[key] = value
        return True
    
    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        return key in self._store
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        if channel not in self._channels:
            self._channels[channel] = []
        for queue in self._channels[channel]:
            await queue.put(message)
        return True
    
    async def subscribe(self, channel: str) -> "MemorySubscription":
        if channel not in self._channels:
            self._channels[channel] = []
        queue = asyncio.Queue()
        self._channels[channel].append(queue)
        return MemorySubscription(queue, channel, self._channels)
    
    async def list_push(self, key: str, value: Any) -> int:
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].append(value)
        return len(self._lists[key])
    
    async def list_pop(self, key: str) -> Optional[Any]:
        if key in self._lists and self._lists[key]:
            return self._lists[key].pop(0)
        return None
    
    async def list_range(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        if key not in self._lists:
            return []
        lst = self._lists[key]
        if end == -1:
            return lst[start:]
        return lst[start:end]
    
    async def list_length(self, key: str) -> int:
        return len(self._lists.get(key, []))


class MemorySubscription(DistributedSubscription):
    """内存订阅实现"""
    
    def __init__(self, queue: asyncio.Queue, channel: str, channels_dict: Dict):
        self._queue = queue
        self._channel = channel
        self._channels_dict = channels_dict
    
    async def get_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    async def unsubscribe(self):
        if self._channel in self._channels_dict:
            try:
                self._channels_dict[self._channel].remove(self._queue)
            except ValueError:
                pass


_distributed_store: Optional[DistributedStateStore] = None


def get_distributed_store() -> DistributedStateStore:
    """获取分布式存储实例"""
    global _distributed_store
    if _distributed_store is None:
        import os
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            _distributed_store = RedisStateStore(redis_url)
        else:
            _distributed_store = MemoryDistributedStore()
    return _distributed_store


def set_distributed_store(store: DistributedStateStore):
    """设置分布式存储实例"""
    global _distributed_store
    _distributed_store = store


__all__ = [
    "DistributedStateStore",
    "DistributedSubscription",
    "RedisStateStore",
    "RedisSubscription",
    "MemoryDistributedStore",
    "MemorySubscription",
    "get_distributed_store",
    "set_distributed_store",
]