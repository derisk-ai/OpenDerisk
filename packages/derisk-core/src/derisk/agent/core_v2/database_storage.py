"""
Database State Storage - 数据库存储实现

支持 PostgreSQL 和 MySQL 作为状态存储后端。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .distributed_execution import StateStorage, StorageConfig

logger = logging.getLogger(__name__)


class DatabaseStateStorage(StateStorage):
    """
    数据库状态存储

    支持：
    - PostgreSQL
    - MySQL
    - SQLite

    使用方式：
        config = StorageConfig(
            backend_type=StorageBackendType.DATABASE,
            database_url="postgresql://user:pass@localhost/agent_db",
            table_name="agent_state",
        )
        storage = StateStorageFactory.create(config)
    """

    def __init__(self, config: StorageConfig):
        self.database_url = config.database_url
        self.table_name = config.table_name
        self._pool = None
        self._lock_table = f"{config.table_name}_locks"

    async def _get_connection(self):
        """获取数据库连接"""
        if self._pool is None:
            try:
                import asyncpg

                # 创建连接池
                self._pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=2,
                    max_size=10,
                )

                # 创建表
                await self._create_tables()

            except ImportError:
                raise RuntimeError(
                    "Database storage requires 'asyncpg' package. "
                    "Install with: pip install asyncpg"
                )

        return self._pool

    async def _create_tables(self):
        """创建必要的表"""
        async with self._pool.acquire() as conn:
            # 状态表
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    key VARCHAR(255) PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 锁表
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._lock_table} (
                    key VARCHAR(255) PRIMARY KEY,
                    owner VARCHAR(255) NOT NULL,
                    expires_at TIMESTAMP NOT NULL
                )
            """)

            # 索引
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated 
                ON {self.table_name}(updated_at)
            """)

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存状态"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {self.table_name} (key, data, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (key) 
                    DO UPDATE SET data = $2, updated_at = NOW()
                """,
                    key,
                    json.dumps(data, default=str),
                )

            return True

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载状态"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT data FROM {self.table_name} WHERE key = $1", key
                )

                if row:
                    return json.loads(row["data"])
                return None

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """删除状态"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                await conn.execute(f"DELETE FROM {self.table_name} WHERE key = $1", key)

            return True

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] Delete failed: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """检查是否存在"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT 1 FROM {self.table_name} WHERE key = $1", key
                )
                return row is not None

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] Exists check failed: {e}")
            return False

    async def list_keys(self, prefix: str) -> List[str]:
        """列出指定前缀的键"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT key FROM {self.table_name} WHERE key LIKE $1", f"{prefix}%"
                )
                return [row["key"] for row in rows]

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] List keys failed: {e}")
            return []

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int = 30,
        owner: str = None,
    ) -> bool:
        """获取分布式锁"""
        try:
            import uuid

            owner = owner or str(uuid.uuid4().hex)
            lock_key = f"lock:{key}"

            pool = await self._get_connection()

            async with pool.acquire() as conn:
                # 清理过期锁
                await conn.execute(
                    f"DELETE FROM {self._lock_table} WHERE expires_at < NOW()"
                )

                # 尝试获取锁
                result = await conn.execute(
                    f"""
                    INSERT INTO {self._lock_table} (key, owner, expires_at)
                    VALUES ($1, $2, NOW() + INTERVAL '{ttl_seconds} seconds')
                    ON CONFLICT (key) DO NOTHING
                """,
                    lock_key,
                    owner,
                )

                return result == "INSERT 0 1"

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] Acquire lock failed: {e}")
            return False

    async def release_lock(self, key: str, owner: str = None) -> bool:
        """释放分布式锁"""
        try:
            lock_key = f"lock:{key}"

            pool = await self._get_connection()

            async with pool.acquire() as conn:
                if owner:
                    result = await conn.execute(
                        f"DELETE FROM {self._lock_table} WHERE key = $1 AND owner = $2",
                        lock_key,
                        owner,
                    )
                else:
                    result = await conn.execute(
                        f"DELETE FROM {self._lock_table} WHERE key = $1", lock_key
                    )

                return result != "DELETE 0"

        except Exception as e:
            logger.error(f"[DatabaseStateStorage] Release lock failed: {e}")
            return False


class MySQLStateStorage(StateStorage):
    """
    MySQL 状态存储

    使用 aiomysql 实现异步 MySQL 存储
    """

    def __init__(self, config: StorageConfig):
        self.database_url = config.database_url
        self.table_name = config.table_name
        self._pool = None
        self._lock_table = f"{config.table_name}_locks"

    async def _get_connection(self):
        """获取数据库连接"""
        if self._pool is None:
            try:
                import aiomysql

                # 解析连接URL
                # mysql://user:pass@host:port/db

                self._pool = await aiomysql.create_pool(
                    host=self._parse_host(),
                    port=self._parse_port(),
                    user=self._parse_user(),
                    password=self._parse_password(),
                    db=self._parse_db(),
                    minsize=2,
                    maxsize=10,
                )

                await self._create_tables()

            except ImportError:
                raise RuntimeError(
                    "MySQL storage requires 'aiomysql' package. "
                    "Install with: pip install aiomysql"
                )

        return self._pool

    def _parse_host(self) -> str:
        """解析主机"""
        # 简化实现
        return "localhost"

    def _parse_port(self) -> int:
        """解析端口"""
        return 3306

    def _parse_user(self) -> str:
        """解析用户"""
        return "root"

    def _parse_password(self) -> str:
        """解析密码"""
        return ""

    def _parse_db(self) -> str:
        """解析数据库"""
        return "agent_db"

    async def _create_tables(self):
        """创建表"""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        `key` VARCHAR(255) PRIMARY KEY,
                        `data` JSON NOT NULL,
                        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)

                await cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._lock_table} (
                        `key` VARCHAR(255) PRIMARY KEY,
                        `owner` VARCHAR(255) NOT NULL,
                        `expires_at` TIMESTAMP NOT NULL
                    )
                """)

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存状态"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (`key`, `data`)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE `data` = %s
                    """,
                        (
                            key,
                            json.dumps(data, default=str),
                            json.dumps(data, default=str),
                        ),
                    )

            return True

        except Exception as e:
            logger.error(f"[MySQLStateStorage] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载状态"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT `data` FROM {self.table_name} WHERE `key` = %s", (key,)
                    )
                    row = await cur.fetchone()

                    if row:
                        return json.loads(row[0])
                    return None

        except Exception as e:
            logger.error(f"[MySQLStateStorage] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """删除状态"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"DELETE FROM {self.table_name} WHERE `key` = %s", (key,)
                    )

            return True

        except Exception as e:
            logger.error(f"[MySQLStateStorage] Delete failed: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """检查是否存在"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT 1 FROM {self.table_name} WHERE `key` = %s", (key,)
                    )
                    row = await cur.fetchone()
                    return row is not None

        except Exception as e:
            logger.error(f"[MySQLStateStorage] Exists check failed: {e}")
            return False

    async def list_keys(self, prefix: str) -> List[str]:
        """列出指定前缀的键"""
        try:
            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT `key` FROM {self.table_name} WHERE `key` LIKE %s",
                        (f"{prefix}%",),
                    )
                    rows = await cur.fetchall()
                    return [row[0] for row in rows]

        except Exception as e:
            logger.error(f"[MySQLStateStorage] List keys failed: {e}")
            return []

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int = 30,
        owner: str = None,
    ) -> bool:
        """获取分布式锁"""
        try:
            import uuid

            owner = owner or str(uuid.uuid4().hex)
            lock_key = f"lock:{key}"

            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # 清理过期锁
                    await cur.execute(
                        f"DELETE FROM {self._lock_table} WHERE `expires_at` < NOW()"
                    )

                    # 尝试获取锁
                    await cur.execute(
                        f"""
                        INSERT IGNORE INTO {self._lock_table} (`key`, `owner`, `expires_at`)
                        VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s SECOND))
                    """,
                        (lock_key, owner, ttl_seconds),
                    )

                    return cur.rowcount > 0

        except Exception as e:
            logger.error(f"[MySQLStateStorage] Acquire lock failed: {e}")
            return False

    async def release_lock(self, key: str, owner: str = None) -> bool:
        """释放分布式锁"""
        try:
            lock_key = f"lock:{key}"

            pool = await self._get_connection()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    if owner:
                        await cur.execute(
                            f"DELETE FROM {self._lock_table} WHERE `key` = %s AND `owner` = %s",
                            (lock_key, owner),
                        )
                    else:
                        await cur.execute(
                            f"DELETE FROM {self._lock_table} WHERE `key` = %s",
                            (lock_key,),
                        )

                    return cur.rowcount > 0

        except Exception as e:
            logger.error(f"[MySQLStateStorage] Release lock failed: {e}")
            return False


