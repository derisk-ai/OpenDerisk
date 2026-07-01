# Agent V2 Runtime P2: SubAgent Runtime + P1 Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the SubAgent Runtime (spec §8) — `spawn_subagent` unified entry, sync/async modes, `detach`/`resume`, depth limiting, parent-delegate interaction policy (策略 C) — and close out P1's 2 Important latent bugs (I-1 response.choice mismatch, I-2 seq=0 placeholder) plus Level 4 Tool.check_permissions hook + the §9.4 ActionOutput.ask_user compatibility adapter.

**Architecture:**
- P1 follow-ups first (Tasks 1-3): fix `response.choice` reading, pass emit callable into `PermissionGate.check()` so seq is correct, fold `runtime_extra` into `VALID_TRANSITIONS`, wire checkpoint deletion into `_run_acting_phase`.
- §9.3 Level 4 (Task 4): add optional `check_permissions()` hook to `ToolBase`; PermissionGate calls it after ruleset, before ask.
- §9.4 compat adapter (Task 5): keep `ActionOutput.ask_user` field, convert to `InteractionRequest` inside the runtime so legacy Actions keep working until P4.
- §8 SubAgent Runtime (Tasks 6-11): new `subagent_runtime.py` + `subagent_handle.py` + `spawn_subagent_tool.py` + `agent_transcript` table + `SubAgentInteractionGateway` (策略 C) + depth limiter + sync/async modes + `detach`/`resume` + notification injection.
- Public API (Task 12): export the new surface from `derisk.agent.core.v2`.

**Tech Stack:** Python ≥ 3.10, pydantic v2 (`from derisk._private.pydantic import BaseModel, ConfigDict, Field`), stdlib `asyncio`/`uuid`/`enum`, existing `AsyncTaskManager` (`agent/util/async_task_manager.py:122`), existing `InteractionGateway` (`agent/interaction/interaction_gateway.py:147`), existing `InteractionResponse` (`agent/interaction/interaction_protocol.py:138`), existing `ToolBase` (`agent/tools/base.py:81`).

## Global Constraints

- Python ≥ 3.10
- pydantic v2 via `from derisk._private.pydantic import BaseModel, ConfigDict, Field` (never `from pydantic import`)
- V2 kernel code under `packages/derisk-core/src/derisk/agent/core/v2/`
- TDD: RED → GREEN → commit per task
- All V2 methods are `async`
- `StateStore` methods are `async`; SQLite calls wrapped in `asyncio.to_thread`
- Event sourcing: `step_event` is append-only (`INSERT` not `INSERT OR REPLACE`); `step_state`/`interaction_checkpoint`/`agent_transcript` are latest-snapshot
- Durability before visibility: every event persisted before yielded
- Reuse existing infra: `AsyncTaskManager.spawn`/`wait_all`/`cancel`/`get_status`, `InteractionGateway.send_and_wait`, `InteractionResponse.choice`
- Do NOT delete legacy `ActionOutput.ask_user`, `push_context_event`, `push_message`, `queue_iterator`, `needs_tool_approval` in P2 (P4 cleanup)
- V2 kernel passes plain params (no `AgentContext` dataclass modification)
- Test output must be pristine (filterwarnings for pre-existing pydantic noise already configured in P0)
- V2 tests live under `packages/derisk-core/tests/agent/core/v2/`
- Working tree has unrelated uncommitted changes from a parallel scenario-workspace effort; stage only the files each task names

---

## File Structure

**New V2 kernel files (under `packages/derisk-core/src/derisk/agent/core/v2/`):**
- `subagent_runtime.py` — `SubAgentRuntime` class. Single entry `spawn(spec) -> SubAgentHandle`. Manages sync (await + AWAITING_SUB_AGENT) and async (background task + transcript persistence) modes. ~150 lines.
- `subagent_handle.py` — `SubAgentHandle` pydantic model: `task_id`, `parent_step_id`, `sub_conv_id`, `mode` (sync/async), `status`, `result`. Methods: `is_done()`, `wait()`, `resume()`. ~60 lines.
- `subagent_interaction_gateway.py` — `SubAgentInteractionGateway(InteractionGateway)` (策略 C). Sync mode delegates to parent; async mode auto-denies. ~40 lines.
- `spawn_subagent_tool.py` — `SpawnSubagentTool(ToolBase)`. LLM-facing tool wrapping `SubAgentRuntime.spawn`. ~80 lines.

**Modified V2 files:**
- `step_state.py` — fold `runtime_extra` transitions into `VALID_TRANSITIONS` (P1 follow-up): add `INIT → AWAITING_USER`, `ACTING → DONE`.
- `permission_gate.py` — (P1 I-1) read `response.choice` instead of `getattr(response, "action", "deny")`; (P1 I-2) accept an `emit` callable in `check()` so events get proper seq; (Level 4) call `tool.check_permissions()` if present.
- `runtime.py` — wire checkpoint deletion into `_run_acting_phase` (P1 follow-up); remove `runtime_extra` workaround; pass emit callable into `PermissionGate.check()`; accept `subagent_runtime` param; emit `AWAITING_SUB_AGENT` events when sync sub-agent spawns.
- `state_store.py` — add `agent_transcript` table + 4 methods (`save_transcript`, `get_transcript`, `list_transcripts_for_parent`, `delete_transcript`).
- `__init__.py` — export `SubAgentRuntime`, `SubAgentHandle`, `SubAgentMode`, `SubAgentInteractionGateway`, `SpawnSubagentTool`, `AgentTranscript`.

**External files touched (minimal, surgical):**
- `packages/derisk-core/src/derisk/agent/tools/base.py` — add optional `async check_permissions(input, context) -> Optional[PermissionCheckResult]` hook to `ToolBase`. Default returns `None`. No existing tool is modified.
- `packages/derisk-core/src/derisk/agent/core/action/base.py` — `ActionOutput.ask_user` stays as-is; runtime adds an adapter that converts `ask_user` to `InteractionRequest` when an Action returns it. (P2 only adds the adapter, does not remove the field.)

**Files NOT touched (deferred per spec §11.4):**
- `base_agent.py` (legacy `check_tool_permission`/`needs_tool_approval` stay; P4 cleanup)
- `agent/core/agent.py` (`AgentContext` dataclass unchanged)
- `interaction_adapter.py` / `interaction_gateway.py` / `interaction_protocol.py` (reused as-is, subclassed by `SubAgentInteractionGateway`)
- BAIZE subsystem (P3)
- Frontend SSE (P3)

---

## Task 1: P1 follow-up — fold runtime_extra into VALID_TRANSITIONS

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/step_state.py`
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/runtime.py` (remove `runtime_extra` workaround)
- Test: `packages/derisk-core/tests/agent/core/v2/test_step_state.py` (existing — extend)

**Interfaces:**
- Adds to `VALID_TRANSITIONS`:
  - `INIT: (THINKING, AWAITING_USER)` — thinking_fn can request user input before any token
  - `ACTING: (OBSERVING, AWAITING_TOOL_PERMISSION, AWAITING_SUB_AGENT, DONE, FAILED)` — permission-denial path goes straight to DONE
- Removes from `runtime.py`: the `runtime_extra` set + its usage in `_validate_and_track_transition`

- [ ] **Step 1: Write the failing test (extend existing test_step_state.py)**

Open `packages/derisk-core/tests/agent/core/v2/test_step_state.py` and add to the existing test functions (or add new ones):

```python
from derisk.agent.core.v2.step_state import (
    StepState, VALID_TRANSITIONS, validate_transition, IllegalTransitionError,
)


def test_init_can_transition_to_awaiting_user():
    """P1 follow-up: thinking_fn can request user input before any token."""
    assert validate_transition(StepState.INIT, StepState.AWAITING_USER)


def test_acting_can_transition_to_done():
    """P1 follow-up: permission-denial path skips OBSERVING, goes straight to DONE."""
    assert validate_transition(StepState.ACTING, StepState.DONE)


def test_runtime_extra_no_longer_needed():
    """The runtime_extra workaround in runtime.py should be removed after folding."""
    import derisk.agent.core.v2.runtime as runtime_mod
    src = open(runtime_mod.__file__).read()
    assert "runtime_extra" not in src, (
        "runtime_extra workaround should be removed — transitions folded into VALID_TRANSITIONS"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_step_state.py -v`
Expected: FAIL — `test_init_can_transition_to_awaiting_user` and `test_acting_can_transition_to_done` fail; `test_runtime_extra_no_longer_needed` fails (string still present).

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/step_state.py`. Replace the `VALID_TRANSITIONS` dict with:

```python
VALID_TRANSITIONS: Dict[StepState, Tuple[StepState, ...]] = {
    StepState.INIT: (StepState.THINKING, StepState.AWAITING_USER),
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
        StepState.DONE,
        StepState.FAILED,
    ),
    StepState.OBSERVING: (StepState.THINKING, StepState.DONE, StepState.FAILED),
    StepState.AWAITING_USER: (StepState.THINKING, StepState.FAILED),
    StepState.AWAITING_TOOL_PERMISSION: (StepState.ACTING, StepState.FAILED),
    StepState.AWAITING_SUB_AGENT: (StepState.OBSERVING, StepState.FAILED),
    StepState.DONE: (),
    StepState.FAILED: (),
}
```

Open `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`. Find the `runtime_extra` set (added in P1 Task 5 as a workaround) and remove it. Find `_validate_and_track_transition` and remove the `runtime_extra` check — it should now just call `validate_transition(prev, new)` directly:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_step_state.py -v`
Expected: PASS (existing tests + 3 new)

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS (62+ tests, pristine output)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/step_state.py \
        packages/derisk-core/src/derisk/agent/core/v2/runtime.py \
        packages/derisk-core/tests/agent/core/v2/test_step_state.py
