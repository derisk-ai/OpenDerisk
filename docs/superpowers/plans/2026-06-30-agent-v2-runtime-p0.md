# Agent V2 Runtime — P0 内核骨架 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 V2 Runtime 内核骨架——StepState 状态机 + StepEvent 事件溯源 + EventStream（AsyncGenerator）+ StateStore（DbStateStore/SQLite）+ 崩溃恢复（lease + replay），可在无 LLM 的测试桩下端到端跑通"跑一步→kill→续接"。

**Architecture:** 新建 `derisk/agent/core/v2/` 包，六件套中的四件（StepState/EventStream/StateStore/Recovery）+ `run_step()` 入口。`run_step` 接受可注入的 `thinking_fn`/`acting_fn` 回调以支持无 LLM 测试。StateStore 用 stdlib `sqlite3` + `asyncio.to_thread` 实现，零新外部依赖。本计划是 spec（`docs/superpowers/specs/2026-06-30-agent-framework-evolution-design.md`）的 P0 阶段；P1（Permission Gate）/P2（SubAgent）/P3（事件流统一）/P4（清理）另行计划。

**Tech Stack:** Python ≥3.10, pydantic v2, stdlib sqlite3 + asyncio.to_thread, pytest。不引入 Redis/aiosqlite（P0 范围外）。

## Global Constraints

- **Python ≥ 3.10**（pyproject.toml 已声明）。
- **pydantic ≥ 2.6**（pyproject.toml 已声明）——所有数据模型用 `BaseModel`，序列化用 `model_to_dict`。
- **不新增第三方依赖**——P0 只用 stdlib（`sqlite3`、`asyncio`、`uuid`、`time`、`json`）+ 已有 pydantic。
- **异步接口**——所有 StateStore/EventStream/Recovery 方法是 `async def`；sqlite3 同步调用必须包 `asyncio.to_thread`。
- **测试用 pytest**——测试文件放 `packages/derisk-core/tests/agent/core/v2/`，命名 `test_*.py`。
- **不修改现有 `RecoveryCoordinator`/`interaction_gateway.py`/`base_agent.py`**——P0 只新建文件，不动老代码（避免双轨期污染）。
- **append-only 语义**——`step_event` 表只插入不更新；`step_state` 表可更新（最新状态）。
- **seq 单调递增**——同一 `conv_id` 内 `seq` 严格递增，由 `EventStream` 分配，不依赖 DB 自增。

## File Structure

新建文件（P0 范围）：

| 文件 | 职责 |
|---|---|
| `packages/derisk-core/src/derisk/agent/core/v2/__init__.py` | 包初始化 + 公开 API 导出 |
| `packages/derisk-core/src/derisk/agent/core/v2/step_state.py` | `StepState` 枚举 + 状态转换规则 + 校验函数 |
| `packages/derisk-core/src/derisk/agent/core/v2/step_event.py` | `StepEvent` pydantic 模型 + 序列化 |
| `packages/derisk-core/src/derisk/agent/core/v2/state_store.py` | `StateStore` ABC + `DbStateStore`（SQLite 实现） |
| `packages/derisk-core/src/derisk/agent/core/v2/event_stream.py` | `EventStream`：AsyncGenerator 包装器，每个 yield 前持久化 |
| `packages/derisk-core/src/derisk/agent/core/v2/recovery.py` | `RecoveryCoordinatorV2`：lease 管理 + 重放恢复 |
| `packages/derisk-core/src/derisk/agent/core/v2/runtime.py` | `run_step()` AsyncGenerator 入口 |
| `packages/derisk-core/tests/agent/core/v2/__init__.py` | 测试包 |
| `packages/derisk-core/tests/agent/core/v2/test_step_state.py` | Task 1 测试 |
| `packages/derisk-core/tests/agent/core/v2/test_step_event.py` | Task 2 测试 |
| `packages/derisk-core/tests/agent/core/v2/test_state_store.py` | Task 3 测试 |
| `packages/derisk-core/tests/agent/core/v2/test_event_stream.py` | Task 4 测试 |
| `packages/derisk-core/tests/agent/core/v2/test_recovery.py` | Task 5 测试 |
| `packages/derisk-core/tests/agent/core/v2/test_runtime.py` | Task 6 测试 |

---

