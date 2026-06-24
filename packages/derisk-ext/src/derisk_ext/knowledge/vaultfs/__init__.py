"""VaultFS implementations for the knowledge module.

LocalVaultFS: FS + SQLite + LanceDB (single-machine service mode)
DistributedVaultFS: S3 + Postgres/MySQL + pgvector (multi-tenant service mode)
"""

from derisk_ext.knowledge.vaultfs.local import LocalVaultFS
from derisk_ext.knowledge.vaultfs.distributed import DistributedVaultFS

__all__ = ["LocalVaultFS", "DistributedVaultFS"]
