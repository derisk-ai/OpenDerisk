"""StateStore——V2 Runtime 持久化接口。

P0 实现 DbStateStore（SQLite，stdlib sqlite3 + asyncio.to_thread）。
后续阶段加 RedisStateStore / HybridStateStore。
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


class StateStore(ABC):
    """持久化接口。所有方法是 async。"""

    @abstractmethod
    async def append_event(self, event: StepEvent) -> None: ...

    @abstractmethod
    async def get_events(self, conv_id: str, since_seq: int = 0) -> List[StepEvent]: ...

    @abstractmethod
    async def get_step_state(self, step_id: str) -> Optional[Tuple[StepState, dict]]: ...

    @abstractmethod
    async def set_step_state(
        self, step_id: str, conv_id: str, state: StepState, snapshot: dict
    ) -> None: ...

    @abstractmethod
    async def acquire_lease(self, conv_id: str, agent_id: str, ttl_seconds: int) -> bool: ...

    @abstractmethod
    async def renew_lease(self, conv_id: str, agent_id: str, ttl_seconds: int) -> bool: ...

    @abstractmethod
    async def release_lease(self, conv_id: str) -> None: ...

    @abstractmethod
    async def scan_expired_leases(self) -> List[str]: ...

    @abstractmethod
    async def save_interaction_checkpoint(
        self, request_id: str, step_id: str, conv_id: str, request_payload: dict
    ) -> None: ...

    @abstractmethod
    async def get_interaction_checkpoint(self, request_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def delete_interaction_checkpoint(self, request_id: str) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS step_event (
    event_id TEXT PRIMARY KEY,
    step_id TEXT NOT NULL,
    conv_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    parent_step_id TEXT,
    state TEXT NOT NULL,
    event_type TEXT NOT NULL,
    input TEXT,
    output TEXT,
    seq INTEGER NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_step_event_conv_seq ON step_event(conv_id, seq);

CREATE TABLE IF NOT EXISTS step_state (
    step_id TEXT PRIMARY KEY,
    conv_id TEXT NOT NULL,
    state TEXT NOT NULL,
    snapshot TEXT,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_step_state_conv ON step_state(conv_id);

CREATE TABLE IF NOT EXISTS agent_lease (
    conv_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    lease_expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lease_expires ON agent_lease(lease_expires_at);

CREATE TABLE IF NOT EXISTS interaction_checkpoint (
    request_id TEXT PRIMARY KEY,
    step_id TEXT NOT NULL,
    conv_id TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_conv ON interaction_checkpoint(conv_id);
"""


class DbStateStore(StateStore):
    """SQLite 实现。同步 sqlite3 调用全部包 asyncio.to_thread。"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def append_event(self, event: StepEvent) -> None:
        def _do():
            conn = self._connect()
            try:
                d = event.to_storage_dict()
                # INSERT (not INSERT OR REPLACE) 强制 append-only：
                # event_id 是 UUID，碰撞概率≈0；若碰撞应报错而非覆盖
                conn.execute(
                    "INSERT INTO step_event "
                    "(event_id, step_id, conv_id, agent_id, parent_step_id, state, "
                    " event_type, input, output, seq, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (d["event_id"], d["step_id"], d["conv_id"], d["agent_id"],
                     d["parent_step_id"], d["state"], d["event_type"],
                     d["input"], d["output"], d["seq"], d["timestamp"]),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)

    async def get_events(self, conv_id: str, since_seq: int = 0) -> List[StepEvent]:
        def _do():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM step_event WHERE conv_id = ? AND seq >= ? "
                    "ORDER BY seq ASC",
                    (conv_id, since_seq),
                ).fetchall()
                return [StepEvent.from_storage_dict(dict(r)) for r in rows]
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def get_step_state(self, step_id: str) -> Optional[Tuple[StepState, dict]]:
        def _do():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT state, snapshot FROM step_state WHERE step_id = ?",
                    (step_id,),
                ).fetchone()
                if not row:
                    return None
                return StepState(row["state"]), json.loads(row["snapshot"] or "{}")
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def set_step_state(
        self, step_id: str, conv_id: str, state: StepState, snapshot: dict
    ) -> None:
        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO step_state "
                    "(step_id, conv_id, state, snapshot, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (step_id, conv_id, state.value, json.dumps(snapshot), time.time()),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)

    async def acquire_lease(self, conv_id: str, agent_id: str, ttl_seconds: int) -> bool:
        def _do():
            conn = self._connect()
            try:
                now = time.time()
                expires = now + ttl_seconds
                # 若无 lease 或已过期，抢到
                row = conn.execute(
                    "SELECT agent_id, lease_expires_at FROM agent_lease WHERE conv_id = ?",
                    (conv_id,),
                ).fetchone()
                if row is None or row["lease_expires_at"] < now:
                    conn.execute(
                        "INSERT OR REPLACE INTO agent_lease "
                        "(conv_id, agent_id, lease_expires_at) VALUES (?, ?, ?)",
                        (conv_id, agent_id, expires),
                    )
                    conn.commit()
                    return True
                if row["agent_id"] == agent_id:
                    conn.execute(
                        "UPDATE agent_lease SET lease_expires_at = ? WHERE conv_id = ?",
                        (expires, conv_id),
                    )
                    conn.commit()
                    return True
                return False
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def renew_lease(self, conv_id: str, agent_id: str, ttl_seconds: int) -> bool:
        return await self.acquire_lease(conv_id, agent_id, ttl_seconds)

    async def release_lease(self, conv_id: str) -> None:
        def _do():
            conn = self._connect()
            try:
                conn.execute("DELETE FROM agent_lease WHERE conv_id = ?", (conv_id,))
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)

    async def scan_expired_leases(self) -> List[str]:
        def _do():
            conn = self._connect()
            try:
                now = time.time()
                rows = conn.execute(
                    "SELECT conv_id FROM agent_lease WHERE lease_expires_at < ?",
                    (now,),
                ).fetchall()
                return [r["conv_id"] for r in rows]
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def save_interaction_checkpoint(
        self, request_id: str, step_id: str, conv_id: str, request_payload: dict
    ) -> None:
        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO interaction_checkpoint "
                    "(request_id, step_id, conv_id, request_payload, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (request_id, step_id, conv_id,
                     json.dumps(request_payload, ensure_ascii=False), time.time()),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)

    async def get_interaction_checkpoint(self, request_id: str) -> Optional[dict]:
        def _do():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT request_id, step_id, conv_id, request_payload, created_at "
                    "FROM interaction_checkpoint WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if not row:
                    return None
                d = dict(row)
                d["request_payload"] = json.loads(d["request_payload"])
                return d
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def delete_interaction_checkpoint(self, request_id: str) -> None:
        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM interaction_checkpoint WHERE request_id = ?",
                    (request_id,),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)