### Task 1: StepState 枚举 + 状态转换校验

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/step_state.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_step_state.py`

**Interfaces:**
- Produces: `StepState`（Enum）、`VALID_TRANSITIONS`（dict）、`validate_transition(from: StepState, to: StepState) -> bool`、`IllegalTransitionError`（Exception）

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_step_state.py
import pytest
from derisk.agent.core.v2.step_state import (
    StepState,
    validate_transition,
    IllegalTransitionError,
)


def test_step_state_members():
    assert StepState.INIT.value == "init"
    assert StepState.THINKING.value == "thinking"
    assert StepState.ACTING.value == "acting"
    assert StepState.OBSERVING.value == "observing"
    assert StepState.AWAITING_USER.value == "awaiting_user"
    assert StepState.AWAITING_TOOL_PERMISSION.value == "awaiting_tool_permission"
    assert StepState.AWAITING_SUB_AGENT.value == "awaiting_sub_agent"
    assert StepState.DONE.value == "done"
    assert StepState.FAILED.value == "failed"


def test_legal_transitions():
    assert validate_transition(StepState.INIT, StepState.THINKING) is True
    assert validate_transition(StepState.THINKING, StepState.ACTING) is True
    assert validate_transition(StepState.ACTING, StepState.OBSERVING) is True
    assert validate_transition(StepState.OBSERVING, StepState.THINKING) is True
    assert validate_transition(StepState.THINKING, StepState.AWAITING_USER) is True
    assert validate_transition(StepState.AWAITING_USER, StepState.THINKING) is True
    assert validate_transition(StepState.ACTING, StepState.AWAITING_TOOL_PERMISSION) is True
    assert validate_transition(StepState.AWAITING_TOOL_PERMISSION, StepState.ACTING) is True
    assert validate_transition(StepState.ACTING, StepState.AWAITING_SUB_AGENT) is True
    assert validate_transition(StepState.AWAITING_SUB_AGENT, StepState.OBSERVING) is True
    assert validate_transition(StepState.THINKING, StepState.DONE) is True
    assert validate_transition(StepState.ACTING, StepState.FAILED) is True


def test_illegal_transitions():
    assert validate_transition(StepState.INIT, StepState.DONE) is False
    assert validate_transition(StepState.DONE, StepState.THINKING) is False
    assert validate_transition(StepState.AWAITING_USER, StepState.DONE) is False
    assert validate_transition(StepState.FAILED, StepState.THINKING) is False


def test_awaiting_states_reachable_from_thinking_or_acting():
    # 所有 AWAITING_* 必须从 THINKING 或 ACTING 可达
    for awaiting in [
        StepState.AWAITING_USER,
        StepState.AWAITING_TOOL_PERMISSION,
        StepState.AWAITING_SUB_AGENT,
    ]:
        assert validate_transition(StepState.THINKING, awaiting) is True or \
               validate_transition(StepState.ACTING, awaiting) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_step_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2'`

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/step_state.py
"""StepState 状态机——V2 Runtime 显式状态枚举。

替代散落的 Status 枚举 + received_message_state + RuntimeContext.recovering。
每个 AWAITING_* 状态都是可持久化挂起的——进程重启后能从 StateStore 恢复。
"""
from __future__ import annotations
from enum import Enum
from typing import Dict, Tuple


class StepState(Enum):
    INIT = "init"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    AWAITING_USER = "awaiting_user"
    AWAITING_TOOL_PERMISSION = "awaiting_tool_permission"
    AWAITING_SUB_AGENT = "awaiting_sub_agent"
    DONE = "done"
    FAILED = "failed"


class IllegalTransitionError(Exception):
    """非法状态转换。"""


VALID_TRANSITIONS: Dict[StepState, Tuple[StepState, ...]] = {
    StepState.INIT: (StepState.THINKING,),
    StepState.THINKING: (
        StepState.ACTING,
        StepState.AWAITING_USER,
        StepState.DONE,
        StepState.FAILED,
    ),
    StepState.ACTING: (
        StepState.OBSERVING,
        StepState.AWAITING_TOOL_PERMISSION,
        StepState.AWAITING_SUB_AGENT,
        StepState.FAILED,
    ),
    StepState.OBSERVING: (StepState.THINKING, StepState.DONE, StepState.FAILED),
    StepState.AWAITING_USER: (StepState.THINKING, StepState.FAILED),
    StepState.AWAITING_TOOL_PERMISSION: (StepState.ACTING, StepState.FAILED),
    StepState.AWAITING_SUB_AGENT: (StepState.OBSERVING, StepState.FAILED),
    StepState.DONE: (),
    StepState.FAILED: (),
}


def validate_transition(from_state: StepState, to_state: StepState) -> bool:
    """检查状态转换是否合法。"""
    return to_state in VALID_TRANSITIONS.get(from_state, ())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_step_state.py -v`
Expected: PASS（4 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/step_state.py \
        packages/derisk-core/tests/agent/core/v2/__init__.py \
        packages/derisk-core/tests/agent/core/v2/test_step_state.py
git commit -m "feat(agent-v2): StepState 状态机 + 转换校验"
```

---

