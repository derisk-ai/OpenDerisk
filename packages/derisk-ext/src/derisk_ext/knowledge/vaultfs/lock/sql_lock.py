"""SQL advisory lock for DistributedVaultFS.

Wraps `SQLAlchemyRelationalStore.acquire_advisory_lock` /
`release_advisory_lock` so `DistributedVaultFS._acquire_distributed_lock`
can stay backend-agnostic.

- Postgres: `pg_try_advisory_lock(int)` polled until acquired; released
  via `pg_advisory_unlock(int)`.
- MySQL: `GET_LOCK(name, timeout)` returns 1 on success; released via
  `RELEASE_LOCK(name)`.

The handle returned is `(kind, key)` — opaque to callers, meaningful
only to `release`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SQLAdvisoryLock:
    """Cross-process advisory lock backed by a SQLAlchemyRelationalStore.

    Shares the store's engine — no separate connection pool.
    """

    def __init__(self, store):
        self._store = store

    async def acquire(self, space_id: str, timeout: int = 30) -> Optional[Any]:
        """Try to acquire the lock. Return handle on success, None on timeout."""
        return await self._store.acquire_advisory_lock(space_id, timeout)

    async def release(self, handle: Any) -> None:
        if handle is None:
            return
        await self._store.release_advisory_lock(handle)