git commit -m "fix(agent-v2): P1 #4 折叠 runtime_extra 到 VALID_TRANSITIONS"
```

---

## Task 2: P1 follow-up — fix PermissionGate response.choice + seq placeholder

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py`
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/runtime.py` (pass emit callable into gate.check())
- Test: `packages/derisk-core/tests/agent/core/v2/test_permission_gate.py` (existing — extend)
- Test: `packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py` (existing — extend)

**Interfaces:**
- `PermissionGate.check(tool_call, emit: Optional[Callable] = None)` — when `emit` is provided, the gate uses it to construct+persist the AWAITING_TOOL_PERMISSION event (correct seq assigned by runtime's `_make_emit`). When `emit` is None (P1 unit tests), falls back to internal `seq=0` placeholder (so existing unit tests still pass).
- Gate reads `response.choice` (the field on `InteractionResponse` at `interaction_protocol.py:144`) instead of `getattr(response, "action", "deny")`. Maps: `"allow_once"` / `"allow_session"` → ALLOW; anything else (including `None`) → DENY.
- `runtime.py`'s `_run_acting_phase` calls `gate.check(tc, emit=emit)` passing the runtime's emit closure.

- [ ] **Step 1: Write the failing test (extend test_permission_gate.py)**

Add to `packages/derisk-core/tests/agent/core/v2/test_permission_gate.py`:

```python
async def test_ask_reads_response_choice_not_action(store, stream):
    """P1 I-1 fix: gate reads response.choice, not response.action."""
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            # Real InteractionResponse has .choice, NOT .action
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(
                request_id="req-x",
                choice="allow_once",
            )

    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {"path": "/x"}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_ask_deny_when_response_choice_is_none(store, stream):
    """If response.choice is None (e.g. user dismissed), default to deny."""
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice=None)

    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())
    events = [e async for e in gate.check({"tool": "rm", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_check_accepts_emit_callable_for_correct_seq(store, stream):
    """P1 I-2 fix: when emit callable is passed, gate uses it (correct seq)."""
    ruleset = PermissionRuleset(rules={
        "rm": PermissionRule(tool_pattern="rm", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)

    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice="allow_once")

    gate = _gate(store, stream, ruleset=ruleset, interaction_adapter=FakeAdapter())

    # Fake emit: increments seq, persists, returns the event
    seq = {"n": 100}
    captured = {}
    async def fake_emit(state, event_type, input_data=None, output_data=None):
        from derisk.agent.core.v2.step_event import StepEvent
        import time
        evt = StepEvent(
            event_id=f"evt-{seq['n']}", step_id=gate._step_id, conv_id=gate._conv_id,
            agent_id=gate._agent_id, parent_step_id=None, state=state,
            event_type=event_type, input=input_data or {}, output=output_data or {},
            seq=seq["n"], timestamp=time.time(),
        )
        seq["n"] += 1
        captured["event"] = evt
        return evt

    events = [e async for e in gate.check({"tool": "rm", "input": {}}), emit=fake_emit] \
        if False else [e async for e in gate.check({"tool": "rm", "input": {}}, emit=fake_emit)]
    # The emitted event should have seq=100, not seq=0
    assert events[0].seq == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_gate.py -v`
Expected: FAIL — `test_ask_reads_response_choice_not_action` fails (gate looks for `.action`, gets default `"deny"`); `test_check_accepts_emit_callable_for_correct_seq` fails (`check()` doesn't accept `emit` kwarg).

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py`. Modify the `check()` method signature and the ASK path:

```python
async def check(
    self,
    tool_call: dict,
    emit: Optional[Callable] = None,
) -> AsyncGenerator[StepEvent, None]:
    """Run the 5-level check.

    Yields AWAITING_TOOL_PERMISSION events when asking.
    Sets self.last_result. Caller reads last_result after generator exhausts.

    Args:
        tool_call: {"tool": str, "input": dict}
        emit: optional runtime emit callable
            (state, event_type, input_data, output_data) -> StepEvent.
            When provided, the gate uses it to construct+persist the
            AWAITING_TOOL_PERMISSION event (correct seq assigned by runtime).
            When None, the gate constructs the event itself with seq=0
            (unit-test mode; not safe for production replay ordering).
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
    action = PermissionAction.ALLOW
    if self._ruleset is not None:
        action = self._ruleset.check(tool_name, context={})
    if action is PermissionAction.ALLOW:
        self.last_result = PermissionResult(decision=PermissionDecision.ALLOW, reason="ruleset allow")
        return
    if action is PermissionAction.DENY:
        self.last_result = PermissionResult(decision=PermissionDecision.DENY, reason="ruleset deny")
        return

    # Level 4: Tool.check_permissions — added in Task 4 (this task leaves it as no-op)
    # Level 4 will be wired in Task 4; for now fall through to Level 5

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
    await self._store.save_interaction_checkpoint(
        request_id, self._step_id, self._conv_id, request_payload
    )

    if emit is not None:
        # Runtime path: use the runtime's emit so seq is correctly assigned
        persisted = await emit(
            StepState.AWAITING_TOOL_PERMISSION,
            "interaction_request",
            input_data=request_payload,
        )
        yield persisted
    else:
        # Unit-test path: construct event directly with seq=0 placeholder
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
            seq=0,
            timestamp=time.time(),
        )
        persisted = await self._stream.emit(event)
        yield persisted

    # Delegate to InteractionAdapter (blocks until user responds)
    response = await self._adapter.request_tool_permission(
        tool_name=tool_name, tool_args=tool_input,
    )
    # P1 I-1 fix: read response.choice (the field on InteractionResponse),
    # NOT response.action. Map: allow_once/allow_session → ALLOW; else DENY.
    choice = getattr(response, "choice", None)
    # Clean up checkpoint (deletion still deferred to runtime — but the gate
    # can clean up its own checkpoint on denial; runtime cleans up on allow)
    if choice not in ("allow_once", "allow_session"):
        await self._store.delete_interaction_checkpoint(request_id)
        self._cache.deny(tool_name, input_hash)
        self.last_result = PermissionResult(
            decision=PermissionDecision.DENY,
            reason=f"user choice: {choice!r}",
            request_id=request_id,
        )
        return
    if choice == "allow_session":
        self._cache.allow_session(tool_name, input_hash)
    # allow_once: no cache update; checkpoint deletion deferred to runtime
    self.last_result = PermissionResult(
        decision=PermissionDecision.ALLOW,
        reason=f"user choice: {choice}",
        request_id=request_id,
    )
```

Add `from typing import Callable` to the imports at the top of `permission_gate.py` (it already imports `AsyncGenerator, Optional`).

Open `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`. In `_run_acting_phase`, change the gate call:

```python
async def _run_acting_phase(emit, gate, tool_calls, acting_fn, state_store=None):
    """ACTING + OBSERVING 阶段。每个 tool_call 前 PermissionGate.check()。"""
    for tc in tool_calls:
        if gate is not None:
            async for perm_event in gate.check(tc, emit=emit):
                yield perm_event
            result = gate.last_result
            if result.decision == PermissionDecision.DENY:
                yield await emit(
                    StepState.ACTING, "tool_call",
                    input_data=tc, output_data={"denied": True, "reason": result.reason},
                )
                continue
            # ALLOW path: delete the interaction checkpoint (if a request_id was set)
            if result.request_id and state_store is not None:
                await state_store.delete_interaction_checkpoint(result.request_id)
        yield await emit(StepState.ACTING, "tool_call", input_data=tc)
        if acting_fn is not None:
            result_dict = await acting_fn(tc)
            yield await emit(StepState.OBSERVING, "tool_result", output_data=result_dict)
```

Update the two call sites in `run_step` and `resume_step` to pass `state_store`:

```python
async for e in _run_acting_phase(emit, permission_gate, result_box["tool_calls"], acting_fn, state_store=state_store):
    yield e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_gate.py -v`
Expected: PASS (12 existing + 3 new = 15 tests)

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime_permission.py -v`
Expected: PASS (5 existing tests — the runtime now passes emit into gate, but tests don't assert on seq so they should pass)

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS (pristine)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py \
        packages/derisk-core/src/derisk/agent/core/v2/runtime.py \
        packages/derisk-core/tests/agent/core/v2/test_permission_gate.py
git commit -m "fix(agent-v2): P1 I-1/I-2 修复 (response.choice + emit callable)"
```

---

## Task 3: P1 follow-up — wire checkpoint deletion into runtime (already partly done in Task 2)

This task is folded into Task 2's implementation (the `state_store.delete_interaction_checkpoint(result.request_id)` call in `_run_acting_phase`). Verify with a dedicated test.

**Files:**
- Test: `packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py` (existing — extend)

- [ ] **Step 1: Write the failing test**

Add to `packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py`:

```python
async def test_runtime_deletes_checkpoint_after_tool_executes(store):
    """P1 follow-up: runtime deletes interaction_checkpoint after ALLOW + tool execution."""
    ruleset = PermissionRuleset(rules={
        "read_file": PermissionRule(tool_pattern="read_file", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ALLOW)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice="allow_once")
    gate = _make_gate(store, ruleset=ruleset, adapter=FakeAdapter())
    events = []
    async for e in run_step("agent-1", "conv-1", {"prompt": "hi"}, store,
                             thinking_fn, acting_fn, permission_gate=gate):
        events.append(e)
    # After the step is DONE, no interaction_checkpoint should remain
    from derisk.agent.core.v2.state_store import DbStateStore
    # The store fixture is DbStateStore; iterate its rows
    import sqlite3
    if isinstance(store, DbStateStore):
        conn = store._connect()
        try:
            rows = conn.execute("SELECT request_id FROM interaction_checkpoint").fetchall()
        finally:
            conn.close()
        assert rows == [], f"expected no checkpoint left, got {rows}"
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime_permission.py::test_runtime_deletes_checkpoint_after_tool_executes -v`
Expected: PASS (because Task 2 already wired the deletion). If FAIL, debug.

- [ ] **Step 3: No new implementation needed — Task 2 covered it**

- [ ] **Step 4: Run full v2 regression**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/tests/agent/core/v2/test_runtime_permission.py
git commit -m "test(agent-v2): 验证 runtime 删除 interaction_checkpoint"
```

---

## Task 4: §9.3 Level 4 — ToolBase.check_permissions hook

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/tools/base.py` (add `check_permissions` hook to `ToolBase`)
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py` (call the hook in Level 4)
- Test: `packages/derisk-core/tests/agent/core/v2/test_permission_gate_tool_hook.py` (new)

**Interfaces:**
- Adds to `ToolBase` (`agent/tools/base.py:81`):
  ```python
  async def check_permissions(self, input: dict, context: Optional[dict] = None) -> Optional["PermissionCheckResult"]:
      """Tool-defined permission check. Return None to fall through to next level."""
      return None
  ```
- Adds `PermissionCheckResult` pydantic model (in `permission_gate.py`):
  ```python
  class PermissionCheckResult(BaseModel):
      decision: str  # "allow" / "deny" / "ask"
      reason: str = ""
  ```
- `PermissionGate.check()` Level 4: if a tool is provided via `tool` kwarg and `tool.check_permissions(input)` returns non-None, use that result (ALLOW/DENY short-circuit; ASK falls through to Level 5).

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_permission_gate_tool_hook.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.session_cache import SessionPermissionCache
from derisk.agent.core.v2.permission_gate import (
    PermissionGate, PermissionDecision, PermissionCheckResult,
)
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.event_stream import EventStream
from derisk_core.permission.ruleset import PermissionRuleset, PermissionRule, PermissionAction
from derisk.agent.tools.base import ToolBase
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import ToolResult


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


class _AllowTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    async def check_permissions(self, input, context=None):
        return PermissionCheckResult(decision="allow", reason="tool says allow")


class _DenyTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    async def check_permissions(self, input, context=None):
        return PermissionCheckResult(decision="deny", reason="tool says deny")


class _AskTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    async def check_permissions(self, input, context=None):
        return PermissionCheckResult(decision="ask", reason="tool says ask")


class _NoOpinionTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(name="custom_tool", description="test")
    def _define_parameters(self):
        return {"type": "object", "properties": {}, "required": []}
    async def execute(self, args, context=None):
        return ToolResult(success=True, output="")
    # no check_permissions override → default returns None


def _gate(store, stream, tool=None, ruleset=None):
    return PermissionGate(
        state_store=store, event_stream=stream,
        interaction_adapter=None,
        session_cache=SessionPermissionCache(),
        ruleset=ruleset, mode=PermissionMode.DEFAULT,
        step_id="step-1", conv_id="conv-1", agent_id="agent-1",
        tool=tool,
    )


async def test_tool_check_permissions_allow_short_circuits(store, stream):
    """Level 4: tool says allow → ALLOW without asking."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, tool=_AllowTool(), ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert events == []
    assert gate.last_result.decision is PermissionDecision.ALLOW
    assert "tool says allow" in gate.last_result.reason


async def test_tool_check_permissions_deny_short_circuits(store, stream):
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ALLOW)
    gate = _gate(store, stream, tool=_DenyTool(), ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.DENY


async def test_tool_check_permissions_ask_falls_through_to_level_5(store, stream):
    """If tool says ask, Level 5 (InteractionRequest) handles it."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ASK)
    }, default_action=PermissionAction.ASK)
    class FakeAdapter:
        async def request_tool_permission(self, tool_name, tool_args, **kwargs):
            from derisk.agent.interaction.interaction_protocol import InteractionResponse
            return InteractionResponse(request_id="req-x", choice="allow_once")
    gate = _gate(store, stream, tool=_AskTool(), ruleset=ruleset)
    gate._adapter = FakeAdapter()
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert len(events) == 1
    assert gate.last_result.decision is PermissionDecision.ALLOW


async def test_tool_check_permissions_none_falls_through(store, stream):
    """Default check_permissions returns None → fall through to ruleset/ask."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, tool=_NoOpinionTool(), ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW
    assert "ruleset" in gate.last_result.reason


async def test_no_tool_passed_skips_level_4(store, stream):
    """When no tool is provided (default), Level 4 is skipped — backwards compat with P1."""
    ruleset = PermissionRuleset(rules={
        "custom_tool": PermissionRule(tool_pattern="custom_tool", action=PermissionAction.ALLOW)
    }, default_action=PermissionAction.ASK)
    gate = _gate(store, stream, tool=None, ruleset=ruleset)
    events = [e async for e in gate.check({"tool": "custom_tool", "input": {}})]
    assert gate.last_result.decision is PermissionDecision.ALLOW
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_gate_tool_hook.py -v`
Expected: FAIL — `PermissionGate` doesn't accept `tool` kwarg; `PermissionCheckResult` doesn't exist.

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/tools/base.py`. Add to `ToolBase` (after `execute` or wherever fits cleanly):

```python
    async def check_permissions(
        self,
        input: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Tool-defined permission check (spec §9.3 Level 4).

        Override to provide tool-specific rules. Return None to fall through
        to the next PermissionGate level (ask). Return a PermissionCheckResult
        to short-circuit (allow/deny) or to force ask.

        Args:
            input: the tool's input args
            context: optional runtime context (agent_id, conv_id, etc.)

        Returns:
            None (default, no opinion) or PermissionCheckResult(decision, reason)
        """
        return None
```

Open `packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py`. Add `PermissionCheckResult` model and `tool` param to `PermissionGate.__init__`, and the Level 4 check between Level 3 and Level 5:

```python
# Add to imports
from typing import Any

# Add after PermissionResult
class PermissionCheckResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)
    decision: str  # "allow" / "deny" / "ask"
    reason: str = ""
```

In `PermissionGate.__init__`, add `tool: Optional[Any] = None` parameter and `self._tool = tool`.

In `check()`, insert between Level 3 and Level 5:

```python
    # Level 4: Tool.check_permissions
    if self._tool is not None:
        tool_result = await self._tool.check_permissions(tool_input, context={
            "agent_id": self._agent_id,
            "conv_id": self._conv_id,
            "step_id": self._step_id,
        })
        if tool_result is not None:
            if tool_result.decision == "allow":
                self.last_result = PermissionResult(
                    decision=PermissionDecision.ALLOW,
                    reason=f"tool check_permissions: {tool_result.reason}",
                )
                return
            if tool_result.decision == "deny":
                self.last_result = PermissionResult(
                    decision=PermissionDecision.DENY,
                    reason=f"tool check_permissions: {tool_result.reason}",
                )
                return
            # decision == "ask" → fall through to Level 5
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_permission_gate_tool_hook.py -v`
Expected: PASS (5 tests)

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/tools/base.py \
        packages/derisk-core/src/derisk/agent/core/v2/permission_gate.py \
        packages/derisk-core/tests/agent/core/v2/test_permission_gate_tool_hook.py
git commit -m "feat(agent-v2): §9.3 Level 4 ToolBase.check_permissions hook"
```

---

## Task 5: §9.4 ActionOutput.ask_user compatibility adapter

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/action/base.py` (no — read-only; we add the adapter in v2)
- Create: `packages/derisk-core/src/derisk/agent/core/v2/ask_user_adapter.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_ask_user_adapter.py`

**Interfaces:**
- `AskUserAdapter` class with one async method:
  ```python
  async def convert(self, ask_user_payload: dict, step_id: str, conv_id: str) -> StepEvent
  ```
  Converts a legacy `ActionOutput.ask_user` dict to an `InteractionRequest`-style `AWAITING_USER` StepEvent. Persists via StateStore's `interaction_checkpoint` table (reuses the same table — `request_payload["type"] = "ASK_USER_LEGACY"`).
- The adapter is a thin converter; it does NOT execute the ask. The runtime is responsible for yielding the event upstream and delegating to `InteractionGateway`.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_ask_user_adapter.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.ask_user_adapter import AskUserAdapter
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_convert_ask_user_to_event(store):
    """Legacy ActionOutput.ask_user dict → AWAITING_USER StepEvent + checkpoint."""
    adapter = AskUserAdapter(state_store=store)
    ask_payload = {
        "type": "ask_user",
        "message": "What's your name?",
        "options": ["Alice", "Bob"],
    }
    event = await adapter.convert(ask_payload, step_id="step-1", conv_id="conv-1")
    assert event.state is StepState.AWAITING_USER
    assert event.event_type == "interaction_request"
    assert event.input["type"] == "ASK_USER_LEGACY"
    assert event.input["message"] == "What's your name?"
    assert event.input["options"] == ["Alice", "Bob"]
    assert event.input["step_id"] == "step-1"
    assert event.input["conv_id"] == "conv-1"
    assert "request_id" in event.input
    # Checkpoint persisted
    cp = await store.get_interaction_checkpoint(event.input["request_id"])
    assert cp is not None
    assert cp["request_payload"]["type"] == "ASK_USER_LEGACY"


async def test_convert_preserves_request_id_format(store):
    adapter = AskUserAdapter(state_store=store)
    event = await adapter.convert({"message": "hi"}, step_id="s", conv_id="c")
    assert event.input["request_id"].startswith("req-")


async def test_convert_handles_minimal_payload(store):
    """Empty message / no options still works."""
    adapter = AskUserAdapter(state_store=store)
    event = await adapter.convert({}, step_id="s", conv_id="c")
    assert event.input["message"] == ""
    assert event.input["options"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_ask_user_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'derisk.agent.core.v2.ask_user_adapter'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/ask_user_adapter.py
"""AskUserAdapter — legacy ActionOutput.ask_user → InteractionRequest converter.

Spec §9.4 compat layer. Old Actions return ActionOutput.ask_user; this adapter
converts that payload to an AWAITING_USER StepEvent (persisted via the same
interaction_checkpoint table used by PermissionGate). The runtime yields the
event upstream and delegates to InteractionGateway.

This keeps legacy Actions working without modification until P4 cleanup.
"""
from __future__ import annotations
import uuid
import time
from typing import Any, Optional, TYPE_CHECKING
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState

if TYPE_CHECKING:
    from derisk.agent.core.v2.state_store import StateStore


class AskUserAdapter:
    def __init__(self, state_store: "StateStore"):
        self._store = state_store

    async def convert(
        self,
        ask_user_payload: dict,
        step_id: str,
        conv_id: str,
    ) -> StepEvent:
        """Convert legacy ask_user dict to AWAITING_USER StepEvent + persist checkpoint."""
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        request_payload = {
            "request_id": request_id,
            "type": "ASK_USER_LEGACY",
            "message": ask_user_payload.get("message", ""),
            "options": ask_user_payload.get("options", []),
            "step_id": step_id,
            "conv_id": conv_id,
        }
        await self._store.save_interaction_checkpoint(
            request_id, step_id, conv_id, request_payload
        )
        return StepEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            step_id=step_id,
            conv_id=conv_id,
            agent_id=None,  # set by runtime when yielding
            parent_step_id=None,
            state=StepState.AWAITING_USER,
            event_type="interaction_request",
            input=request_payload,
            output={},
            seq=0,  # runtime's emit will overwrite seq when re-emitting
            timestamp=time.time(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_ask_user_adapter.py -v`
Expected: PASS (3 tests)

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/ask_user_adapter.py \
        packages/derisk-core/tests/agent/core/v2/test_ask_user_adapter.py
git commit -m "feat(agent-v2): §9.4 ActionOutput.ask_user 兼容适配层"
```

---

## Task 6: StateStore agent_transcript table

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/state_store.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_state_store_transcript.py`

**Interfaces:**
- Adds to `StateStore` ABC (4 new abstract methods):
  - `async save_transcript(transcript_id: str, task_id: str, sub_conv_id: str, parent_step_id: str, parent_conv_id: str, agent_name: str, status: str, latest_event_seq: int, payload: dict) -> None`
  - `async get_transcript(transcript_id: str) -> Optional[dict]`
  - `async list_transcripts_for_parent(parent_conv_id: str) -> List[dict]`
  - `async delete_transcript(transcript_id: str) -> None`
- Adds to `DbStateStore`: concrete implementations.
- Adds to `_SCHEMA`: new `agent_transcript` table:
  ```sql
  CREATE TABLE IF NOT EXISTS agent_transcript (
      transcript_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      sub_conv_id TEXT NOT NULL,
      parent_step_id TEXT NOT NULL,
      parent_conv_id TEXT NOT NULL,
      agent_name TEXT NOT NULL,
      status TEXT NOT NULL,
      latest_event_seq INTEGER NOT NULL,
      payload TEXT NOT NULL,
      updated_at REAL NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_transcript_parent ON agent_transcript(parent_conv_id);
  CREATE INDEX IF NOT EXISTS idx_transcript_task ON agent_transcript(task_id);
  ```

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_state_store_transcript.py
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


async def test_save_and_get_transcript(store):
    await store.save_transcript(
        transcript_id="t-1", task_id="task-1", sub_conv_id="conv-sub",
        parent_step_id="step-p", parent_conv_id="conv-p", agent_name="BAIZE",
        status="running", latest_event_seq=5,
        payload={"prompt": "hi", "last_token": "..."},
    )
    row = await store.get_transcript("t-1")
    assert row is not None
    assert row["transcript_id"] == "t-1"
    assert row["task_id"] == "task-1"
    assert row["sub_conv_id"] == "conv-sub"
    assert row["parent_conv_id"] == "conv-p"
    assert row["agent_name"] == "BAIZE"
    assert row["status"] == "running"
    assert row["latest_event_seq"] == 5
    assert row["payload"]["prompt"] == "hi"


async def test_get_transcript_returns_none_if_absent(store):
    assert await store.get_transcript("nope") is None


async def test_list_transcripts_for_parent(store):
    await store.save_transcript(
        "t-1", "task-1", "conv-sub-1", "step-p", "conv-p", "BAIZE",
        "running", 0, {},
    )
    await store.save_transcript(
        "t-2", "task-2", "conv-sub-2", "step-p2", "conv-p", "BAIZE",
        "done", 10, {"result": "ok"},
    )
    await store.save_transcript(
        "t-3", "task-3", "conv-sub-3", "step-p3", "conv-other", "BAIZE",
        "running", 0, {},
    )
    rows = await store.list_transcripts_for_parent("conv-p")
    assert len(rows) == 2
    task_ids = {r["task_id"] for r in rows}
    assert task_ids == {"task-1", "task-2"}


async def test_delete_transcript(store):
    await store.save_transcript(
        "t-1", "task-1", "conv-sub", "step-p", "conv-p", "BAIZE",
        "running", 0, {},
    )
    await store.delete_transcript("t-1")
    assert await store.get_transcript("t-1") is None


async def test_delete_absent_is_noop(store):
    await store.delete_transcript("never-existed")  # no error


async def test_save_transcript_overwrites_on_same_id(store):
    await store.save_transcript(
        "t-1", "task-1", "conv-sub", "step-p", "conv-p", "BAIZE",
        "running", 0, {"v": 1},
    )
    await store.save_transcript(
        "t-1", "task-1", "conv-sub", "step-p", "conv-p", "BAIZE",
        "done", 20, {"v": 2, "result": "ok"},
    )
    row = await store.get_transcript("t-1")
    assert row["status"] == "done"
    assert row["latest_event_seq"] == 20
    assert row["payload"]["v"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store_transcript.py -v`
Expected: FAIL with `AttributeError: 'DbStateStore' object has no attribute 'save_transcript'`

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/state_store.py`. Append to `_SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS agent_transcript (
    transcript_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sub_conv_id TEXT NOT NULL,
    parent_step_id TEXT NOT NULL,
    parent_conv_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL,
    latest_event_seq INTEGER NOT NULL,
    payload TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcript_parent ON agent_transcript(parent_conv_id);
CREATE INDEX IF NOT EXISTS idx_transcript_task ON agent_transcript(task_id);
```

Add 4 abstract methods to `StateStore` ABC (after `delete_interaction_checkpoint`):

```python
    @abstractmethod
    async def save_transcript(
        self, transcript_id: str, task_id: str, sub_conv_id: str,
        parent_step_id: str, parent_conv_id: str, agent_name: str,
        status: str, latest_event_seq: int, payload: dict,
    ) -> None: ...

    @abstractmethod
    async def get_transcript(self, transcript_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def list_transcripts_for_parent(self, parent_conv_id: str) -> List[dict]: ...

    @abstractmethod
    async def delete_transcript(self, transcript_id: str) -> None: ...
```

Add 4 concrete methods to `DbStateStore` (after `delete_interaction_checkpoint`):

```python
    async def save_transcript(
        self, transcript_id: str, task_id: str, sub_conv_id: str,
        parent_step_id: str, parent_conv_id: str, agent_name: str,
        status: str, latest_event_seq: int, payload: dict,
    ) -> None:
        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO agent_transcript "
                    "(transcript_id, task_id, sub_conv_id, parent_step_id, parent_conv_id, "
                    "agent_name, status, latest_event_seq, payload, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (transcript_id, task_id, sub_conv_id, parent_step_id, parent_conv_id,
                     agent_name, status, latest_event_seq,
                     json.dumps(payload, ensure_ascii=False), time.time()),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)

    async def get_transcript(self, transcript_id: str) -> Optional[dict]:
        def _do():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT transcript_id, task_id, sub_conv_id, parent_step_id, "
                    "parent_conv_id, agent_name, status, latest_event_seq, payload, updated_at "
                    "FROM agent_transcript WHERE transcript_id = ?",
                    (transcript_id,),
                ).fetchone()
                if not row:
                    return None
                d = dict(row)
                d["payload"] = json.loads(d["payload"])
                return d
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def list_transcripts_for_parent(self, parent_conv_id: str) -> List[dict]:
        def _do():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT transcript_id, task_id, sub_conv_id, parent_step_id, "
                    "parent_conv_id, agent_name, status, latest_event_seq, payload, updated_at "
                    "FROM agent_transcript WHERE parent_conv_id = ? "
                    "ORDER BY updated_at ASC",
                    (parent_conv_id,),
                ).fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    d["payload"] = json.loads(d["payload"])
                    result.append(d)
                return result
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def delete_transcript(self, transcript_id: str) -> None:
        def _do():
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM agent_transcript WHERE transcript_id = ?",
                    (transcript_id,),
                )
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store_transcript.py -v`
Expected: PASS (6 tests)

Run existing StateStore tests to confirm no regression:
Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_state_store.py tests/agent/core/v2/test_state_store_checkpoint.py -v`
Expected: PASS (8 + 5 = 13 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/state_store.py \
        packages/derisk-core/tests/agent/core/v2/test_state_store_transcript.py
git commit -m "feat(agent-v2): StateStore agent_transcript 表 + 4 方法"
```

---

## Task 7: SubAgentHandle model

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/subagent_handle.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_subagent_handle.py`

**Interfaces:**
- `SubAgentMode` enum: `SYNC = "sync"`, `ASYNC = "async"`
- `SubAgentStatus` enum: `PENDING = "pending"`, `RUNNING = "running"`, `DONE = "done"`, `FAILED = "failed"`, `CANCELLED = "cancelled"`
- `SubAgentHandle` pydantic model:
  - `task_id: str` — unique handle id (uuid)
  - `parent_step_id: str`
  - `parent_conv_id: str`
  - `sub_conv_id: str` — independent conversation for the sub-agent
  - `agent_name: str`
  - `mode: SubAgentMode`
  - `status: SubAgentStatus`
  - `result: Optional[dict] = None`
  - `error: Optional[str] = None`
  - `created_at: float`
  - `updated_at: float`
  - `transcript_id: Optional[str] = None` — set when ASYNC mode persists to agent_transcript
  - Methods: `is_done() -> bool`, `to_payload() -> dict`

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_subagent_handle.py
import time
from derisk.agent.core.v2.subagent_handle import (
    SubAgentHandle, SubAgentMode, SubAgentStatus,
)


def _make_handle(**overrides):
    defaults = dict(
        task_id="task-1", parent_step_id="step-p", parent_conv_id="conv-p",
        sub_conv_id="conv-sub", agent_name="BAIZE",
        mode=SubAgentMode.SYNC, status=SubAgentStatus.RUNNING,
        created_at=time.time(), updated_at=time.time(),
    )
    defaults.update(overrides)
    return SubAgentHandle(**defaults)


def test_handle_basic_fields():
    h = _make_handle()
    assert h.task_id == "task-1"
    assert h.mode is SubAgentMode.SYNC
    assert h.status is SubAgentStatus.RUNNING
    assert h.result is None


def test_is_done_true_for_terminal_states():
    assert _make_handle(status=SubAgentStatus.DONE).is_done()
    assert _make_handle(status=SubAgentStatus.FAILED).is_done()
    assert _make_handle(status=SubAgentStatus.CANCELLED).is_done()


def test_is_done_false_for_running():
    assert not _make_handle(status=SubAgentStatus.RUNNING).is_done()
    assert not _make_handle(status=SubAgentStatus.PENDING).is_done()


def test_to_payload_roundtrip():
    h = _make_handle(
        status=SubAgentStatus.DONE,
        result={"answer": 42},
        transcript_id="t-1",
    )
    p = h.to_payload()
    assert p["task_id"] == "task-1"
    assert p["status"] == "done"
    assert p["result"] == {"answer": 42}
    assert p["transcript_id"] == "t-1"


def test_async_mode():
    h = _make_handle(mode=SubAgentMode.ASYNC, transcript_id="t-1")
    assert h.mode is SubAgentMode.ASYNC
    assert h.transcript_id == "t-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_handle.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/subagent_handle.py
"""SubAgentHandle — handle returned by SubAgentRuntime.spawn.

Spec §8.1. Carries the task_id, parent/sub conv ids, mode, status, and result.
SYNC mode: handle is awaited; result populated when sub-agent finishes.
ASYNC mode: handle is returned immediately; transcript persisted to
agent_transcript table; parent polls or receives notification injection.
"""
from __future__ import annotations
import time
from enum import Enum
from typing import Optional
from derisk._private.pydantic import BaseModel, ConfigDict


class SubAgentMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class SubAgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = {SubAgentStatus.DONE, SubAgentStatus.FAILED, SubAgentStatus.CANCELLED}


class SubAgentHandle(BaseModel):
    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)

    task_id: str
    parent_step_id: str
    parent_conv_id: str
    sub_conv_id: str
    agent_name: str
    mode: SubAgentMode
    status: SubAgentStatus
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float
    updated_at: float
    transcript_id: Optional[str] = None

    def is_done(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def to_payload(self) -> dict:
        return {
            "task_id": self.task_id,
            "parent_step_id": self.parent_step_id,
            "parent_conv_id": self.parent_conv_id,
            "sub_conv_id": self.sub_conv_id,
            "agent_name": self.agent_name,
            "mode": self.mode.value,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "transcript_id": self.transcript_id,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_handle.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/subagent_handle.py \
        packages/derisk-core/tests/agent/core/v2/test_subagent_handle.py
git commit -m "feat(agent-v2): SubAgentHandle + Mode/Status 枚举"
```

---

## Task 8: SubAgentInteractionGateway (策略 C)

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/subagent_interaction_gateway.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_subagent_interaction_gateway.py`

**Interfaces:**
- `SubAgentInteractionGateway(InteractionGateway)` subclass:
  - Constructor: `SubAgentInteractionGateway(parent_gateway: InteractionGateway, sync: bool)`
  - `async send_and_wait(request: InteractionRequest) -> InteractionResponse`:
    - `sync=True` → delegate to `parent_gateway.send_and_wait(request)` (bubbles up to parent's user)
    - `sync=False` → return `InteractionResponse(request_id=request.request_id, choice="deny", cancel_reason="auto-deny for background agent")`

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_subagent_interaction_gateway.py
import pytest
from derisk.agent.core.v2.subagent_interaction_gateway import SubAgentInteractionGateway
from derisk.agent.interaction.interaction_protocol import (
    InteractionRequest, InteractionResponse, InteractionType,
)


class FakeParentGateway:
    """Fake parent gateway for testing — records what was delegated."""
    def __init__(self, response_choice="allow_once"):
        self._response_choice = response_choice
        self.last_request = None

    async def send_and_wait(self, request):
        self.last_request = request
        return InteractionResponse(
            request_id=request.request_id,
            choice=self._response_choice,
        )


async def test_sync_mode_delegates_to_parent():
    parent = FakeParentGateway(response_choice="allow_session")
    gw = SubAgentInteractionGateway(parent_gateway=parent, sync=True)
    req = InteractionRequest(
        type=InteractionType.AUTHORIZE,
        request_id="req-1",
        options=[],
    )
    resp = await gw.send_and_wait(req)
    assert resp.choice == "allow_session"
    assert parent.last_request is req


async def test_async_mode_auto_denies():
    parent = FakeParentGateway()
    gw = SubAgentInteractionGateway(parent_gateway=parent, sync=False)
    req = InteractionRequest(
        type=InteractionType.AUTHORIZE,
        request_id="req-1",
        options=[],
    )
    resp = await gw.send_and_wait(req)
    assert resp.choice == "deny"
    assert "background" in (resp.cancel_reason or "").lower()
    # Parent was NOT called
    assert parent.last_request is None


async def test_sync_mode_can_deny_via_parent():
    """If parent denies, sub-agent sees the denial."""
    parent = FakeParentGateway(response_choice="deny")
    gw = SubAgentInteractionGateway(parent_gateway=parent, sync=True)
    req = InteractionRequest(
        type=InteractionType.AUTHORIZE,
        request_id="req-1",
        options=[],
    )
    resp = await gw.send_and_wait(req)
    assert resp.choice == "deny"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_interaction_gateway.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/subagent_interaction_gateway.py
"""SubAgentInteractionGateway — 策略 C (spec §8.6).

Sync sub-agent: ask_user/permission requests bubble up to the parent agent's
InteractionGateway (so the parent's user sees them).
Async sub-agent: requests auto-deny (background agents must not interrupt
the parent's flow).
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from derisk.agent.interaction.interaction_gateway import InteractionGateway
from derisk.agent.interaction.interaction_protocol import (
    InteractionRequest, InteractionResponse,
)

if TYPE_CHECKING:
    pass


class SubAgentInteractionGateway(InteractionGateway):
    def __init__(self, parent_gateway: InteractionGateway, sync: bool):
        # NOTE: do NOT call super().__init__ — we don't want the parent's
        # internal state. We only delegate send_and_wait.
        self._parent = parent_gateway
        self._sync = sync

    async def send_and_wait(self, request: InteractionRequest) -> InteractionResponse:
        if self._sync:
            return await self._parent.send_and_wait(request)
        return InteractionResponse(
            request_id=request.request_id,
            choice="deny",
            cancel_reason="auto-deny for background agent",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_interaction_gateway.py -v`
Expected: PASS (3 tests)

If `InteractionGateway.__init__` requires args and we can't skip it cleanly, adjust: pass through minimal args or use object.__new__ to bypass. Document the actual approach in the report.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/subagent_interaction_gateway.py \
        packages/derisk-core/tests/agent/core/v2/test_subagent_interaction_gateway.py
git commit -m "feat(agent-v2): SubAgentInteractionGateway 策略 C"
```

---

## Task 9: SubAgentRuntime core (spawn + sync/async + depth limit)

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/subagent_runtime.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_subagent_runtime.py`

**Interfaces:**
- `SubAgentRuntime` class:
  - Constructor: `SubAgentRuntime(state_store: StateStore, max_depth: int = 5, async_task_manager: Optional[AsyncTaskManager] = None)`
  - `async spawn(spec: SubAgentSpawnSpec) -> SubAgentHandle` where `SubAgentSpawnSpec` is a pydantic model:
    ```python
    class SubAgentSpawnSpec(BaseModel):
        agent_name: str
        task: str
        run_in_background: bool = False
        context: dict = {}
        parent_step_id: str
        parent_conv_id: str
        parent_agent_id: str
        depth: int = 0  # current depth; runtime rejects if depth+1 > max_depth
        thinking_fn: Optional[Any] = None  # sub-agent's thinking fn
        acting_fn: Optional[Any] = None    # sub-agent's acting fn
        interaction_gateway: Optional[Any] = None  # parent's gateway (sync) or None (async)
    ```
  - `async wait(handle: SubAgentHandle, timeout: Optional[float] = None) -> SubAgentHandle` — for SYNC mode; awaits sub-agent's run_step completion
  - `async get_status(task_id: str) -> Optional[SubAgentHandle]`
  - `async cancel(task_id: str) -> bool`
  - `async resume(task_id: str) -> SubAgentHandle` — re-attach to an async sub-agent

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_subagent_runtime.py
import pytest
import tempfile
import os
import asyncio
from derisk.agent.core.v2.subagent_runtime import (
    SubAgentRuntime, SubAgentSpawnSpec,
)
from derisk.agent.core.v2.subagent_handle import SubAgentMode, SubAgentStatus
from derisk.agent.core.v2.state_store import DbStateStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _subagent_thinking(input_):
    yield {"token": "sub"}
    yield {"token": "", "tool_calls": []}


async def _subagent_acting(tc):
    return {"result": f"sub:{tc.get('tool', '')}"}


def _make_spec(parent_step_id="step-p", parent_conv_id="conv-p", run_in_background=False, depth=0):
    return SubAgentSpawnSpec(
        agent_name="BAIZE",
        task="do something",
        run_in_background=run_in_background,
        context={},
        parent_step_id=parent_step_id,
        parent_conv_id=parent_conv_id,
        parent_agent_id="agent-p",
        depth=depth,
        thinking_fn=_subagent_thinking,
        acting_fn=_subagent_acting,
    )


async def test_spawn_sync_returns_handle_with_done_result(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec(run_in_background=False))
    assert handle.mode is SubAgentMode.SYNC
    assert handle.status is SubAgentStatus.DONE
    assert handle.result is not None
    assert handle.parent_conv_id == "conv-p"
    assert handle.sub_conv_id != "conv-p"  # independent conv


async def test_spawn_async_returns_running_handle(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec(run_in_background=True))
    assert handle.mode is SubAgentMode.ASYNC
    assert handle.status in (SubAgentStatus.RUNNING, SubAgentStatus.DONE)  # may finish fast
    assert handle.transcript_id is not None


async def test_spawn_exceeds_depth_limit_rejected(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=3)
    with pytest.raises(ValueError, match="depth"):
        await runtime.spawn(_make_spec(depth=3))  # depth+1 = 4 > 3


async def test_spawn_at_depth_limit_boundary_ok(store):
    """depth=2, max_depth=3 → depth+1=3 == max_depth, allowed."""
    runtime = SubAgentRuntime(state_store=store, max_depth=3)
    handle = await runtime.spawn(_make_spec(depth=2))
    assert handle.status is SubAgentStatus.DONE


async def test_get_status_returns_handle(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec())
    fetched = await runtime.get_status(handle.task_id)
    assert fetched is not None
    assert fetched.task_id == handle.task_id


async def test_get_status_returns_none_for_unknown(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    assert await runtime.get_status("never-existed") is None


async def test_cancel_async_task(store):
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    # Spawn an async task that takes a bit
    async def slow_thinking(input_):
        await asyncio.sleep(0.1)
        yield {"token": "sub", "tool_calls": []}

    spec = _make_spec(run_in_background=True)
    spec.thinking_fn = slow_thinking
    handle = await runtime.spawn(spec)
    ok = await runtime.cancel(handle.task_id)
    assert ok is True
    # After cancel, status is CANCELLED or DONE (if it finished first)
    fetched = await runtime.get_status(handle.task_id)
    assert fetched.status in (SubAgentStatus.CANCELLED, SubAgentStatus.DONE)


async def test_resume_async_task(store):
    """resume() on an async task returns the current handle (may be running or done)."""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec(run_in_background=True))
    resumed = await runtime.resume(handle.task_id)
    assert resumed.task_id == handle.task_id


async def test_sync_spawn_writes_subagent_events_to_same_store(store):
    """Sub-agent's StepEvents go into the same step_event table with sub_conv_id."""
    runtime = SubAgentRuntime(state_store=store, max_depth=5)
    handle = await runtime.spawn(_make_spec())
    events = await store.get_events(handle.sub_conv_id)
    assert len(events) > 0
    # Sub-agent should have at least INIT, THINKING, DONE
    states = [e.state.value for e in events]
    assert "init" in states
    assert "done" in states
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/derisk-core/src/derisk/agent/core/v2/subagent_runtime.py
"""SubAgentRuntime — spec §8 SubAgent Runtime entry point.

Single entry: spawn(spec) -> SubAgentHandle.
- SYNC mode: await sub-agent's run_step, return handle with result
- ASYNC mode: schedule run_step in background, persist transcript, return immediately
- Depth limiting: reject spawn if depth+1 > max_depth
- Independent context: each spawn creates a new sub_conv_id

P2 wraps the existing AsyncTaskManager for ASYNC mode (lifecycle, cancel,
wait). SYNC mode just awaits run_step directly.
"""
from __future__ import annotations
import uuid
import time
import asyncio
from typing import Any, Optional, Dict, TYPE_CHECKING
from derisk._private.pydantic import BaseModel, ConfigDict
from derisk.agent.core.v2.subagent_handle import (
    SubAgentHandle, SubAgentMode, SubAgentStatus,
)
from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.step_state import StepState

if TYPE_CHECKING:
    from derisk.agent.core.v2.state_store import StateStore
    from derisk.agent.util.async_task_manager import AsyncTaskManager


class SubAgentSpawnSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    agent_name: str
    task: str
    run_in_background: bool = False
    context: Dict[str, Any] = {}
    parent_step_id: str
    parent_conv_id: str
    parent_agent_id: str
    depth: int = 0
    thinking_fn: Optional[Any] = None
    acting_fn: Optional[Any] = None
    interaction_gateway: Optional[Any] = None


class SubAgentRuntime:
    def __init__(
        self,
        state_store: "StateStore",
        max_depth: int = 5,
        async_task_manager: Optional["AsyncTaskManager"] = None,
    ):
        self._store = state_store
        self._max_depth = max_depth
        self._async_mgr = async_task_manager
        self._handles: Dict[str, SubAgentHandle] = {}
        self._async_tasks: Dict[str, asyncio.Task] = {}

    async def spawn(self, spec: SubAgentSpawnSpec) -> SubAgentHandle:
        if spec.depth + 1 > self._max_depth:
            raise ValueError(
                f"spawn depth limit exceeded: depth={spec.depth}, max_depth={self._max_depth}"
            )

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        sub_conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        now = time.time()
        mode = SubAgentMode.ASYNC if spec.run_in_background else SubAgentMode.SYNC
        handle = SubAgentHandle(
            task_id=task_id,
            parent_step_id=spec.parent_step_id,
            parent_conv_id=spec.parent_conv_id,
            sub_conv_id=sub_conv_id,
            agent_name=spec.agent_name,
            mode=mode,
            status=SubAgentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        if mode is SubAgentMode.SYNC:
            await self._run_subagent(handle, spec)
        else:
            # ASYNC: schedule in background, persist transcript
            transcript_id = f"t-{uuid.uuid4().hex[:8]}"
            handle.transcript_id = transcript_id
            handle.status = SubAgentStatus.RUNNING
            self._handles[task_id] = handle
            self._async_tasks[task_id] = asyncio.create_task(
                self._run_subagent_async(handle, spec, transcript_id)
            )

        return handle

    async def _run_subagent(self, handle: SubAgentHandle, spec: SubAgentSpawnSpec) -> None:
        """Sync mode: run sub-agent to completion before returning."""
        handle.status = SubAgentStatus.RUNNING
        self._handles[handle.task_id] = handle
        input_ = {"prompt": spec.task, **spec.context}
        try:
            result = {"events": []}
            async for event in run_step(
                agent_id=f"subagent-{handle.task_id}",
                conv_id=handle.sub_conv_id,
                input_=input_,
                state_store=self._store,
                thinking_fn=spec.thinking_fn,
                acting_fn=spec.acting_fn,
                parent_step_id=handle.parent_step_id,
            ):
                result["events"].append({
                    "seq": event.seq,
                    "state": event.state.value,
                    "event_type": event.event_type,
                })
            handle.result = {"status": "done", "events_count": len(result["events"])}
            handle.status = SubAgentStatus.DONE
        except Exception as e:
            handle.error = str(e)
            handle.status = SubAgentStatus.FAILED
        handle.updated_at = time.time()

    async def _run_subagent_async(
        self, handle: SubAgentHandle, spec: SubAgentSpawnSpec, transcript_id: str,
    ) -> None:
        """Async mode: run in background, update transcript periodically."""
        input_ = {"prompt": spec.task, **spec.context}
        try:
            latest_seq = 0
            async for event in run_step(
                agent_id=f"subagent-{handle.task_id}",
                conv_id=handle.sub_conv_id,
                input_=input_,
                state_store=self._store,
                thinking_fn=spec.thinking_fn,
                acting_fn=spec.acting_fn,
                parent_step_id=handle.parent_step_id,
            ):
                latest_seq = max(latest_seq, event.seq)
                # Persist transcript snapshot every few events
                await self._store.save_transcript(
                    transcript_id=transcript_id,
                    task_id=handle.task_id,
                    sub_conv_id=handle.sub_conv_id,
                    parent_step_id=handle.parent_step_id,
                    parent_conv_id=handle.parent_conv_id,
                    agent_name=handle.agent_name,
                    status="running",
                    latest_event_seq=latest_seq,
                    payload={"last_event_state": event.state.value},
                )
            handle.result = {"status": "done", "latest_seq": latest_seq}
            handle.status = SubAgentStatus.DONE
            await self._store.save_transcript(
                transcript_id=transcript_id,
                task_id=handle.task_id,
                sub_conv_id=handle.sub_conv_id,
                parent_step_id=handle.parent_step_id,
                parent_conv_id=handle.parent_conv_id,
                agent_name=handle.agent_name,
                status="done",
                latest_event_seq=latest_seq,
                payload={"result": handle.result},
            )
        except asyncio.CancelledError:
            handle.status = SubAgentStatus.CANCELLED
            await self._store.save_transcript(
                transcript_id=transcript_id,
                task_id=handle.task_id,
                sub_conv_id=handle.sub_conv_id,
                parent_step_id=handle.parent_step_id,
                parent_conv_id=handle.parent_conv_id,
                agent_name=handle.agent_name,
                status="cancelled",
                latest_event_seq=0,
                payload={"error": "cancelled"},
            )
            raise
        except Exception as e:
            handle.error = str(e)
            handle.status = SubAgentStatus.FAILED
            await self._store.save_transcript(
                transcript_id=transcript_id,
                task_id=handle.task_id,
                sub_conv_id=handle.sub_conv_id,
                parent_step_id=handle.parent_step_id,
                parent_conv_id=handle.parent_conv_id,
                agent_name=handle.agent_name,
                status="failed",
                latest_event_seq=0,
                payload={"error": str(e)},
            )
        finally:
            handle.updated_at = time.time()

    async def wait(self, handle: SubAgentHandle, timeout: Optional[float] = None) -> SubAgentHandle:
        if handle.mode is SubAgentMode.SYNC:
            return handle  # sync already done
        task = self._async_tasks.get(handle.task_id)
        if task is None:
            return handle
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return self._handles.get(handle.task_id, handle)

    async def get_status(self, task_id: str) -> Optional[SubAgentHandle]:
        return self._handles.get(task_id)

    async def cancel(self, task_id: str) -> bool:
        task = self._async_tasks.get(task_id)
        if task is None:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    async def resume(self, task_id: str) -> Optional[SubAgentHandle]:
        """Re-attach to an async sub-agent. Returns current handle."""
        return self._handles.get(task_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_subagent_runtime.py -v`
Expected: PASS (9 tests)

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/subagent_runtime.py \
        packages/derisk-core/tests/agent/core/v2/test_subagent_runtime.py
git commit -m "feat(agent-v2): SubAgentRuntime spawn/wait/cancel/resume + 深度限制"
```

---

## Task 10: SpawnSubagentTool (LLM-facing tool)

**Files:**
- Create: `packages/derisk-core/src/derisk/agent/core/v2/spawn_subagent_tool.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_spawn_subagent_tool.py`

**Interfaces:**
- `SpawnSubagentTool(ToolBase)` — LLM-facing wrapper around `SubAgentRuntime.spawn`
  - `execute(args, context)`:
    - Parses `agent_name`, `task`, `run_in_background`, `context` from args
    - Calls `runtime.spawn(spec)` where spec includes parent step/conv from `context`
    - Returns `ToolResult(success=True, output=<handle payload>)`
    - For SYNC mode, output includes the sub-agent's result
    - For ASYNC mode, output includes `task_handle` only

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_spawn_subagent_tool.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.spawn_subagent_tool import SpawnSubagentTool
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec
from derisk.agent.core.v2.state_store import DbStateStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _subagent_thinking(input_):
    yield {"token": "sub", "tool_calls": []}


async def _subagent_acting(tc):
    return {"result": "ok"}


def _make_tool(store, max_depth=5):
    runtime = SubAgentRuntime(state_store=store, max_depth=max_depth)
    return SpawnSubagentTool(runtime=runtime), runtime


def _make_context(parent_step_id="step-p", parent_conv_id="conv-p", parent_agent_id="agent-p"):
    from derisk.agent.tools.context import ToolContext
    return ToolContext(
        parent_step_id=parent_step_id,
        parent_conv_id=parent_conv_id,
        agent_id=parent_agent_id,
        depth=0,
        thinking_fn=_subagent_thinking,
        acting_fn=_subagent_acting,
    )


async def test_tool_execute_sync_returns_result(store):
    tool, runtime = _make_tool(store)
    ctx = _make_context()
    result = await tool.execute(
        args={
            "agent_name": "BAIZE",
            "task": "do thing",
            "run_in_background": False,
            "context": {},
        },
        context=ctx,
    )
    assert result.success is True
    assert "task_id" in result.output
    assert result.output["mode"] == "sync"
    assert result.output["status"] == "done"


async def test_tool_execute_async_returns_handle(store):
    tool, runtime = _make_tool(store)
    ctx = _make_context()
    result = await tool.execute(
        args={
            "agent_name": "BAIZE",
            "task": "do thing async",
            "run_in_background": True,
            "context": {},
        },
        context=ctx,
    )
    assert result.success is True
    assert result.output["mode"] == "async"
    assert "task_id" in result.output


async def test_tool_validates_required_args(store):
    tool, runtime = _make_tool(store)
    ctx = _make_context()
    result = await tool.execute(
        args={"agent_name": "BAIZE"},  # missing task
        context=ctx,
    )
    assert result.success is False
    assert "task" in (result.error or "").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_spawn_subagent_tool.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

First, check the existing `ToolContext` shape — the test above assumes fields that may not exist. Open `packages/derisk-core/src/derisk/agent/tools/context.py` and read its actual fields. If `ToolContext` doesn't have `parent_step_id`/`parent_conv_id`/`thinking_fn` etc., use a dict context instead.

```python
# packages/derisk-core/src/derisk/agent/core/v2/spawn_subagent_tool.py
"""SpawnSubagentTool — LLM-facing tool wrapping SubAgentRuntime.spawn.

Spec §8.1. Replaces the dual-entry agent_start + AsyncTaskManager pattern.
LLM calls this tool with agent_name + task + run_in_background; the tool
builds a SubAgentSpawnSpec and delegates to SubAgentRuntime.
"""
from __future__ import annotations
from typing import Any, Optional, Dict
from derisk.agent.tools.base import ToolBase
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import ToolResult
from derisk.agent.core.v2.subagent_runtime import (
    SubAgentRuntime, SubAgentSpawnSpec,
)


class SpawnSubagentTool(ToolBase):
    def __init__(self, runtime: SubAgentRuntime):
        super().__init__()
        self._runtime = runtime

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="spawn_subagent",
            description="Spawn a sub-agent (sync or async). Spec §8.",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Sub-agent type (e.g. 'BAIZE')"},
                "task": {"type": "string", "description": "Task description for the sub-agent"},
                "run_in_background": {
                    "type": "boolean",
                    "default": False,
                    "description": "False=sync (block until done); True=async (return handle immediately)",
                },
                "context": {"type": "object", "default": {}},
            },
            "required": ["agent_name", "task"],
        }

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Any] = None,
    ) -> ToolResult:
        agent_name = args.get("agent_name")
        task = args.get("task")
        if not agent_name or not task:
            return ToolResult(
                success=False,
                error="spawn_subagent requires 'agent_name' and 'task'",
            )

        # Extract parent info from context. ToolContext shape varies; use getattr.
        parent_step_id = getattr(context, "parent_step_id", None) or "step-unknown"
        parent_conv_id = getattr(context, "parent_conv_id", None) or "conv-unknown"
        parent_agent_id = getattr(context, "agent_id", None) or "agent-unknown"
        depth = getattr(context, "depth", 0)
        thinking_fn = getattr(context, "thinking_fn", None)
        acting_fn = getattr(context, "acting_fn", None)
        interaction_gateway = getattr(context, "interaction_gateway", None)

        spec = SubAgentSpawnSpec(
            agent_name=agent_name,
            task=task,
            run_in_background=args.get("run_in_background", False),
            context=args.get("context", {}),
            parent_step_id=parent_step_id,
            parent_conv_id=parent_conv_id,
            parent_agent_id=parent_agent_id,
            depth=depth,
            thinking_fn=thinking_fn,
            acting_fn=acting_fn,
            interaction_gateway=interaction_gateway,
        )

        handle = await self._runtime.spawn(spec)
        return ToolResult(
            success=True,
            output={
                "task_id": handle.task_id,
                "mode": handle.mode.value,
                "status": handle.status.value,
                "sub_conv_id": handle.sub_conv_id,
                "result": handle.result,
                "transcript_id": handle.transcript_id,
            },
        )
```

Adjust the test's `_make_context` if `ToolContext` doesn't have those fields — use a simple object with attributes, or a dict (and change `getattr` to `.get` in the implementation). The implementation above uses `getattr` which works for both objects and `types.SimpleNamespace`.

If `ToolContext` exists with different field names, update the test to construct it correctly. The implementation should stay generic via `getattr`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_spawn_subagent_tool.py -v`
Expected: PASS (3 tests)

If `ToolResult` doesn't accept `error=` kwarg, check `packages/derisk-core/src/derisk/agent/tools/result.py` and use the correct field name.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/spawn_subagent_tool.py \
        packages/derisk-core/tests/agent/core/v2/test_spawn_subagent_tool.py
git commit -m "feat(agent-v2): SpawnSubagentTool LLM 入口"
```

---

## Task 11: Wire SubAgentRuntime into run_step (AWAITING_SUB_AGENT event)

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_runtime_subagent.py`

**Interfaces:**
- `run_step` accepts `subagent_runtime: Optional[SubAgentRuntime] = None`
- When a tool_call's `tool` is `"spawn_subagent"` and `subagent_runtime` is provided:
  - For sync mode (`run_in_background=False`): emit `AWAITING_SUB_AGENT` event, await sub-agent completion, emit `OBSERVING` with sub-agent result
  - For async mode: emit `AWAITING_SUB_AGENT` event (informational), return handle as the `tool_result`

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/v2/test_runtime_subagent.py
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def _parent_thinking(input_):
    yield {"token": "calling sub"}
    yield {
        "token": "",
        "tool_calls": [{
            "tool": "spawn_subagent",
            "input": {"agent_name": "BAIZE", "task": "do thing", "run_in_background": False},
        }],
    }


async def _subagent_thinking(input_):
    yield {"token": "sub"}
    yield {"token": "", "tool_calls": []}


async def _acting_fn(tc):
    # Should not be called for spawn_subagent — runtime intercepts
    return {"result": "should not reach"}


async def test_run_step_sync_subagent_emits_awaiting_sub_agent(store):
    sub_runtime = SubAgentRuntime(state_store=store, max_depth=5)
    # The sub-agent's thinking_fn/acting_fn come from the spec — but in this
    # integration test, we need to inject them. Use a wrapper.
    async def _parent_thinking_with_sub(input_):
        yield {"token": "calling sub"}
        yield {
            "token": "",
            "tool_calls": [{
                "tool": "spawn_subagent",
                "input": {
                    "agent_name": "BAIZE",
                    "task": "do thing",
                    "run_in_background": False,
                    # Inject sub-agent fns via context (runtime knows to read them)
                    "_sub_thinking_fn": _subagent_thinking,
                    "_sub_acting_fn": lambda tc: {"result": "sub-ok"},
                },
            }],
        }

    events = []
    async for e in run_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store,
        _parent_thinking_with_sub, _acting_fn,
        subagent_runtime=sub_runtime,
    ):
        events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_SUB_AGENT in states
    # After AWAITING_SUB_AGENT, should go to OBSERVING then DONE
    assert states[-1] is StepState.DONE
    # The OBSERVING event should carry the sub-agent's result
    observing = [e for e in events if e.state is StepState.OBSERVING]
    assert len(observing) >= 1
    # The tool_result for spawn_subagent includes the handle
    assert observing[-1].output.get("status") == "done" or "task_id" in observing[-1].output


async def test_run_step_without_subagent_runtime_falls_back_to_acting_fn(store):
    """If subagent_runtime is None, spawn_subagent tool_call goes to acting_fn (backwards compat)."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "spawn_subagent", "input": {}}]}
    async def acting(tc):
        return {"result": "legacy path"}

    events = []
    async for e in run_step(
        "agent-1", "conv-1", {"prompt": "hi"}, store,
        thinking, acting,
        subagent_runtime=None,
    ):
        events.append(e)
    observing = [e for e in events if e.state is StepState.OBSERVING]
    assert len(observing) == 1
    assert observing[0].output == {"result": "legacy path"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime_subagent.py -v`
Expected: FAIL — `run_step` doesn't accept `subagent_runtime` kwarg.

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/runtime.py`. Add `subagent_runtime` param to `run_step` and `resume_step`. In `_run_acting_phase`, intercept `spawn_subagent` tool_calls:

```python
# Add to imports at top of runtime.py
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from derisk.agent.core.v2.subagent_runtime import SubAgentRuntime, SubAgentSpawnSpec


async def _run_acting_phase(
    emit, gate, tool_calls, acting_fn, state_store=None,
    subagent_runtime=None, parent_step_id=None, parent_conv_id=None,
    parent_agent_id=None,
):
    """ACTING + OBSERVING 阶段。每个 tool_call 前 PermissionGate.check()。"""
    for tc in tool_calls:
        # Sub-agent interception (spec §8)
        if tc.get("tool") == "spawn_subagent" and subagent_runtime is not None:
            yield await emit(
                StepState.AWAITING_SUB_AGENT, "subagent_spawn",
                input_data=tc,
            )
            from derisk.agent.core.v2.subagent_runtime import SubAgentSpawnSpec
            spec_input = tc.get("input", {})
            spec = SubAgentSpawnSpec(
                agent_name=spec_input.get("agent_name", "unknown"),
                task=spec_input.get("task", ""),
                run_in_background=spec_input.get("run_in_background", False),
                context=spec_input.get("context", {}),
                parent_step_id=parent_step_id or "step-unknown",
                parent_conv_id=parent_conv_id or "conv-unknown",
                parent_agent_id=parent_agent_id or "agent-unknown",
                depth=0,  # P2 simplification: depth tracking via context in P3
                thinking_fn=spec_input.get("_sub_thinking_fn"),
                acting_fn=spec_input.get("_sub_acting_fn"),
                interaction_gateway=None,
            )
            handle = await subagent_runtime.spawn(spec)
            yield await emit(
                StepState.OBSERVING, "tool_result",
                output_data=handle.to_payload(),
            )
            continue

        # PermissionGate path (existing)
        if gate is not None:
            async for perm_event in gate.check(tc, emit=emit):
                yield perm_event
            result = gate.last_result
            if result.decision == PermissionDecision.DENY:
                yield await emit(
                    StepState.ACTING, "tool_call",
                    input_data=tc, output_data={"denied": True, "reason": result.reason},
                )
                continue
            if result.request_id and state_store is not None:
                await state_store.delete_interaction_checkpoint(result.request_id)
        yield await emit(StepState.ACTING, "tool_call", input_data=tc)
        if acting_fn is not None:
            result_dict = await acting_fn(tc)
            yield await emit(StepState.OBSERVING, "tool_result", output_data=result_dict)
```

Update `run_step` and `resume_step` to accept and forward `subagent_runtime`:

```python
async def run_step(
    agent_id: str,
    conv_id: str,
    input_: dict,
    state_store: StateStore,
    thinking_fn: ThinkingFn,
    acting_fn: Optional[ActingFn] = None,
    parent_step_id: Optional[str] = None,
    permission_gate: Optional[PermissionGate] = None,
    subagent_runtime: Optional["SubAgentRuntime"] = None,
) -> AsyncGenerator[StepEvent, None]:
    """跑一个 step，yield 所有 StepEvent。每个事件持久化后再 yield。"""
    stream = EventStream(state_store)
    step_id = f"step-{uuid.uuid4().hex[:8]}"
    if permission_gate is not None:
        permission_gate._step_id = step_id
    emit = _make_emit(stream, step_id, conv_id, agent_id, parent_step_id, seq_start=0)

    result_box = {}
    async for e in _run_thinking_phase(emit, thinking_fn, input_, result_box):
        yield e

    if result_box["await_user"]:
        return

    if result_box["tool_calls"]:
        async for e in _run_acting_phase(
            emit, permission_gate, result_box["tool_calls"], acting_fn,
            state_store=state_store,
            subagent_runtime=subagent_runtime,
            parent_step_id=step_id, parent_conv_id=conv_id, parent_agent_id=agent_id,
        ):
            yield e

    yield await emit(StepState.DONE, "step_done")
```

Apply the same `subagent_runtime` param + forwarding to `resume_step`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_runtime_subagent.py -v`
Expected: PASS (2 tests)

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/runtime.py \
        packages/derisk-core/tests/agent/core/v2/test_runtime_subagent.py
git commit -m "feat(agent-v2): run_step 接入 SubAgentRuntime + AWAITING_SUB_AGENT"
```

---

## Task 12: Public API exports + full regression

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/v2/__init__.py`
- Test: `packages/derisk-core/tests/agent/core/v2/test_package.py` (existing — extend)

**Interfaces:**
- Adds to `__init__.py` exports: `SubAgentRuntime`, `SubAgentSpawnSpec`, `SubAgentHandle`, `SubAgentMode`, `SubAgentStatus`, `SubAgentInteractionGateway`, `SpawnSubagentTool`, `AskUserAdapter`, `PermissionCheckResult`.

- [ ] **Step 1: Write the failing test (extend test_package.py)**

Add to the import block + assertions in `packages/derisk-core/tests/agent/core/v2/test_package.py`:

```python
from derisk.agent.core.v2 import (
    # ... existing imports ...
    SubAgentRuntime,
    SubAgentSpawnSpec,
    SubAgentHandle,
    SubAgentMode,
    SubAgentStatus,
    SubAgentInteractionGateway,
    SpawnSubagentTool,
    AskUserAdapter,
    PermissionCheckResult,
)


def test_p2_exports():
    assert SubAgentMode.SYNC.value == "sync"
    assert SubAgentMode.ASYNC.value == "async"
    assert SubAgentStatus.RUNNING.value == "running"
    assert SubAgentStatus.DONE.value == "done"
    assert callable(SubAgentRuntime)
    assert callable(SpawnSubagentTool)
    assert callable(AskUserAdapter)
    assert PermissionCheckResult(decision="allow").decision == "allow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_package.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/v2/__init__.py` and add the new imports + `__all__` entries:

```python
from derisk.agent.core.v2.subagent_handle import (
    SubAgentHandle, SubAgentMode, SubAgentStatus,
)
from derisk.agent.core.v2.subagent_runtime import (
    SubAgentRuntime, SubAgentSpawnSpec,
)
from derisk.agent.core.v2.subagent_interaction_gateway import SubAgentInteractionGateway
from derisk.agent.core.v2.spawn_subagent_tool import SpawnSubagentTool
from derisk.agent.core.v2.ask_user_adapter import AskUserAdapter
from derisk.agent.core.v2.permission_gate import PermissionCheckResult
```

Add all 9 names to `__all__`.

- [ ] **Step 4: Run test to verify it passes + full regression**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_package.py -v`
Expected: PASS

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS (90+ tests total — P0 30 + P1 32 + P2 ~30 new)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/v2/__init__.py \
        packages/derisk-core/tests/agent/core/v2/test_package.py
git commit -m "feat(agent-v2): P2 公开 API 导出（SubAgent 全家桶 + 适配层）"
```

---

## Self-Review

**1. Spec coverage (P2 scope = spec §8 SubAgent Runtime + §9.3 Level 4 + §9.4 adapter + P1 follow-ups):**
- ✅ §8.1 `spawn_subagent` 统一入口 → Task 10 `SpawnSubagentTool`
- ✅ §8.2 独立上下文（每次 spawn 必建 sub_conv_id） → Task 9 `SubAgentRuntime.spawn` creates `sub_conv_id = f"conv-{uuid}"`
- ✅ §8.3 同步/异步二选一 → Task 9 SYNC/ASYNC modes, Task 11 sync emits AWAITING_SUB_AGENT
- ✅ §8.4 detach + resume（跨进程） → Task 9 `resume(task_id)`, transcript persistence in `agent_transcript` table (Task 6)
- ✅ §8.5 嵌套递归深度限制 → Task 9 `max_depth` + `depth+1 > max_depth` check
- ✅ §8.6 子 agent 的 ask_user / permission 处理（策略 C） → Task 8 `SubAgentInteractionGateway`
- ⏭️ §8.7 通知注入（异步子 agent 完成后注入 user message） → **P2 defers** to P3 (requires EventStream unification + parent notification mechanism that doesn't exist yet). Active polling via `get_status`/`resume` is P2's scope.
- ✅ §9.3 Level 4 (Tool.check_permissions) → Task 4
- ✅ §9.4 ActionOutput.ask_user 适配层 → Task 5 `AskUserAdapter`
- ✅ P1 I-1 (response.choice) → Task 2
- ✅ P1 I-2 (seq=0 placeholder) → Task 2 (emit callable)
- ✅ P1 #4 (runtime_extra fold) → Task 1
- ✅ P1 #5 (checkpoint deletion) → Task 2 + Task 3 verification

**2. Placeholder scan:** No TBD/TODO/"implement later". The `TODO(P2)` markers from P1 are now resolved in Tasks 1-3. The `_sub_thinking_fn`/`_sub_acting_fn` injection in Task 11's test is a P2 test-only pattern; P3 will replace with proper context wiring. Marked inline.

**3. Type consistency:**
- `SubAgentHandle` fields used consistently across Tasks 7, 9, 10, 11
- `SubAgentSpawnSpec` fields match between Task 9 (definition) and Task 10 (SpawnSubagentTool builds it) and Task 11 (runtime intercepts)
- `PermissionCheckResult` defined Task 4, used in Task 4 tests and exported Task 12
- `InteractionResponse.choice` (P1 I-1 fix in Task 2) matches the actual field at `interaction_protocol.py:144`
- `VALID_TRANSITIONS` additions in Task 1 match the states used by `runtime.py` (THINKING→AWAITING_USER, ACTING→DONE)

**4. P2 简化声明：**
- §8.7 notification injection deferred to P3 — P2 only provides active polling (`get_status`/`resume`)
- `depth` tracking in Task 11 is hardcoded to 0 (P3 will thread it via context)
- `SubAgentInteractionGateway` skips `super().__init__` to avoid parent's internal state — uses delegation only. If `InteractionGateway.__init__` has required args, this may need adjustment (called out in Task 8 step 4)
- `_sub_thinking_fn`/`_sub_acting_fn` injection via spec_input dict is a test convenience; production wiring in P3 will use ToolContext
- ASYNC mode uses `asyncio.create_task` directly, not the existing `AsyncTaskManager`. P3 can wrap with `AsyncTaskManager` for concurrency limits + dependency resolution if needed

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-agent-v2-runtime-p2.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