### Task 2: StepEvent pydantic 模型

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/step_event.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_step_event.py`

**Interfaces:**
- Consumes: `StepState`（from Task 1）
- Produces: `StepEvent`（pydantic BaseModel），字段：`event_id: str`、`step_id: str`、`conv_id: str`、`agent_id: str`、`parent_step_id: str | None`、`state: StepState`、`event_type: str`、`input: dict`、`output: dict`、`seq: int`、`timestamp: float`。方法：`to_storage_dict() -> dict`、`from_storage_dict(d: dict) -> StepEvent`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_step_event.py
import pytest
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


def test_step_event_fields():
    event = StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.THINKING,
        event_type="llm_token",
        input={"prompt": "hi"},
        output={"token": "hello"},
        seq=0,
        timestamp=1000.0,
    )
    assert event.event_id == "evt-1"
    assert event.state == StepState.THINKING
    assert event.seq == 0


def test_step_event_storage_roundtrip():
    event = StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id="step-0",
        state=StepState.ACTING,
        event_type="tool_call",
        input={"tool": "read_file"},
        output={},
        seq=5,
        timestamp=1000.0,
    )
    d = event.to_storage_dict()
    assert d["state"] == "acting"  # 枚举序列化为字符串
    restored = StepEvent.from_storage_dict(d)
    assert restored == event
    assert restored.state == StepState.ACTING


def test_step_event_parent_step_id_optional():
    event = StepEvent(
        event_id="evt-2",
        step_id="step-2",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.INIT,
        event_type="step_init",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    )
    assert event.parent_step_id is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_step_event.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.step_event'`

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/step_event.py
"""StepEvent——event sourcing 最小单元。

append-only：一旦写入不可修改。一个 step 产出多个 StepEvent
（thinking 阶段多个 llm_token，acting 阶段 tool_call + tool_result）。
"""
from __future__ import annotations
from typing import Any, Optional
from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict
from derisk.agent.core.v2.step_state import StepState