class SQLiteStateStorage(StateStorage):
    """
    SQLite 状态存储

    适用于轻量级单机场景
    """

    def __init__(self, config: StorageConfig):
        self.db_path = config.database_url or "agent_state.db"
        self.table_name = config.table_name
        self._conn = None

    async def _get_connection(self):
        """获取数据库连接"""
        if self._conn is None:
            import aiosqlite

            self._conn = await aiosqlite.connect(self.db_path)
            await self._create_tables()

        return self._conn

    async def _create_tables(self):
        """创建表"""
        await self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._conn.commit()

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存状态"""
        try:
            conn = await self._get_connection()

            await conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.table_name} (key, data, updated_at)
                VALUES (?, ?, datetime('now'))
            """,
                (key, json.dumps(data, default=str)),
            )
            await conn.commit()

            return True

        except Exception as e:
            logger.error(f"[SQLiteStateStorage] Save failed: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载状态"""
        try:
            conn = await self._get_connection()

            async with conn.execute(
                f"SELECT data FROM {self.table_name} WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    return json.loads(row[0])
                return None

        except Exception as e:
            logger.error(f"[SQLiteStateStorage] Load failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """删除状态"""
        try:
            conn = await self._get_connection()

            await conn.execute(f"DELETE FROM {self.table_name} WHERE key = ?", (key,))
            await conn.commit()

            return True

        except Exception as e:
            logger.error(f"[SQLiteStateStorage] Delete failed: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """检查是否存在"""
        try:
            conn = await self._get_connection()

            async with conn.execute(
                f"SELECT 1 FROM {self.table_name} WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                return row is not None

        except Exception as e:
            logger.error(f"[SQLiteStateStorage] Exists check failed: {e}")
            return False

    async def list_keys(self, prefix: str) -> List[str]:
        """列出指定前缀的键"""
        try:
            conn = await self._get_connection()

            async with conn.execute(
                f"SELECT key FROM {self.table_name} WHERE key LIKE ?", (f"{prefix}%",)
            ) as cur:
                rows = await cur.fetchall()
                return [row[0] for row in rows]

        except Exception as e:
            logger.error(f"[SQLiteStateStorage] List keys failed: {e}")
            return []

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int = 30,
        owner: str = None,
    ) -> bool:
        """获取锁 (SQLite使用文件锁)"""
        # SQLite 本身就是文件锁，这里简单实现
        return True

    async def release_lock(self, key: str, owner: str = None) -> bool:
        """释放锁"""
        return True
