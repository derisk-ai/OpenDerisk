"""Distributed lock interface for cron job coordination.

This module defines the interface for distributed locks used to coordinate
cron job execution across multiple instances in a distributed deployment.
"""

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator


class DistributedLock(ABC):
    """Abstract interface for distributed locks.

    This interface provides a way to acquire locks that can coordinate
    cron job execution across multiple instances. Implementations should
    support different backends (in-memory, Redis, database, etc.).

    The lock is designed to be used as an async context manager:

    Example:
        ```python
        lock = MemoryLock()  # or RedisLock(redis_client)
        async with lock.acquire("cron:job-123") as acquired:
            if acquired:
                # Execute the job
                ...
            else:
                # Another instance is running the job
                ...
        ```
    """

    @abstractmethod
    @asynccontextmanager
    async def acquire(
        self, key: str, timeout: float = 30.0
    ) -> AsyncIterator[bool]:
        """Attempt to acquire a lock.

        This is an async context manager that yields True if the lock
        was acquired, False otherwise. The lock is automatically released
        when the context exits.

        Args:
            key: The unique key for the lock.
            timeout: The maximum time to hold the lock in seconds.
                After this time, the lock should be automatically released
                to prevent deadlocks from crashed processes.

        Yields:
            bool: True if the lock was acquired, False otherwise.
        """
        yield False