class StepEvent(BaseModel):
    model_config = ConfigDict(
        title="StepEvent",
        use_enum_values=False,
        arbitrary_types_allowed=True,
    )

    event_id: str
    step_id: str
    conv_id: str
    agent_id: str
    parent_step_id: Optional[str] = None
    state: StepState
    event_type: str
    input: dict = {}
    output: dict = {}
    seq: int
    timestamp: float

    def to_storage_dict(self) -> dict:
        """序列化为可存入 DB 的 dict（枚举转字符串）。"""
        d = model_to_dict(self)
        d["state"] = self.state.value
        d["input"] = __import__("json").dumps(self.input)
        d["output"] = __import__("json").dumps(self.output)
        d["parent_step_id"] = self.parent_step_id
        return d

    @staticmethod
    def from_storage_dict(d: dict) -> "StepEvent":
        """从 DB 行反序列化。"""
        import json
        return StepEvent(
            event_id=d["event_id"],
            step_id=d["step_id"],
            conv_id=d["conv_id"],
            agent_id=d["agent_id"],
            parent_step_id=d.get("parent_step_id"),
            state=StepState(d["state"]),
            event_type=d["event_type"],
            input=json.loads(d["input"]) if d.get("input") else {},
            output=json.loads(d["output"]) if d.get("output") else {},
            seq=d["seq"],
            timestamp=d["timestamp"],
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_step_event.py -v`
Expected: PASS（3 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/step_event.py \
        packages/derisk-core/tests/agent/core/v2/test_step_event.py
git commit -m "feat(agent-v2): StepEvent 事件溯源数据模型"
```

---

### Task 3: StateStore 接口 + DbStateStore（SQLite）

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/state_store.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_state_store.py`

**Interfaces:**
- Consumes: `StepEvent`（from Task 2）、`StepState`（from Task 1）
- Produces: `StateStore`（ABC），方法：`append_event(event: StepEvent) -> None`、`get_events(conv_id: str, since_seq: int = 0) -> list[StepEvent]`、`get_step_state(step_id: str) -> tuple[StepState, dict] | None`、`set_step_state(step_id: str, conv_id: str, state: StepState, snapshot: dict) -> None`、`acquire_lease(conv_id: str, agent_id: str, ttl_seconds: int) -> bool`、`renew_lease(conv_id: str, agent_id: str, ttl_seconds: int) -> bool`、`release_lease(conv_id: str) -> None`、`scan_expired_leases() -> list[str]`。`DbStateStore`（SQLite 实现，构造器 `DbStateStore(db_path: str)`）

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_state_store.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_append_and_get_events_ordered(store):
    for i in range(3):
        e = StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={"i": i},
            seq=i,
            timestamp=float(i),
        )
        await store.append_event(e)
    events = await store.get_events("conv-1")
    assert len(events) == 3
    assert [e.seq for e in events] == [0, 1, 2]


async def test_get_events_since_seq(store):
    for i in range(5):
        e = StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={},
            seq=i,
            timestamp=float(i),
        )
        await store.append_event(e)
    events = await store.get_events("conv-1", since_seq=2)
    assert [e.seq for e in events] == [2, 3, 4]


async def test_set_and_get_step_state(store):
    await store.set_step_state("step-1", "conv-1", StepState.AWAITING_USER, {"input": "x"})
    result = await store.get_step_state("step-1")
    assert result is not None
    state, snapshot = result
    assert state == StepState.AWAITING_USER
    assert snapshot == {"input": "x"}


async def test_get_step_state_returns_none_if_absent(store):
    assert await store.get_step_state("nope") is None


async def test_acquire_and_renew_lease(store):
    assert await store.acquire_lease("conv-1", "agent-1", ttl_seconds=30) is True
    # 同一 conv 被同一 agent 再次 acquire 也算续期成功
    assert await store.renew_lease("conv-1", "agent-1", ttl_seconds=30) is True


async def test_acquire_lease_conflict(store):
    assert await store.acquire_lease("conv-1", "agent-1", ttl_seconds=30) is True
    # 不同 agent 在 lease 未过期时不能抢
    assert await store.acquire_lease("conv-1", "agent-2", ttl_seconds=30) is False


async def test_scan_expired_leases(store):
    await store.acquire_lease("conv-1", "agent-1", ttl_seconds=0)
    # ttl=0 立即过期
    expired = await store.scan_expired_leases()
    assert "conv-1" in expired


async def test_release_lease(store):
    await store.acquire_lease("conv-1", "agent-1", ttl_seconds=30)
    await store.release_lease("conv-1")
    assert await store.acquire_lease("conv-1", "agent-2", ttl_seconds=30) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.state_store'`

注意：若 pytest 不识别 `async def` 测试，需确认 `pytest-asyncio` 是否安装。若无，在 Task 3 开始前先在 derisk-core 的 dev 依赖里加 `pytest-asyncio` 并配置 `asyncio_mode = "auto"`。检查命令：`cd packages/derisk-core && python -c "import pytest_asyncio" 2>&1`。若报错，先执行：

```bash
cd packages/derisk-core && pip install pytest-asyncio && \
  python -c "import configparser; print('check pyproject for asyncio_mode')"
```

并在 `packages/derisk-core/pyproject.toml` 的 `[tool.pytest.ini_options]` 加 `asyncio_mode = "auto"`（若该节不存在则新增）。此步骤算作 Task 3 的前置准备，包含在本步骤内。

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/state_store.py
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store.py -v`
Expected: PASS（8 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/state_store.py \
        packages/derisk-core/tests/agent/core/v2/test_state_store.py \
        packages/derisk-core/pyproject.toml
git commit -m "feat(agent-v2): StateStore 接口 + DbStateStore(SQLite) 实现"
```

---

### Task 4: EventStream（AsyncGenerator + 持久化）

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/event_stream.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_event_stream.py`

**Interfaces:**
- Consumes: `StepEvent`（Task 2）、`StateStore`（Task 3）、`StepState`（Task 1）
- Produces: `EventStream` 类。构造器 `EventStream(state_store: StateStore)`。方法 `emit(event: StepEvent) -> StepEvent`（async，持久化后返回同一 event 供调用方 yield）。类方法 `replay(state_store, conv_id, since_seq=0) -> AsyncGenerator[StepEvent, None]`（从 StateStore 重放历史事件）

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_event_stream.py
import pytest
import tempfile
import os
import asyncio
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_emit_persists_and_returns_event(store):
    stream = EventStream(store)
    event = StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.INIT,
        event_type="step_init",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    )
    returned = await stream.emit(event)
    assert returned is event
    persisted = await store.get_events("conv-1")
    assert len(persisted) == 1
    assert persisted[0].event_id == "evt-1"


async def test_replay_yields_historical_events_in_order(store):
    stream = EventStream(store)
    for i in range(3):
        await stream.emit(StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={"i": i},
            seq=i,
            timestamp=float(i),
        ))

    # 模拟进程重启后重放
    new_stream = EventStream(store)
    events = []
    async for e in new_stream.replay("conv-1"):
        events.append(e)
    assert [e.seq for e in events] == [0, 1, 2]
    assert [e.output["i"] for e in events] == [0, 1, 2]


async def test_replay_since_seq(store):
    stream = EventStream(store)
    for i in range(5):
        await stream.emit(StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={},
            seq=i,
            timestamp=float(i),
        ))
    new_stream = EventStream(store)
    events = []
    async for e in new_stream.replay("conv-1", since_seq=3):
        events.append(e)
    assert [e.seq for e in events] == [3, 4]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_event_stream.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.event_stream'`

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/event_stream.py
"""EventStream——AsyncGenerator + 持久化。

每个 yield 前先持久化到 StateStore（durability before visibility）。
进程崩溃后通过 replay() 从 StateStore 重放历史事件。
"""
from __future__ import annotations
from typing import AsyncGenerator
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore


class EventStream:
    """事件流：持久化 + 重放。不直接 yield，由 run_step 的 async generator 驱动。"""

    def __init__(self, state_store: StateStore):
        self._store = state_store

    async def emit(self, event: StepEvent) -> StepEvent:
        """持久化事件后返回同一对象，供调用方 yield。"""
        await self._store.append_event(event)
        await self._store.set_step_state(
            event.step_id, event.conv_id, event.state, event.input
        )
        return event

    async def replay(
        self, conv_id: str, since_seq: int = 0
    ) -> AsyncGenerator[StepEvent, None]:
        """从 StateStore 重放历史事件。用于进程重启后续接。"""
        events = await self._store.get_events(conv_id, since_seq=since_seq)
        for event in events:
            yield event
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_event_stream.py -v`
Expected: PASS（3 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/event_stream.py \
        packages/derisk-core/tests/agent/core/v2/test_event_stream.py
git commit -m "feat(agent-v2): EventStream 持久化 + 重放"
```

---

### Task 5: RecoveryCoordinatorV2（lease + 重放恢复）

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/recovery.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_recovery.py`

**Interfaces:**
- Consumes: `StateStore`（Task 3）、`EventStream`（Task 4）、`StepState`（Task 1）、`StepEvent`（Task 2）
- Produces: `RecoveryCoordinatorV2` 类。构造器 `RecoveryCoordinatorV2(state_store: StateStore, lease_ttl_seconds: int = 30, renew_interval_seconds: int = 10)`。方法：
  - `async acquire_lease(conv_id: str, agent_id: str) -> bool`
  - `async renew_lease(conv_id: str, agent_id: str) -> bool`
  - `async release_lease(conv_id: str) -> None`
  - `async scan_expired() -> list[str]`
  - `async get_last_step_state(conv_id: str) -> tuple[str, StepState, dict] | None`（返回 `step_id, state, snapshot`）
  - `async replay_events(conv_id: str) -> list[StepEvent]`
  - `async decide_resume_action(conv_id: str) -> dict`（返回 `{"action": "resume_awaiting" | "redo_step" | "continue_next", "step_id": str | None, "state": StepState | None}`）

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_recovery.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.recovery import RecoveryCoordinatorV2
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def recovery():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = DbStateStore(path)
    yield RecoveryCoordinatorV2(store, lease_ttl_seconds=30), store, EventStream(store)
    os.unlink(path)


async def test_acquire_and_renew_lease(recovery):
    rc, store, stream = recovery
    assert await rc.acquire_lease("conv-1", "agent-1") is True
    assert await rc.renew_lease("conv-1", "agent-1") is True


async def test_scan_expired(recovery):
    rc, store, stream = recovery
    # 用 ttl=0 立即过期
    assert await store.acquire_lease("conv-1", "agent-1", ttl_seconds=0) is True
    expired = await rc.scan_expired()
    assert "conv-1" in expired


async def test_get_last_step_state_returns_none_when_empty(recovery):
    rc, store, stream = recovery
    assert await rc.get_last_step_state("conv-1") is None


async def test_get_last_step_state_returns_latest(recovery):
    rc, store, stream = recovery
    # 两个 step，最后一个是 AWAITING_USER
    for step_id, state, seq in [
        ("step-1", StepState.DONE, 0),
        ("step-2", StepState.AWAITING_USER, 1),
    ]:
        await stream.emit(StepEvent(
            event_id=f"evt-{step_id}",
            step_id=step_id,
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=state,
            event_type="step_init" if state == StepState.DONE else "interaction_request",
            input={"prompt": "hi"} if state == StepState.AWAITING_USER else {},
            output={},
            seq=seq,
            timestamp=float(seq),
        ))
    result = await rc.get_last_step_state("conv-1")
    assert result is not None
    step_id, state, snapshot = result
    assert step_id == "step-2"
    assert state == StepState.AWAITING_USER
    assert snapshot == {"prompt": "hi"}


async def test_decide_resume_action_awaiting(recovery):
    rc, store, stream = recovery
    await stream.emit(StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.AWAITING_USER,
        event_type="interaction_request",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    ))
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "resume_awaiting"
    assert decision["step_id"] == "step-1"
    assert decision["state"] == StepState.AWAITING_USER


async def test_decide_resume_action_redo_for_incomplete_step(recovery):
    rc, store, stream = recovery
    # step 停在 THINKING（未完成）→ 应重做
    await stream.emit(StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.THINKING,
        event_type="llm_token",
        input={"prompt": "hi"},
        output={"token": "partial"},
        seq=0,
        timestamp=0.0,
    ))
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "redo_step"
    assert decision["step_id"] == "step-1"


async def test_decide_resume_action_continue_when_done(recovery):
    rc, store, stream = recovery
    await stream.emit(StepEvent(
        event_id="evt-1",
        step_id="step-1",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.DONE,
        event_type="step_done",
        input={},
        output={},
        seq=0,
        timestamp=0.0,
    ))
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "continue_next"


async def test_replay_events(recovery):
    rc, store, stream = recovery
    for i in range(3):
        await stream.emit(StepEvent(
            event_id=f"evt-{i}",
            step_id="step-1",
            conv_id="conv-1",
            agent_id="agent-1",
            parent_step_id=None,
            state=StepState.THINKING,
            event_type="llm_token",
            input={},
            output={"i": i},
            seq=i,
            timestamp=float(i),
        ))
    events = await rc.replay_events("conv-1")
    assert [e.seq for e in events] == [0, 1, 2]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_recovery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.recovery'`

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/recovery.py
"""RecoveryCoordinatorV2——lease 管理 + 重放恢复决策。

崩溃检测：agent 运行时持有 lease（StateStore 实现），每 N 秒续期，
进程崩溃后 lease 过期，其他进程可 scan_expired 接管。

重放恢复：读 step_event 表，找最后一个 step 的 state，
- AWAITING_* → 恢复到等待状态
- THINKING/ACTING/OBSERVING → 未完成，重做该 step
- DONE → 继续下一个 step
"""
from __future__ import annotations
import time
from typing import List, Optional, Tuple, Dict, Any
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


_AWAITING_STATES = {
    StepState.AWAITING_USER,
    StepState.AWAITING_TOOL_PERMISSION,
    StepState.AWAITING_SUB_AGENT,
}
_INCOMPLETE_STATES = {
    StepState.THINKING,
    StepState.ACTING,
    StepState.OBSERVING,
    StepState.INIT,
}


class RecoveryCoordinatorV2:
    def __init__(
        self,
        state_store: StateStore,
        lease_ttl_seconds: int = 30,
        renew_interval_seconds: int = 10,
    ):
        self._store = state_store
        self._stream = EventStream(state_store)
        self.lease_ttl_seconds = lease_ttl_seconds
        self.renew_interval_seconds = renew_interval_seconds

    async def acquire_lease(self, conv_id: str, agent_id: str) -> bool:
        return await self._store.acquire_lease(conv_id, agent_id, self.lease_ttl_seconds)

    async def renew_lease(self, conv_id: str, agent_id: str) -> bool:
        return await self._store.renew_lease(conv_id, agent_id, self.lease_ttl_seconds)

    async def release_lease(self, conv_id: str) -> None:
        await self._store.release_lease(conv_id)

    async def scan_expired(self) -> List[str]:
        return await self._store.scan_expired_leases()

    async def get_last_step_state(
        self, conv_id: str
    ) -> Optional[Tuple[str, StepState, dict]]:
        """返回 (step_id, state, snapshot)。通过重放事件找最后一个 step。"""
        events = await self._store.get_events(conv_id)
        if not events:
            return None
        last = events[-1]
        state_result = await self._store.get_step_state(last.step_id)
        snapshot = state_result[1] if state_result else {}
        return last.step_id, last.state, snapshot

    async def replay_events(self, conv_id: str) -> List[StepEvent]:
        return await self._store.get_events(conv_id)

    async def decide_resume_action(self, conv_id: str) -> Dict[str, Any]:
        """根据最后一个 step 的 state 决定恢复动作。"""
        last = await self.get_last_step_state(conv_id)
        if last is None:
            return {"action": "continue_next", "step_id": None, "state": None}
        step_id, state, _ = last
        if state in _AWAITING_STATES:
            return {"action": "resume_awaiting", "step_id": step_id, "state": state}
        if state in _INCOMPLETE_STATES:
            return {"action": "redo_step", "step_id": step_id, "state": state}
        # DONE / FAILED
        return {"action": "continue_next", "step_id": None, "state": state}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_recovery.py -v`
Expected: PASS（7 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/recovery.py \
        packages/derisk-core/tests/agent/core/v2/test_recovery.py
git commit -m "feat(agent-v2): RecoveryCoordinatorV2 lease + 重放恢复决策"
```

---

### Task 6: run_step() Runtime 入口 + 端到端崩溃恢复集成测试

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_runtime.py`

**Interfaces:**
- Consumes: `StepState`（Task 1）、`StepEvent`（Task 2）、`StateStore`（Task 3）、`EventStream`（Task 4）、`RecoveryCoordinatorV2`（Task 5）
- Produces: `run_step()` async generator 函数。签名：
  ```python
  async def run_step(
      agent_id: str,
      conv_id: str,
      input_: dict,
      state_store: StateStore,
      thinking_fn: Callable[[dict], AsyncGenerator[dict, None]],
      acting_fn: Optional[Callable[[dict], Awaitable[dict]]] = None,
      parent_step_id: Optional[str] = None,
  ) -> AsyncGenerator[StepEvent, None]
  ```
  - `thinking_fn`：async generator，yield token dict（`{"token": "..."}`）
  - `acting_fn`：async function，接收 tool_call dict，返回 result dict。P0 可为 None（纯思考 step）
- 还产出 `resume_step()` 函数：从给定 `step_id` 续接，重放已完成事件 + 重做未完成部分

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_runtime.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step, resume_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.recovery import RecoveryCoordinatorV2
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def thinking_fn(input_):
    """测试用思考函数：yield 两个 token。"""
    yield {"token": "hello"}
    yield {"token": "world"}


async def acting_fn(tool_call):
    return {"result": f"executed:{tool_call['tool']}"}


async def test_run_step_produces_init_thinking_done(store):
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store, thinking_fn):
        events.append(e)

    states = [e.state for e in events]
    assert states[0] == StepState.INIT
    assert StepState.THINKING in states
    assert states[-1] == StepState.DONE
    # 至少有 2 个 llm_token
    tokens = [e for e in events if e.event_type == "llm_token"]
    assert len(tokens) == 2


async def test_run_step_with_acting(store):
    async def thinking_with_tool(input_):
        yield {"token": "calling tool"}
        # 在 token 流里附带 tool_calls（约定：thinking_fn 的最后一个 yield 可以含 tool_calls）
        yield {"token": "", "tool_calls": [{"tool": "read_file"}]}

    events = []
    async for e in run_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store, thinking_with_tool, acting_fn
    ):
        events.append(e)

    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert tool_results[0].output == {"result": "executed:read_file"}


async def test_crash_recovery_resumes_awaiting(store):
    """模拟跑到 AWAITING_USER 后崩溃，resume 后状态恢复。"""
    # 先跑一步，停在 awaiting（用特殊 thinking_fn 模拟）
    async def thinking_awaiting(input_):
        yield {"token": "need user input", "await_user": True}

    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store, thinking_awaiting):
        events.append(e)

    # 确认停在 AWAITING_USER
    rc = RecoveryCoordinatorV2(store)
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "resume_awaiting"
    assert decision["state"] == StepState.AWAITING_USER

    # 重放事件
    replayed = await rc.replay_events("conv-1")
    assert len(replayed) == len(events)


async def test_resume_step_redoes_incomplete(store):
    """step 停在 THINKING（崩溃），resume 后重做该 step。"""
    # 手动塞一个 THINKING 事件模拟崩溃
    from derisk.agent.core.v2.event_stream import EventStream
    from derisk.agent.core.v2.step_event import StepEvent
    stream = EventStream(store)
    await stream.emit(StepEvent(
        event_id="evt-pre",
        step_id="step-pre",
        conv_id="conv-1",
        agent_id="agent-1",
        parent_step_id=None,
        state=StepState.THINKING,
        event_type="llm_token",
        input={"prompt": "hi"},
        output={"token": "partial"},
        seq=0,
        timestamp=0.0,
    ))

    rc = RecoveryCoordinatorV2(store)
    decision = await rc.decide_resume_action("conv-1")
    assert decision["action"] == "redo_step"
    assert decision["step_id"] == "step-pre"

    # resume_step 应该重做该 step
    events = []
    async for e in resume_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store, thinking_fn,
        step_id="step-pre"
    ):
        events.append(e)
    # 重做后应该到 DONE
    assert events[-1].state == StepState.DONE
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.runtime'`

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/runtime.py
"""run_step()——V2 Runtime 入口。

P0 实现：INIT → THINKING（yield tokens）→ ACTING（可选）→ OBSERVING → DONE
thinking_fn / acting_fn 可注入，P0 测试用桩，P1+ 接真实 LLM 和工具。

崩溃恢复：每个 yield 前持久化，进程崩溃后 resume_step 从 StateStore
重放已完成事件，未完成的 step 重新执行（LLM 调用重新发，但已完成
的 step 从事件流读结果不重做）。
"""
from __future__ import annotations
import uuid
import time
from typing import AsyncGenerator, Callable, Awaitable, Optional, List
from derisk.agent.core.v2.step_state import StepState, validate_transition
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.event_stream import EventStream


ThinkingFn = Callable[[dict], AsyncGenerator[dict, None]]
ActingFn = Callable[[dict], Awaitable[dict]]


def _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start):
    """创建 emit 函数：构造 StepEvent、持久化、返回。seq 单调递增。"""
    seq = {"n": seq_start}

    async def emit(state, event_type, input_data=None, output_data=None):
        event = StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id=step_id,
            conv_id=conv_id,
            agent_id=agent_id,
            parent_step_id=parent_step_id,
            state=state,
            event_type=event_type,
            input=input_data or {},
            output=output_data or {},
            seq=seq["n"],
            timestamp=time.time(),
        )
        seq["n"] += 1
        return await stream.emit(event)

    return emit


