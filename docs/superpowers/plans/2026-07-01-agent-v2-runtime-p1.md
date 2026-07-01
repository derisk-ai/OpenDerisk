# Agent V2 Runtime P1: PermissionGate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the PermissionGate — a 5-level check chain that runs before every tool call in the V2 Runtime, with InteractionRequest persistence for crash-safe authorization prompts.

**Architecture:** A new `permission_gate.py` in the V2 kernel. `PermissionGate.check()` is called by `run_step`/`resume_step` between the `ACTING` event and `acting_fn`. On `ask`, it yields an `AWAITING_TOOL_PERMISSION` event (persisted via the existing EventStream → StateStore) and delegates to the existing `InteractionAdapter.request_tool_permission`. P0's three Important findings (resume_step acting_fn drop, unenforced state machine, missing resume_awaiting path) are folded into this plan because the permission integration forces those refactors anyway.

**Tech Stack:** Python ≥ 3.10, pydantic v2 (`from derisk._private.pydantic import BaseModel, ConfigDict, Field`), stdlib `enum`/`fnmatch`/`hashlib`, pytest-asyncio (already configured). Reuses existing `InteractionAdapter`, `InteractionGateway`, `PermissionRuleset` (the newer pydantic one at `derisk_core/permission/ruleset.py`).

## Global Constraints

- Python ≥ 3.10
- pydantic v2 via `from derisk._private.pydantic import BaseModel, ConfigDict, Field` (never `from pydantic import`)
- V2 kernel code under `packages/derisk-core/src/derisk/agent/core/v2/`
- TDD: RED → GREEN → commit per task
- All V2 methods are `async`
- `StateStore` methods are `async`; SQLite calls wrapped in `asyncio.to_thread`
- Event sourcing: `step_event` is append-only (`INSERT` not `INSERT OR REPLACE`); `step_state` is latest-snapshot
- Durability before visibility: every event persisted before yielded
- Reuse existing infra: `InteractionAdapter.request_tool_permission` (`interaction_adapter.py:244`), `InteractionGateway.send_and_wait` (`interaction_gateway.py:220`), `PermissionRuleset` (`derisk_core/permission/ruleset.py:20`)
- Do NOT modify legacy `AgentContext` dataclass (`agent/core/agent.py:223`) — V2 kernel passes `PermissionMode` as a plain parameter, not via `AgentContext`
- Do NOT modify legacy `check_tool_permission`/`needs_tool_approval`/`ActionOutput.ask_user` in P1 — they stay as-is, deprecated per spec §11.4 (P4 cleanup)
- Working tree has unrelated uncommitted changes from a parallel scenario-workspace effort; stage only the files each task names
- Test output must be pristine (Task 3 of P0 added `filterwarnings` for pre-existing pydantic noise — do not regress)
- V2 tests live under `packages/derisk-core/tests/agent/core/v2/`

---

## File Structure

**New files (all in `packages/derisk-core/src/derisk/agent/core/v2/`):**
- `permission_mode.py` — `PermissionMode` enum (`default`/`plan`/`auto`/`bypass`). ~15 lines.
- `permission_gate.py` — `PermissionGate` class + `PermissionResult`/`PermissionDecision` types. ~120 lines. The 5-level check chain.
- `session_cache.py` — `SessionPermissionCache` (in-memory, per-agent). `allow_once`/`allow_session`/`deny` keyed by `tool_name + input_hash`. ~50 lines.

**Modified V2 files:**
- `runtime.py` — wire `PermissionGate` into the ACTING loop of `run_step` + `resume_step`; also fix the 3 P0 Important findings (acting_fn in resume_step, `validate_transition` enforcement, `resume_awaiting` path).
- `step_state.py` — no change (already has `AWAITING_TOOL_PERMISSION`).
- `state_store.py` — add `interaction_checkpoint` table + 3 methods (`save_interaction_checkpoint`, `get_interaction_checkpoint`, `delete_interaction_checkpoint`) for crash-safe InteractionRequest persistence.
- `__init__.py` — export `PermissionMode`, `PermissionGate`, `PermissionResult`, `SessionPermissionCache`.

**New test files:**
- `tests/agent/core/v2/test_permission_mode.py`
- `tests/agent/core/v2/test_session_cache.py`
- `tests/agent/core/v2/test_permission_gate.py`
- `tests/agent/core/v2/test_state_store_checkpoint.py` (for the new table)
- `tests/agent/core/v2/test_runtime_permission.py` (integration: run_step with permission gate)

**External files touched (minimal, surgical):**
- `packages/derisk-core/src/derisk/agent/resource/tool/base.py` — add optional `check_permissions(input, context) -> Optional[PermissionCheckResult]` hook to `ToolBase`. Default returns `None` (no opinion). This is the spec §9.3 step-4 hook. Existing tools are unaffected (default `None` means "fall through to next level").

**Files NOT touched (deferred per spec §11.4):**
- `base_agent.py` (legacy `check_tool_permission`/`needs_tool_approval` stay; P4 cleanup)
- `agent/core/action/base.py` (`ActionOutput.ask_user` stays; P4 cleanup)
- `agent/core/agent.py` (`AgentContext` dataclass unchanged; V2 uses plain `PermissionMode` param)
- `interaction_adapter.py` / `interaction_gateway.py` / `interaction_protocol.py` (reused as-is)

---

