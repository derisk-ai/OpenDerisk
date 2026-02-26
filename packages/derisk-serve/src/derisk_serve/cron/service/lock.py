"""Distributed lock implementations.

This module provides lock implementations for coordinating cron job execution.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional

from derisk.cron import DistributedLock


class MemoryLock(DistributedLock):
    """In-memory lock implementation for single-instance deployment.

    This lock uses asyncio.Lock internally and is suitable for single-instance
    deployments. For multi-instance deployments, use a Redis-based lock instead.
    """

    def __init__(self):
        """Initialize the memory lock."""
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_times: Dict[str, float] = {}
        self._cleanup_interval: float = 60.0  # Cleanup old locks every 60 seconds
        self._last_cleanup: float = time.time()

    def _cleanup_old_locks(self) -> None:
        """Clean up locks that haven't been used recently."""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return

        # Remove locks that were released more than 5 minutes ago
        cleanup_threshold = current_time - 300
        keys_to_remove = [
            key for key, lock_time in self._lock_times.items()
            if lock_time < cleanup_threshold and key not in self._locks
        ]
        for key in keys_to_remove:
            del self._lock_times[key]

        self._last_cleanup = current_time

    @asynccontextmanager
    async def acquire(
        self, key: str, timeout: float = 30.0
    ) -> AsyncIterator[bool]:
        """Attempt to acquire a lock.

        This implementation uses asyncio.Lock which provides mutual exclusion
        within a single process. It does not provide any timeout mechanism
        for automatic release - the lock holder must release it explicitly.

        Args:
            key: The unique key for the lock.
            timeout: This parameter is accepted for API compatibility but
                not enforced in the memory lock implementation.

        Yields:
            bool: True if the lock was acquired (always True for memory lock).
        """
        self._cleanup_old_locks()

        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            self._lock_times[key] = time.time()
            yield True
            # Lock is automatically released when exiting the context


# Redis lock implementation placeholder for future multi-instance support
# This would require additional dependencies like redis-py
#
# class RedisLock(DistributedLock):
#     """Redis-based distributed lock for multi-instance deployment.
#
#     This lock uses Redis SET with NX and EX flags to implement a
#     distributed lock that works across multiple service instances.
#     """
#
#     def __init__(self, redis_client, key_prefix: str = "derisk:cron:lock:"):
#         """Initialize the Redis lock.
#
#         Args:
#             redis_client: The Redis client instance.
#             key_prefix: Prefix for all lock keys.
#         """
#         self._redis = redis_client
#         self._key_prefix = key_prefix
#         self._lock_value = str(uuid.uuid4())
#
#     @asynccontextmanager
#     async def acquire(
#         self, key: str, timeout: float = 30.0
#     ) -> AsyncIterator[bool]:
#         """Attempt to acquire a lock using Redis.
#
#         Args:
#             key: The unique key for the lock.
#             timeout: Lock expiration time in seconds.
#
#         Yields:
#             bool: True if the lock was acquired, False otherwise.
#         """
#         full_key = f"{self._key_prefix}{key}"
#         acquired = await self._redis.set(
#             full_key, self._lock_value, nx=True, ex=int(timeout)
#         )
#         try:
#             yield bool(acquired)
#         finally:
#             # Only release if we own the lock
#             script = """
#             if redis.call("get", KEYS[1]) == ARGV[1] then
#                 return redis.call("del", KEYS[1])
#             else
#                 return 0
#             end
#             """
#             await self._redis.eval(script, [full_key], [self._lock_value])