async def _run_thinking_phase(emit, thinking_fn, input_, result_box):
    """INIT + THINKING 阶段。yield 事件，把 tool_calls/await_user 写入 result_box。"""
    yield await emit(StepState.INIT, "step_init", input_data=input_)
    result_box["tool_calls"] = []
    result_box["await_user"] = False
    async for chunk in thinking_fn(input_):
        if chunk.get("await_user"):
            result_box["await_user"] = True
            yield await emit(
                StepState.AWAITING_USER, "interaction_request",
                input_data={"reason": "thinking_fn requested user input"},
            )
            return
        if chunk.get("tool_calls"):
            result_box["tool_calls"].extend(chunk["tool_calls"])
        yield await emit(
            StepState.THINKING, "llm_token",
            output_data={"token": chunk.get("token", "")},
        )


async def run_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    parent_step_id: Optional[str] = None,
) -> AsyncGenerator[StepEvent, None]:
    """跑一个 step，yield 所有 StepEvent。每个事件持久化后再 yield。"""
    stream = EventStream(state_store)
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    emit = _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start=0)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    # ACTING + OBSERVING（P0 无 permission gate，P1 加）
    if result_box["tool_calls"] and acting_fn:
        for tc in result_box["tool_calls"]:
            yield await emit(StepState.ACTING, "tool_call", input_data=tc)
            result = await acting_fn(tc)
            yield await emit(StepState.OBSERVING, "tool_result", output_data=result)

    yield await emit(StepState.DONE, "step_done")