## Task 1: PermissionMode enum

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/permission_mode.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_permission_mode.py`

**Interfaces:**
- Produces: `PermissionMode` enum with 4 values: `DEFAULT="default"`, `PLAN="plan"`, `AUTO="auto"`, `BYPASS="bypass"`. String values match spec §9.2 exactly.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_permission_mode.py
from derisk.agent.core.v2.permission_mode import PermissionMode


def test_permission_mode_values():
    assert PermissionMode.DEFAULT.value == "default"
    assert PermissionMode.PLAN.value == "plan"
    assert PermissionMode.AUTO.value == "auto"
    assert PermissionMode.BYPASS.value == "bypass"


def test_permission_mode_from_string():
    assert PermissionMode("default") is PermissionMode.DEFAULT
    assert PermissionMode("plan") is PermissionMode.PLAN
    assert PermissionMode("auto") is PermissionMode.AUTO
    assert PermissionMode("bypass") is PermissionMode.BYPASS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_mode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.permission_mode'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/permission_mode.py
"""PermissionMode — agent-level permission behavior switch.

See spec §9.2. Stored on the agent, passed to PermissionGate.check().
"""
from __future__ import annotations
from enum import Enum


class PermissionMode(str, Enum):
    DEFAULT = "default"   # per-tool rule check, ask if rule says ask
    PLAN = "plan"         # deny all side-effecting tools, allow read-only
    AUTO = "auto"         # allow all (YOLO)
    BYPASS = "bypass"     # skip PermissionGate entirely (system ops only)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_mode.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/permission_mode.py \
        packages/derisk-core/tests/agent/core/v2/test_permission_mode.py
git commit -m "feat(agent-v2): PermissionMode 枚举（4 模式）"
```

---

## Task 2: SessionPermissionCache

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/session_cache.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_session_cache.py`

**Interfaces:**
- Produces: `SessionPermissionCache` class. Constructor: `SessionPermissionCache()`. Methods:
  - `is_allowed(tool_name: str, input_hash: str) -> bool` — True if `allow_session` was set for this tool+input
  - `allow_session(tool_name: str, input_hash: str) -> None` — mark allowed for session
  - `allow_once(tool_name: str, input_hash: str) -> None` — no-op marker (allow_once is not cached; included for API symmetry)
  - `deny(tool_name: str, input_hash: str) -> None` — explicitly remove from session cache (a prior allow_session is revoked)
  - `clear() -> None` — wipe all entries
- Produces: helper `hash_tool_input(input: dict) -> str` — stable SHA256 hex of the JSON-serialized input (sorted keys). Used by PermissionGate and tests.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_session_cache.py
from derisk.agent.core.v2.session_cache import SessionPermissionCache, hash_tool_input


def test_hash_tool_input_is_stable_and_sorted():
    h1 = hash_tool_input({"a": 1, "b": 2})
    h2 = hash_tool_input({"b": 2, "a": 1})
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex


def test_allow_session_makes_is_allowed_true():
    cache = SessionPermissionCache()
    assert cache.is_allowed("read_file", "hash1") is False
    cache.allow_session("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is True


def test_allow_once_does_not_cache():
    cache = SessionPermissionCache()
    cache.allow_once("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is False


def test_deny_revokes_prior_allow_session():
    cache = SessionPermissionCache()
    cache.allow_session("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is True
    cache.deny("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is False


def test_deny_on_uncached_is_noop():
    cache = SessionPermissionCache()
    cache.deny("read_file", "hash1")  # no error
    assert cache.is_allowed("read_file", "hash1") is False


def test_clear_wipes_all():
    cache = SessionPermissionCache()
    cache.allow_session("read_file", "hash1")
    cache.allow_session("write_file", "hash2")
    cache.clear()
    assert cache.is_allowed("read_file", "hash1") is False
    assert cache.is_allowed("write_file", "hash2") is False


def test_cache_is_per_tool_per_input():
    cache = SessionPermissionCache()
    cache.allow_session("read_file", "hash1")
    assert cache.is_allowed("read_file", "hash1") is True
    assert cache.is_allowed("read_file", "hash2") is False  # different input
    assert cache.is_allowed("write_file", "hash1") is False  # different tool
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_session_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.session_cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/session_cache.py
"""SessionPermissionCache — per-agent, in-memory allow_session cache.

Keyed by (tool_name, input_hash). allow_once is not cached (caller just
proceeds). deny revokes any prior allow_session for the same key.

This is the spec §9.3 step-2 session cache. Survives across steps within
a single agent run; cleared on agent restart.
"""
from __future__ import annotations
import hashlib
import json
from typing import Dict


def hash_tool_input(input_: dict) -> str:
    """Stable SHA256 hex of the JSON-serialized input (sorted keys)."""
    payload = json.dumps(input_, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SessionPermissionCache:
    def __init__(self):
        self._allowed: Dict[str, set] = {}  # tool_name -> set of input_hashes

    def is_allowed(self, tool_name: str, input_hash: str) -> bool:
        return input_hash in self._allowed.get(tool_name, set())

    def allow_session(self, tool_name: str, input_hash: str) -> None:
        self._allowed.setdefault(tool_name, set()).add(input_hash)

    def allow_once(self, tool_name: str, input_hash: str) -> None:
        # allow_once is not cached — the caller proceeds, next call re-checks
        pass

    def deny(self, tool_name: str, input_hash: str) -> None:
        bucket = self._allowed.get(tool_name)
        if bucket:
            bucket.discard(input_hash)

    def clear(self) -> None:
        self._allowed.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_session_cache.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/session_cache.py \
        packages/derisk-core/tests/agent/core/v2/test_session_cache.py
git commit -m "feat(agent-v2): SessionPermissionCache + hash_tool_input"
```

---

