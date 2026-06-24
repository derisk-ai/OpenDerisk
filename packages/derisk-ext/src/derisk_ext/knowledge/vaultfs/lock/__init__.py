"""Distributed lock backends for DistributedVaultFS."""

from derisk_ext.knowledge.vaultfs.lock.sql_lock import SQLAdvisoryLock

__all__ = ["SQLAdvisoryLock"]