async def resume_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    step_id: Optional[str] = None,
) -> AsyncGenerator[StepEvent, None]:
    """从崩溃点续接。

    若指定 step_id 且该 step 未完成，重做该 step（重新跑 thinking_fn）。
    已完成的 step 从事件流读结果不重做（P0 简化：直接重做指定 step）。
    """
    if not step_id:
        async for e in run_step(agent_id, conv_id, input_, state_store, thinking_fn, acting_fn):
            yield e
        return

    stream = EventStream(state_store)
    existing = await state_store.get_events(conv_id)
    seq_start = existing[-1].seq + 1 if existing else 0
    emit = _make_emit(stream, step_id, conv_id, agent_id, None, seq_start)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    yield await emit(StepState.DONE, "step_done")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime.py -v`
Expected: PASS（4 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/runtime.py \
        packages/derisk-core/tests/agent/core/v2/test_runtime.py
git commit -m "feat(agent-v2): run_step() 入口 + resume_step() 崩溃恢复"
```

---

### Task 7: V2 包初始化 + 公开 API 导出 + 全量回归

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/__init__.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_package.py`

**Interfaces:**
- Produces: `derisk.agent.core.v2` 包，导出：`StepState`、`StepEvent`、`StateStore`、`DbStateStore`、`EventStream`、`RecoveryCoordinatorV2`、`run_step`、`resume_step`、`validate_transition`、`IllegalTransitionError`

- [ ] **Step 1: 写失败测试**

```python
# packages/derisk-core/tests/agent/core/v2/test_package.py
from derisk.agent.core.v2 import (
    StepState,
    StepEvent,
    StateStore,
    DbStateStore,
    EventStream,
    RecoveryCoordinatorV2,
    run_step,
    resume_step,
    validate_transition,
    IllegalTransitionError,
)