## Task 3: StateStore interaction_checkpoint table

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/state_store.py` (add table to `_SCHEMA` + 3 methods to `StateStore` ABC and `DbStateStore`)
- Test: `packages/derisk-core/tests/agent/core/v2/test_state_store_checkpoint.py`

**Interfaces:**
- Adds to `StateStore` ABC (3 new abstract methods):
  - `async save_interaction_checkpoint(request_id: str, step_id: str, conv_id: str, request_payload: dict) -> None`
  - `async get_interaction_checkpoint(request_id: str) -> Optional[dict]` — returns `{"request_id", "step_id", "conv_id", "request_payload", "created_at"}` or `None`
  - `async delete_interaction_checkpoint(request_id: str) -> None`
- Adds to `DbStateStore`: concrete implementations of the above.
- Adds to `_SCHEMA`: new `interaction_checkpoint` table:
  ```sql
  CREATE TABLE IF NOT EXISTS interaction_checkpoint (
      request_id TEXT PRIMARY KEY,
      step_id TEXT NOT NULL,
      conv_id TEXT NOT NULL,
      request_payload TEXT NOT NULL,
      created_at REAL NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_checkpoint_conv ON interaction_checkpoint(conv_id);
  ```
- Existing `step_event`/`step_state`/`agent_lease` tables and methods unchanged.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_state_store_checkpoint.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.state_store import DbStateStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_save_and_get_checkpoint(store):
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1",
        {"type": "AUTHORIZE", "tool_name": "read_file", "options": []},
    )
    row = await store.get_interaction_checkpoint("req-1")
    assert row is not None
    assert row["request_id"] == "req-1"
    assert row["step_id"] == "step-1"
    assert row["conv_id"] == "conv-1"
    assert row["request_payload"]["tool_name"] == "read_file"
    assert "created_at" in row


async def test_get_checkpoint_returns_none_if_absent(store):
    assert await store.get_interaction_checkpoint("nope") is None


async def test_delete_checkpoint(store):
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1", {"tool": "x"}
    )
    await store.delete_interaction_checkpoint("req-1")
    assert await store.get_interaction_checkpoint("req-1") is None


async def test_delete_absent_checkpoint_is_noop(store):
    await store.delete_interaction_checkpoint("never-existed")  # no error


async def test_save_checkpoint_overwrites_on_same_request_id(store):
    # Primary key is request_id — saving twice with same id should replace
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1", {"v": 1}
    )
    await store.save_interaction_checkpoint(
        "req-1", "step-1", "conv-1", {"v": 2}
    )
    row = await store.get_interaction_checkpoint("req-1")
    assert row["request_payload"]["v"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store_checkpoint.py -v`
Expected: FAIL with `AttributeError: 'DbStateStore' object has no attribute 'save_interaction_checkpoint'`

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/state_store.py`. The current `_SCHEMA` ends with the `agent_lease` table + its index. **Add** the `interaction_checkpoint` table + index to `_SCHEMA` (append, do not modify existing tables):

```python
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
```

**Add** 3 abstract methods to the `StateStore` ABC (after `scan_expired_leases`):

```python
    @abstractmethod
    async def save_interaction_checkpoint(
        self, request_id: str, step_id: str, conv_id: str, request_payload: dict
    ) -> None: ...

    @abstractmethod
    async def get_interaction_checkpoint(self, request_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def delete_interaction_checkpoint(self, request_id: str) -> None: ...
```

**Add** 3 concrete methods to `DbStateStore` (after `scan_expired_leases`):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store_checkpoint.py -v`
Expected: PASS (5 tests)

Also run the existing StateStore tests to confirm no regression:
Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store.py -v`
Expected: PASS (8 tests, unchanged)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/state_store.py \
        packages/derisk-core/tests/agent/core/v2/test_state_store_checkpoint.py
git commit -m "feat(agent-v2): StateStore interaction_checkpoint 表 + 3 方法"
```

---

## Task 4: PermissionGate core (5-level check chain)

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_permission_gate.py`

**Interfaces:**
- Consumes:
  - `PermissionMode` (from Task 1)
  - `SessionPermissionCache`, `hash_tool_input` (from Task 2)
  - `PermissionRuleset` from `derisk_core.permission.ruleset` (existing, newer pydantic version)
  - `PermissionAction` enum (`ALLOW`/`DENY`/`ASK`) from `derisk_core.permission.ruleset`
  - `InteractionAdapter` from `derisk.agent.core.interaction_adapter` (existing) — for the `ask` path
  - `StateStore` (from P0 Task 3, now with checkpoint methods from Task 3 above) — for InteractionRequest persistence
  - `StepEvent` + `EventStream` (from P0) — for emitting `AWAITING_TOOL_PERMISSION` events
- Produces:
  - `PermissionDecision` enum: `ALLOW` / `DENY` / `AWAITING` (AWAITING means we emitted an event and are waiting for user response)
  - `PermissionResult` pydantic model: `decision: PermissionDecision`, `reason: str = ""`, `request_id: Optional[str] = None` (set when AWAITING)
  - `PermissionGate` class:
    - Constructor: `PermissionGate(state_store: StateStore, event_stream: EventStream, interaction_adapter: Optional[InteractionAdapter] = None, session_cache: Optional[SessionPermissionCache] = None, ruleset: Optional[PermissionRuleset] = None, mode: PermissionMode = PermissionMode.DEFAULT, step_id: Optional[str] = None, conv_id: Optional[str] = None, agent_id: Optional[str] = None)`
    - Method: `async check(tool_call: dict) -> AsyncGenerator[StepEvent, None]` — yields `AWAITING_TOOL_PERMISSION` events when decision is AWAITING; the final `PermissionResult` is retrieved via `gate.last_result` after the generator is exhausted. (Async generator because permission asking needs to emit events for the runtime to yield upstream.)
    - Attribute: `last_result: PermissionResult` — set after `check()` generator exhausts.

**Design note — why `check()` is an async generator:** The runtime (`run_step`) is itself an async generator that yields `StepEvent`s upstream. When PermissionGate needs to ask the user, it must emit an `AWAITING_TOOL_PERMISSION` event that flows through the runtime to the SSE layer. So `check()` yields events as a side effect, and the caller reads `gate.last_result` for the final decision.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_permission_gate.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache
from derisk.agent.core.v2.permission_gate import PermissionGate, PermissionDecision
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.step_state import StepState
from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


@pytest.fixture
def stream(store):
    return EventStream(store)


def _gate(store, stream, mode=PermissionMode.DEFAULT, ruleset=None, session_cache=None,
          interaction_adapter=None, step_id="step-1", conv_id="conv-1", agent_id="agent-1"):
    return PermissionGate(
        state_store=store, event_stream=stream,
        interaction_adapter=interaction_adapter,
        session_cache=session_cache or SessionPermissionCache(),
        ruleset=ruleset, mode=mode,
        step_id=step_id, conv_id=conv_id, agent_id=agent_id,
    )


async def test_bypass_mode_allows(store, stream):
    gate = _gate(store, stream, mode=PermissionMode.BYPASS)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []  # no event emitted
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_auto_mode_allows(store, stream):
    gate = _gate(store, stream, mode=PermissionMode.AUTO)
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_plan_mode_denies_side_effect_tool_when_ruleset_says_allow(store, stream):
    # ruleset allows rm, but plan mode overrides → deny
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, mode=PermissionMode.PLAN, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    assert gate.last_result.decision is PermissionDecision.DENY
    assert "plan mode" in gate.last_result.reason.lower()


async def test_plan_mode_allows_readonly_tool(store, stream):
    ruleset = PermissionRuleset(default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, mode=PermissionMode.PLAN, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_session_cache_skips_ruleset(store, stream):
    cache = SessionPermissionCache()
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ASK)
    # Pre-populate session cache
    from derisk.agent.core.v2.session_cache import hash_tool_input
    cache.allow_session("read_file", hash_tool_input({}))
    gate = _gate(store, stream, ruleset=ruleset, session_cache=cache)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ruleset_allow_short_circuits(store, stream):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ruleset_deny_short_circuits(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.DENY)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_ask_emits_awaiting_event_and_persists_checkpoint(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    # Fake interaction adapter: responds "allow_once" immediately
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class FakeResponse:
                action = "allow_once"
                status = None
            return FakeResponse()
    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    # Should emit exactly one AWAITING_TOOL_PERMISSION event
    assert len(events) == 1
    assert events[0].state is StepState.AWAITING_TOOL_PERMISSION
    assert events[0].event_type == "interaction_request"
    assert events[0].input["tool_name"] == "rm"
    # Checkpoint persisted
    request_id = events[0].input["request_id"]
    cp = await store.get_interaction_checkpoint(request_id)
    assert cp is not None
    assert cp["step_id"] == "step-1"
    # After response, checkpoint deleted and decision is ALLOW
    assert gate.last_result.decision is PermissionDecision.ALLOW
    assert await store.get_interaction_checkpoint(request_id) is None


async def test_ask_deny_response_persists_deny(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class FakeResponse:
                action = "deny"
                status = None
            return FakeResponse()
    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_ask_allow_session_caches_for_session(store, stream):
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class FakeResponse:
                action = "allow_session"
                status = None
            return FakeResponse()
    cache = SessionPermissionCache()
    gate = _gate(store, stream, ruleset=ruleset, session_cache=cache,
                 interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW
    # Second call with same input should skip the ask (no event, cache hit)
    from derisk.agent.core.v2.session_cache import hash_tool_input
    assert cache.is_allowed("rm", hash_tool_input({"path": "/x"}))


async def test_no_ruleset_no_adapter_defaults_to_allow(store, stream):
    # No ruleset, no adapter — default_action when no ruleset is ALLOW (safe default for P1 tests)
    gate = _gate(store, stream, ruleset=None, interaction_adapter=None)
    events = [e async for e in gate.check({"tool": "read_file", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_no_ruleset_but_ask_action_without_adapter_raises(store, stream):
    # If somehow no ruleset but mode says ask... can't happen in practice,
    # but guard: if decision would be ASK and no adapter, raise clear error
    from derisk.agent.core.v2.permission_gate import NoInteractionAdapterError
    # Build a gate with no ruleset AND no adapter; force the ASK path by using
    # a ruleset that returns ASK
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=None)
    with pytest.raises(NoInteractionAdapterError):
        async for _ in gate.check({"tool": "rm", "input": {}}):
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.permission_gate'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py
"""PermissionGate — 5-level check chain before every tool call.

Spec §9.3. Levels (in order):
  1. PermissionMode short-circuit (bypass/auto/plan)
  2. session cache (allow_session)
  3. permission_ruleset (static rules: ALLOW/DENY/ASK)
  4. (P1 deferred) Tool.check_permissions hook — no Tool integration yet
  5. ask → emit AWAITING_TOOL_PERMISSION event + persist checkpoint +
     delegate to InteractionAdapter.request_tool_permission

check() is an async generator: it yields AWAITING_TOOL_PERMISSION events
when asking; the caller reads gate.last_result for the final decision.
"""
from __future__ import annotations
import uuid
from typing import AsyncGenerator, Optional, TYPE_CHECKING
from derisk._private.pydantic import BaseModel, ConfigDict, Field
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache, hash_tool_input
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState
from derisk_core.permission.ruleset import PermissionRuleset, PermissionAction

if TYPE_CHECKING:
    from derisk.agent.core.v2.state_store import StateStore
    from derisk.agent.core.v2.event_stream import EventStream
    from derisk.agent.core.interaction_adapter import InteractionAdapter


# Tools that have side effects (write/delete/execute). In P1 we use a simple
# heuristic: tools whose name matches these patterns are side-effecting.
# P2+ can replace this with Tool.metadata.risk_level.
_SIDE_EFFECT_PATTERNS = ("rm", "write", "delete", "execute", "bash", "shell",
                         "mv", "cp", "mkdir", "rmdir", "chmod", "chown")


def _is_side_effecting(tool_name: str) -> bool:
    lower = tool_name.lower()
    return any(p in lower for p in _SIDE_EFFECT_PATTERNS)


class NoInteractionAdapterError(RuntimeError):
    """Raised when PermissionGate reaches the ASK path but no adapter is configured."""


class PermissionDecision:
    ALLOW = "allow"
    DENY = "deny"
    AWAITING = "awaiting"


class PermissionResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)
    decision: str  # PermissionDecision.*
    reason: str = ""
    request_id: Optional[str] = None


class PermissionGate:
    def __init__(
        self,
        state_store: "StateStore",
        event_stream: "EventStream",
        interaction_adapter: Optional["InteractionAdapter"] = None,
        session_cache: Optional[SessionPermissionCache] = None,
        ruleset: Optional[PermissionRuleset] = None,
        mode: PermissionMode = PermissionMode.DEFAULT,
        step_id: Optional[str] = None,
        conv_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        self._store = state_store
        self._stream = event_stream
        self._adapter = interaction_adapter
        self._cache = session_cache or SessionPermissionCache()
        self._ruleset = ruleset
        self._mode = mode
        self._step_id = step_id
        self._conv_id = conv_id
        self._agent_id = agent_id
        self.last_result: PermissionResult = PermissionResult(
            decision=PermissionDecision.DENY, reason="not checked"
        )

    async def check(self, tool_call: dict) -> AsyncGenerator[StepEvent, None]:
        """Run the 5-level check. Yields AWAITING_TOOL_PERMISSION events when asking.
        Sets self.last_result. Caller reads last_result after generator exhausts.
        """
        tool_name = tool_call.get("tool", "")
        tool_input = tool_call.get("input", {}) or {}
        input_hash = hash_tool_input(tool_input)

        # Level 1: PermissionMode short-circuit
        if self._mode is PermissionMode.BYPASS:
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="bypass mode")
            return
        if self._mode is PermissionMode.AUTO:
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="auto mode")
            return
        if self._mode is PermissionMode.PLAN and _is_side_effecting(tool_name):
            self.last_result = PermissionResult(decision=PermissionDecision.DENY, reason="plan mode denies side-effecting tool")
            return

        # Level 2: session cache
        if self._cache.is_allowed(tool_name, input_hash):
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="session cache")
            return

        # Level 3: permission_ruleset
        action = PermissionAction.ASK  # default when no ruleset
        if self._ruleset is not None:
            action = self._ruleset.check(tool_name, context={}).action
        if action is PermissionAction.ALLOW:
            self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="ruleset allow")
            return
        if action is PermissionAction.DENY:
            self.last_result = PermissionResult(decision=PermissionDecision.DENY, reason="ruleset deny")
            return

        # Level 4: Tool.check_permissions — P1 defers this (no Tool integration yet)
        # TODO(P2): if tool has check_permissions, call it; non-None result short-circuits

        # Level 5: ask → emit event + persist + delegate
        if self._adapter is None:
            raise NoInteractionAdapterError(
                f"PermissionGate reached ASK for tool '{tool_name}' but no "
                f"InteractionAdapter is configured"
            )

        request_id = f"req-{uuid.uuid4().hex[:8]}"
        request_payload = {
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "step_id": self._step_id,
            "conv_id": self._conv_id,
        }
        # Persist checkpoint BEFORE emitting (durability before visibility)
        await self._store.save_interaction_checkpoint(
            request_id, self._step_id, self._conv_id, request_payload
        )
        # Emit AWAITING_TOOL_PERMISSION event
        event = StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id=self._step_id,
            conv_id=self._conv_id,
            agent_id=self._agent_id,
            parent_step_id=None,
            state=StepState.AWAITING_TOOL_PERMISSION,
            event_type="interaction_request",
            input=request_payload,
            output={},
            seq=0,  # runtime's _make_emit will overwrite seq; gate uses 0 placeholder
            timestamp=__import__("time").time(),
        )
        # Persist + yield via EventStream
        persisted = await self._stream.emit(event)
        yield persisted

        # Delegate to InteractionAdapter (blocks until user responds)
        response = await self._adapter.request_tool_permission(
            tool_name=tool_name, tool_args=tool_input,
        )
        action_str = getattr(response, "action", "deny")
        # Clean up checkpoint
        await self._store.delete_interaction_checkpoint(request_id)

        if action_str == "deny":
            self._cache.deny(tool_name, input_hash)
            self.last_result = PermissionResult(
                decision=PermissionDecision.DENY,
                reason="user denied",
                request_id=request_id,
            )
            return
        if action_str == "allow_session":
            self._cache.allow_session(tool_name, input_hash)
        # allow_once: no cache update
        self.last_result = PermissionResult(
            decision=PermissionDecision.ALLOW,
            reason=f"user {action_str}",
            request_id=request_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_gate.py -v`
Expected: PASS (12 tests)

If the `seq=0` placeholder causes issues with EventStream's `set_step_state` (because step_state is keyed by step_id and the runtime assigns seq via `_make_emit`), note that `PermissionGate.check()` is called *inside* `run_step`'s ACTING loop, and the event it yields will be re-emitted by the runtime's own `_make_emit` — see Task 6 for how this is wired. For Task 4's unit tests, the `seq=0` is fine because the tests only inspect `events[0].state` and `events[0].input`, not `seq`.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py \
        packages/derisk-core/tests/agent/core/v2/test_permission_gate.py
git commit -m "feat(agent-v2): PermissionGate 5 级检查链"
```

---

## Task 5: Wire PermissionGate into run_step + fix P0 Important #1 (resume_step acting_fn) + #2 (validate_transition enforcement)

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py` (new)
- Test: `packages/derisk-core/tests/agent/core/v2/test_runtime.py` (existing — verify regression-free)

**Interfaces:**
- Modifies `run_step()` signature to add 2 optional params:
  - `permission_gate: Optional[PermissionGate] = None`
  - (existing `acting_fn` unchanged)
- Modifies `resume_step()` signature to add:
  - `permission_gate: Optional[PermissionGate] = None`
  - `acting_fn: Optional[ActingFn] = None` (already exists, but P0 dropped it on redo path — now used)
- Adds to `runtime.py`:
  - `_validate_and_track_transition(prev_state, new_state)` helper — calls `validate_transition`, raises `IllegalTransitionError` on invalid. Tracks previous state per step_id.
  - `_run_acting_phase(emit, gate, tool_calls, acting_fn)` async generator — yields ACTING/OBSERVING events, calls `gate.check()` first (yielding any AWAITING events), skips `acting_fn` if gate denies.
- `_make_emit` now calls `_validate_and_track_transition` before persisting.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step, resume_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk.agent.core.v2.permission_gate import PermissionGate, PermissionDecision
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache
from derisk.agent.core.v2.step_state import StepState, IllegalTransitionError
from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield DbStateStore(path)
    os.unlink(path)


async def thinking_fn(input_):
    yield {"token": "calling tool"}
    yield {"token": "", "tool_calls": [{"tool": "read_file", "input": {"path": "/x"}}]}


async def acting_fn(tool_call):
    return {"result": f"executed:{tool_call['tool']}"}


def _make_gate(store, mode=PermissionMode.DEFAULT, ruleset=None, adapter=None):
    stream = EventStream(store)
    return PermissionGate(
        state_store=store, event_stream=stream,
        interaction_adapter=adapter,
        session_cache=SessionPermissionCache(),
        ruleset=ruleset, mode=mode,
        step_id="step-test", conv_id="conv-1", agent_id="agent-1",
    )


async def test_run_step_with_permission_allow_executes_tool(store):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _make_gate(store, ruleset=ruleset)
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert tool_results[0].output == {"result": "executed:read_file"}
    assert events[-1].state is StepState.DONE


async def test_run_step_with_permission_deny_skips_tool(store):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.DENY)
    }, default_action=PermissionAction.ALLOW)
    gate = _make_gate(store, ruleset=ruleset)
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    # ACTING tool_call event IS emitted (we attempted the call), but no tool_result
    assert len(tool_calls) == 1
    assert len(tool_results) == 0
    # The tool_call event's output should indicate denial
    assert tool_calls[0].output.get("denied") is True
    assert events[-1].state is StepState.DONE