def test_all_public_names_importable():
    assert StepState.INIT.value == "init"
    assert callable(run_step)
    assert callable(resume_step)
    assert callable(validate_transition)
    assert issubclass(IllegalTransitionError, Exception)
    assert issubclass(DbStateStore, StateStore)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_package.py -v`
Expected: FAIL with `ImportError`（包没有 `__init__.py` 或导出不全）

- [ ] **Step 3: 写最小实现**

```python
# packages/derisk-core/src/derisk/agent/core/v2/__init__.py
"""V2 Runtime——Agent 框架内核。

六件套中的四件（StepState/EventStream/StateStore/Recovery）在 P0 落地。
PermissionGate/SubAgent Runtime 在后续阶段加。

参见设计文档：docs/superpowers/specs/2026-06-30-agent-framework-evolution-design.md
"""
from derisk.agent.core.v2.step_state import (
    StepState,
    VALID_TRANSITIONS,
    validate_transition,
    IllegalTransitionError,
)
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore, DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.recovery import RecoveryCoordinatorV2
from derisk.agent.core.v2.runtime import run_step, resume_step

__all__ = [
    "StepState",
    "VALID_TRANSITIONS",
    "validate_transition",
    "IllegalTransitionError",
    "StepEvent",
    "StateStore",
    "DbStateStore",
    "EventStream",
    "RecoveryCoordinatorV2",
    "run_step",
    "resume_step",
]
```

- [ ] **Step 4: 运行测试确认通过 + 全量回归**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS（所有 V2 测试全过）

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/__init__.py \
        packages/derisk-core/tests/agent/core/v2/test_package.py
git commit -m "feat(agent-v2): 包初始化 + 公开 API 导出"
```