async def test_run_step_with_permission_ask_emits_awaiting(store):
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            class R: action = "allow_once"
            return R()
    gate = _make_gate(store, ruleset=ruleset, adapter=FakeAdapter())
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    awaiting = [e for e in events if e.state is StepState.AWAITING_TOOL_PERMISSION]
    assert len(awaiting) == 1
    tool_results = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_results) == 1  # tool executed after user allowed
    assert events[-1].state is StepState.DONE


async def test_resume_step_redoes_acting_phase_with_permission(store):
    """P0 Important #1 fix: resume_step must run acting_fn on redo path."""
    from derisk.agent.core.v2.step_event import StepEvent
    stream = EventStream(store)
    # Simulate a crash mid-ACTING: step-pre got a tool_call event but no tool_result
    await stream.emit(StepEvent(
        event_id="evt-pre-1", step_id="step-pre", conv_id="conv-1", agent_id="agent-1",
        parent_step_id=None, state=StepState.THINKING, event_type="llm_token",
        input={"prompt": "hi"}, output={"token": "partial"}, seq=0, timestamp=0.0,
    ))
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = PermissionGate(
        state_store=store, event_stream=stream, interaction_adapter=None,
        session_cache=SessionPermissionCache(), ruleset=ruleset,
        mode=PermissionMode.DEFAULT, step_id="step-pre", conv_id="conv-1", agent_id="agent-1",
    )
    events = []
    async for e in resume_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                                 thinking_fn, acting_fn, step_id="step-pre",
                                 permission_gate=gate):
        events.append(e)
    tool_calls = [e for e in events if e.event_type == "tool_call"]
    tool_results = [e for e in events if e.event_type == "tool_result"]
    # P0 Important #1 fix: acting_fn IS called on redo path
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert events[-1].state is StepState.DONE


async def test_run_step_enforces_invalid_transition(store):
    """P0 Important #2 fix: validate_transition is wired into _make_emit."""
    # We can't easily trigger an invalid transition from outside run_step's normal flow,
    # but we can test _validate_and_track_transition directly
    from derisk.agent.core.v2.runtime import _validate_and_track_transition
    # Valid: INIT -> THINKING
    _validate_and_track_transition("step-1", None, StepState.INIT)
    _validate_and_track_transition("step-1", StepState.INIT, StepState.THINKING)
    # Invalid: INIT -> DONE (skips THINKING)
    with pytest.raises(IllegalTransitionError):
        _validate_and_track_transition("step-2", StepState.INIT, StepState.DONE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime_permission.py -v`
Expected: FAIL with `TypeError: run_step() got an unexpected keyword argument 'permission_gate'`

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`. The current file (after P0 cleanup) has `_make_emit`, `_run_thinking_phase`, `run_step`, `resume_step`. We will:

1. Re-add `validate_transition` + `IllegalTransitionError` imports.
2. Add a module-level `_step_state_tracker: dict[str, StepState]` and `_validate_and_track_transition(step_id, prev, new)` helper.
3. Modify `_make_emit`'s `emit()` to call `_validate_and_track_transition` before constructing the event.
4. Add `_run_acting_phase(emit, gate, tool_calls, acting_fn)` async generator.
5. Modify `run_step` to accept `permission_gate` and use `_run_acting_phase`.
6. Modify `resume_step` to accept `permission_gate`, use `_run_acting_phase` (fixes P0 Important #1), and handle the `resume_awaiting` case (P0 Important #3 — but minimally: if `step_id` is given and the last state for that step is `AWAITING_*`, yield a single `AWAITING_*` event and return without re-running thinking).

Full new content of `runtime.py`:

```python
# packages/derisk-core/src/derisk/agent/core/v2/runtime.py
"""run_step()——V2 Runtime 入口.

P0: INIT → THINKING → ACTING（可选）→ OBSERVING → DONE
P1: + PermissionGate 在 ACTING 前拦截，AWAITING_TOOL_PERMISSION 状态
崩溃恢复：每个 yield 前持久化，resume_step 从 StateStore 重放 + 重做未完成 step。
"""
from __future__ import annotations
import uuid
import time
from typing import AsyncGenerator, Callable, Awaitable, Optional, Dict
from derisk.agent.core.v2.step_state import (
    StepState, VALID_TRANSITIONS, validate_transition, IllegalTransitionError,
)
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.event_stream import EventStream


ThinkingFn = Callable[[dict], AsyncGenerator[dict, None]]
ActingFn = Callable[[dict], Awaitable[dict]]

_AWAITING_STATES = {
    StepState.AWAITING_USER,
    StepState.AWAITING_TOOL_PERMISSION,
    StepState.AWAITING_SUB_AGENT,
}

# Per-process tracker of the last state per step_id. Used by validate_transition.
# In a multi-process setup each process has its own tracker and loads initial
# state from StateStore on resume.
_step_state_tracker: Dict[str, StepState] = {}


def _validate_and_track_transition(step_id: str, prev: Optional[StepState], new: StepState) -> None:
    """Validate prev -> new transition; raise on invalid; track new state.

    If prev is None, we trust the caller (initial state or resume from store).
    """
    if prev is not None:
        if not validate_transition(prev, new):
            raise IllegalTransitionError(
                f"Invalid transition for step {step_id}: {prev.value} -> {new.value}"
            )
    _step_state_tracker[step_id] = new


def _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start):
    """创建 emit 函数：构造 StepEvent、校验状态转换、持久化、返回。"""
    seq = {"n": seq_start}

    async def emit(state, event_type, input_data=None, output_data=None):
        prev = _step_state_tracker.get(step_id)
        _validate_and_track_transition(step_id, prev, state)
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


async def _run_acting_phase(emit, gate, tool_calls, acting_fn):
    """ACTING + OBSERVING 阶段。每个 tool_call 前 PermissionGate.check()。"""
    for tc in tool_calls:
        if gate is not None:
            async for perm_event in gate.check(tc):
                yield perm_event
            result = gate.last_result
            if result.decision == PermissionDecision.DENY:
                yield await emit(
                    StepState.ACTING, "tool_call",
                    input_data=tc, output_data={"denied": True, "reason": result.reason},
                )
                continue
            # AWAITING path already emitted its event via gate.check()
            # ALLOW falls through to execute
        yield await emit(StepState.ACTING, "tool_call", input_data=tc)
        if acting_fn is not None:
            result_dict = await acting_fn(tc)
            yield await emit(StepState.OBSERVING, "tool_result", output_data=result_dict)


# Import here to avoid circular import at module load
from derisk.agent.core.v2.permission_gate import PermissionGate, PermissionDecision  # noqa: E402


async def run_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
) -> AsyncGenerator[StepEvent, None]:
    """跑一个 step，yield 所有 StepEvent。每个事件持久化后再 yield。"""
    stream = EventStream(state_store)
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    if permission_gate is not None:
        permission_gate._step_id = step_id  # bind gate to this step
    emit = _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start=0)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    if result_box["tool_calls"]:
        async for e in _run_acting_phase(emit, permission_gate, result_box["tool_calls"], acting_fn):
            yield e

    yield await emit(StepState.DONE, "step_done")


async def resume_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
) -> AsyncGenerator[StepEvent, None]:
    """从崩溃点续接。

    - 无 step_id：等价 run_step
    - 有 step_id 且最后状态是 AWAITING_*：恢复到等待状态（不重跑 thinking）
    - 有 step_id 且最后状态是 THINKING/ACTING/OBSERVING/INIT：重做该 step
    """
    if not step_id:
        async for e in run_step(agent_id, conv_id, input_, state_store,
                                thinking_fn, acting_fn, permission_gate=permission_gate):
            yield e
        return

    # Inspect last state for this step
    state_result = await state_store.get_step_state(step_id)
    last_state = state_result[0] if state_result else None

    stream = EventStream(state_store)
    if permission_gate is not None:
        permission_gate._step_id = step_id
    existing = await state_store.get_events(conv_id)
    seq_start = existing[-1].seq + 1 if existing else 0
    emit = _make_emit(stream, step_id, conv_id, agent_id, None, seq_start)

    # P0 Important #3: resume_awaiting path
    if last_state in _AWAITING_STATES:
        # Restore the awaiting state without re-running thinking
        # _validate_and_track_transition needs prev=None to skip the check
        # (the step's persisted state is already this; we're re-emitting for SSE)
        _step_state_tracker.pop(step_id, None)
        yield await emit(last_state, "interaction_request",
                         input_data={"reason": f"resumed from {last_state.value}"})
        return

    # redo_step path: re-run thinking + acting (P0 Important #1: acting_fn now included)
    _step_state_tracker.pop(step_id, None)  # reset tracker so INIT is valid
    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    if result_box["tool_calls"]:
        async for e in _run_acting_phase(emit, permission_gate, result_box["tool_calls"], acting_fn):
            yield e

    yield await emit(StepState.DONE, "step_done")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime_permission.py -v`
Expected: PASS (5 tests)

Also run the existing runtime tests + full v2 regression:
Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime.py -v`
Expected: PASS (4 tests — P0 runtime tests must still pass)

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS (all v2 tests, pristine output)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/runtime.py \
        packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py
git commit -m "feat(agent-v2): PermissionGate 接入 run_step + 修复 P0 三个 Important"
```

---

## Task 6: Public API exports + full regression

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/__init__.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_package.py` (existing — extend)

**Interfaces:**
- Adds to `__init__.py` exports: `PermissionMode`, `PermissionGate`, `PermissionResult`, `PermissionDecision`, `SessionPermissionCache`, `hash_tool_input`, `NoInteractionAdapterError`.

- [ ] **Step 1: Write the failing test (extend existing test_package.py)**

Open `packages/derisk-core/tests/agent/core/v2/test_package.py` and add to the import block + assertions:

```python
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
    PermissionMode,
    PermissionGate,
    PermissionResult,
    PermissionDecision,
    SessionPermissionCache,
    hash_tool_input,
    NoInteractionAdapterError,
)


def test_all_public_names_importable():
    assert StepState.INIT.value == "init"
    assert callable(run_step)
    assert callable(resume_step)
    assert callable(validate_transition)
    assert issubclass(IllegalTransitionError, Exception)
    assert issubclass(DbStateStore, StateStore)
    # P1 additions
    assert PermissionMode.DEFAULT.value == "default"
    assert PermissionMode.PLAN.value == "plan"
    assert PermissionMode.AUTO.value == "auto"
    assert PermissionMode.BYPASS.value == "bypass"
    assert callable(hash_tool_input)
    assert PermissionDecision.ALLOW == "allow"
    assert PermissionDecision.DENY == "deny"
    assert PermissionDecision.AWAITING == "awaiting"
    assert issubclass(NoInteractionAdapterError, RuntimeError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_package.py -v`
Expected: FAIL with `ImportError: cannot import name 'PermissionMode' from 'derisk.agent.core.v2'`

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/__init__.py` and add the new imports + `__all__` entries:

```python
"""V2 Runtime——Agent 框架内核.

六件套中的五件在 P1 落地：StepState/EventStream/StateStore/Recovery/PermissionGate。
SubAgent Runtime 在 P2 加。

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
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache, hash_tool_input
from derisk.agent.core.v2.permission_gate import (
    PermissionGate,
    PermissionResult,
    PermissionDecision,
    NoInteractionAdapterError,
)

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
    "PermissionMode",
    "PermissionGate",
    "PermissionResult",
    "PermissionDecision",
    "SessionPermissionCache",
    "hash_tool_input",
    "NoInteractionAdapterError",
]
```

- [ ] **Step 4: Run test to verify it passes + full regression**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_package.py -v`
Expected: PASS

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS (all v2 tests, pristine output — should be 40+ tests now)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/__init__.py \
        packages/derisk-core/tests/agent/core/v2/test_package.py
git commit -m "feat(agent-v2): P1 公开 API 导出（PermissionGate 全家桶）"
```

---

## Self-Review

**1. Spec coverage (P1 scope = spec §9.3 PermissionGate 5-level + §9.1 InteractionRequest persistence + P0遗留 3 Important):**
- ✅ §9.3 Level 1 (PermissionMode short-circuit: bypass/auto/plan) → Task 4 `test_bypass_mode_allows`, `test_auto_mode_allows`, `test_plan_mode_denies_side_effect_tool`, `test_plan_mode_allows_readonly_tool`
- ✅ §9.3 Level 2 (session cache) → Task 4 `test_session_cache_skips_ruleset`, `test_ask_allow_session_caches_for_session`
- ✅ §9.3 Level 3 (permission_ruleset ALLOW/DENY/ASK) → Task 4 `test_ruleset_allow_short_circuits`, `test_ruleset_deny_short_circuits`
- ⏭️ §9.3 Level 4 (Tool.check_permissions) — **P1 defers** (spec says "类似 claude-code" but Tool base class has no such method today; adding it touches `resource/tool/base.py` which is a compat shim — needs careful P2 coordination with Tool refactor). The plan note in Task 4 explicitly marks this as P2.
- ✅ §9.3 Level 5 (ask → InteractionRequest persist + delegate) → Task 4 `test_ask_emits_awaiting_event_and_persists_checkpoint`, `test_ask_deny_response_persists_deny`
- ✅ §9.1 InteractionRequest 持久化 → Task 3 `interaction_checkpoint` table + 3 methods
- ✅ §9.2 PermissionMode 4 模式 → Task 1
- ✅ P0 Important #1 (resume_step acting_fn drop) → Task 5 `test_resume_step_redoes_acting_phase_with_permission`
- ✅ P0 Important #2 (validate_transition unenforced) → Task 5 `test_run_step_enforces_invalid_transition` + `_validate_and_track_transition` wired into `_make_emit`
- ✅ P0 Important #3 (resume_step no resume_awaiting path) → Task 5 `resume_step` now branches on `last_state in _AWAITING_STATES`
- ⏭️ §9.4 老 `ActionOutput.ask_user` 适配层 — **P1 defers** (spec §11.4 puts "废弃 ActionOutput.ask_user" in P4 cleanup; P1 only adds the new PermissionGate, doesn't touch legacy). The plan explicitly lists this as not-touched in File Structure.
- ⏭️ §9.5 前端交互 UI — out of P1 scope (frontend work, separate plan)

**2. Placeholder scan:** No TBD/TODO/"implement later"/"add error handling". The one `TODO(P2)` comment in Task 4's implementation is intentional scope marking for Level 4 deferral — not a placeholder. All code blocks complete.

**3. Type consistency:**
- `PermissionMode` enum values (`"default"`/`"plan"`/`"auto"`/`"bypass"`) — consistent across Task 1 (definition), Task 4 (gate checks `is PermissionMode.BYPASS` etc.), Task 5 (tests use `PermissionMode.DEFAULT`/`PLAN`).
- `PermissionResult` fields (`decision`, `reason`, `request_id`) — defined Task 4, read in Task 5 (`gate.last_result.decision`, `result.reason`).
- `PermissionDecision` constants (`ALLOW`/`DENY`/`AWAITING`) — defined Task 4 as class attributes (not enum, to keep `==` comparison simple), used in Task 5 tests.
- `SessionPermissionCache` methods (`is_allowed`, `allow_session`, `allow_once`, `deny`, `clear`) — defined Task 2, used in Task 4 (`self._cache.is_allowed`, `allow_session`, `deny`) and Task 5 tests.
- `hash_tool_input(input_: dict) -> str` — defined Task 2, used Task 4 (`hash_tool_input(tool_input)`), imported in Task 4/5 tests.
- `StateStore.save_interaction_checkpoint(request_id, step_id, conv_id, request_payload)` — defined Task 3, called Task 4 (`self._store.save_interaction_checkpoint(request_id, self._step_id, self._conv_id, request_payload)`).
- `run_step(..., permission_gate=None)` / `resume_step(..., permission_gate=None)` — added Task 5, used Task 5 tests.
- `_validate_and_track_transition(step_id, prev, new)` — defined Task 5, tested Task 5.

**4. P1 简化声明：**
- Level 4 (Tool.check_permissions) deferred to P2 — marked inline with `TODO(P2)`. Adding it requires touching the Tool base class compat shim, which is a separate refactor.
- `_is_side_effecting(tool_name)` uses a substring heuristic. P2 should replace with `Tool.metadata.risk_level` once Tool metadata is wired. Marked in code comment.
- `resume_step` resume_awaiting path re-emits the awaiting event with a generic reason. Full restoration (re-delivering the original InteractionRequest payload from checkpoint) is a P2/P3 refinement once InteractionAdapter integration deepens.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-agent-v2-runtime-p1.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