---

## Self-Review

**1. Spec coverage（P0 范围）:**
- ✅ StepState 状态机（spec §7.1）→ Task 1
- ✅ StepEvent 数据结构（spec §7.2）→ Task 2
- ✅ EventStream AsyncGenerator（spec §7.3）→ Task 4
- ✅ StateStore 接口 + DbStateStore（spec §7.4）→ Task 3
- ✅ 崩溃检测 lease（spec §7.5）→ Task 3（lease 原语）+ Task 5（协调器）
- ✅ 重放恢复流程（spec §7.5）→ Task 5（决策）+ Task 6（resume_step）
- ✅ "已完成 step 从事件流读结果不重做"（spec §7.5）→ Task 6 `resume_step` 注释说明 P0 简化，完整实现见 P3
- ⏭️ AWAITING_TOOL_PERMISSION / AWAITING_SUB_AGENT 的具体触发 → P1（PermissionGate）/ P2（SubAgent），P0 只验证状态可达
- ⏭️ RedisStateStore / HybridStateStore → 后续阶段（P0 只 DbStateStore）

**2. Placeholder scan:** 无 TBD/TODO/"implement later"/"add error handling"。所有代码块完整。

**3. Type consistency:**
- `StepEvent` 字段在 Task 2 定义，Task 3/4/5/6 使用一致（`event_id/step_id/conv_id/agent_id/parent_step_id/state/event_type/input/output/seq/timestamp`）✓
- `StateStore` 方法签名在 Task 3 定义，Task 4/5 使用一致（`append_event/get_events/get_step_state/set_step_state/acquire_lease/renew_lease/release_lease/scan_expired_leases`）✓
- `EventStream.emit(event) -> StepEvent` 在 Task 4 定义，Task 5/6 使用一致 ✓
- `RecoveryCoordinatorV2` 方法在 Task 5 定义，Task 6 使用 `decide_resume_action/replay_events` ✓
- `run_step` 签名在 Task 6 定义，测试中调用一致 ✓

**4. P0 简化声明：** `resume_step` 在 P0 只实现"重做指定 step"，不实现"已完成 step 从事件流读结果不重做"的完整 event sourcing 重放——这在 spec §7.5 是目标，但 P0 范围只验证状态机和持久化骨架。完整实现在 P3（事件流统一）阶段补。已在 Task 6 实现注释中说明。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-30-agent-v2-runtime-p0.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 我每个 task 派一个新子代理执行，task 间 review，快速迭代

**2. Inline Execution** - 在当前会话用 executing-plans 批量执行，带 checkpoint review

选哪种？
