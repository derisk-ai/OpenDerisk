# Agent V2 Runtime P4: Safe Legacy Cleanup + Deprecation Marking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy code paths that P3 made redundant AND are safe to remove (zero production callers). Mark the remaining legacy APIs as deprecated with `DeprecationWarning`. Document the §11.2 migration (BAIZE → V2 runtime) as a separate follow-up plan, since it's blocked by entanglement with `react_master_agent.py` and the legacy build chain.

**Architecture:**
- Tasks 1-2: Remove dead code (orphan `push_context_event` wrapper, unused `needs_tool_approval` method).
- Tasks 3-4: Add `DeprecationWarning` to legacy APIs still in use (`push_context_event` method, `push_message`, `queue_iterator`, `ActionOutput.ask_user`) — non-breaking, signals intent to consumers.
- Task 5: Write a §11.2 follow-up plan stub documenting the BAIZE → V2 migration scope (NOT executed in P4).

**Tech Stack:** Python ≥ 3.10, pydantic v2, existing V2 kernel.

## Global Constraints

- Python ≥ 3.10
- pydantic v2 via `from derisk._private.pydantic import BaseModel, ConfigDict, Field` (never `from pydantic import`)
- V2 kernel code under `packages/derisk-core/src/derisk/agent/core/v2/`
- TDD: RED → GREEN → commit per task
- All V2 methods are `async`
- Do NOT delete `push_context_event` (method on base_agent)/`push_message`/`queue_iterator`/`base_agent.py` — they are still used by the legacy BAIZE path (`react_master_agent.py`). Mark deprecated only.
- Do NOT touch `react_master_agent.py` — that's §11.2, a separate effort.
- Working tree has unrelated uncommitted changes; stage only the files each task names

---

## File Structure

**Modified files:**
- `packages/derisk-core/src/derisk/context/manager.py` — remove orphan `push_context_event` wrapper (Task 1)
- `packages/derisk-core/src/derisk/agent/core/base_agent.py` — remove `needs_tool_approval` method + add `DeprecationWarning` to `push_context_event` (Tasks 2, 3)
- `packages/derisk-core/src/derisk/agent/core/memory/gpts/gpts_memory.py` — add `DeprecationWarning` to `push_message` + `queue_iterator` (Task 3)
- `packages/derisk-core/src/derisk/agent/core/action/base.py` — add `DeprecationWarning` to `ActionOutput.ask_user` (Task 3)
- Tests for each deprecation (verify warning fires)

**New files:**
- `docs/superpowers/plans/2026-07-02-agent-v2-runtime-p3-5-baize-migration.md` — §11.2 follow-up plan stub (Task 5)

---

## Task 1: Remove orphan `push_context_event` standalone wrapper

**Files:**
- Modify: `packages/derisk-core/src/derisk/context/manager.py`
- Test: `packages/derisk-core/tests/context/test_manager_no_orphan_push.py` (new — verifies the function is gone)

**Interfaces:**
- The standalone `push_context_event` function at `context/manager.py:47` has 0 production callers. Remove it.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/context/test_manager_no_orphan_push.py
"""P4 Task 1: verify the orphan push_context_event wrapper is gone."""
import pytest


def test_orphan_push_context_event_removed():
    """The standalone push_context_event in derisk.context.manager should be removed."""
    from derisk.context import manager
    assert not hasattr(manager, "push_context_event"), (
        "derisk.context.manager.push_context_event should be removed in P4 "
        "(orphan wrapper with 0 production callers)"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/context/test_manager_no_orphan_push.py -v`
Expected: FAIL — `hasattr` returns True.

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/context/manager.py`. Find the `push_context_event` function (around line 47). Delete the function and any imports it made unused. Verify with `grep -rn "from derisk.context.manager import push_context_event\|from derisk.context import push_context_event" packages/` — should return 0 results.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/derisk-core && python -m pytest tests/context/test_manager_no_orphan_push.py -v`
Expected: PASS

Run full v2 regression: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS (no regression)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/context/manager.py \
        packages/derisk-core/tests/context/test_manager_no_orphan_push.py
git commit -m "chore(agent-v2): P4 Task 1 移除孤儿 push_context_event wrapper"
```

---

## Task 2: Remove unused `needs_tool_approval` method

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/base_agent.py`
- Test: `packages/derisk-core/tests/agent/core/test_base_agent_no_needs_tool_approval.py` (new)

**Interfaces:**
- `BaseAgent.needs_tool_approval` (around `base_agent.py:629`) has 0 production callers — only 3 test `hasattr` assertions. Remove the method and update the tests.

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/test_base_agent_no_needs_tool_approval.py
"""P4 Task 2: verify needs_tool_approval is removed from BaseAgent."""


def test_needs_tool_approval_removed():
    from derisk.agent.core.base_agent import BaseAgent
    assert not hasattr(BaseAgent, "needs_tool_approval"), (
        "BaseAgent.needs_tool_approval should be removed in P4 "
        "(0 production callers; PermissionGate supersedes it)"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/test_base_agent_no_needs_tool_approval.py -v`
Expected: FAIL — `hasattr` returns True.

- [ ] **Step 3: Write minimal implementation**

Open `packages/derisk-core/src/derisk/agent/core/base_agent.py`. Find `def needs_tool_approval` (around line 629). Delete the method. Search for any references and remove them: `grep -rn "needs_tool_approval" packages/derisk-core/src/ packages/derisk-core/tests/`.

Update the 3 test `hasattr` assertions to assert the method is GONE (change `assert hasattr(...)` to `assert not hasattr(...)`), or delete those test cases if they were only testing the existence of the now-removed method.

- [ ] **Step 4: Run test to verify it passes + regression**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/test_base_agent_no_needs_tool_approval.py -v`
Expected: PASS

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/ -v`
Expected: PASS (any tests that previously asserted `hasattr(BaseAgent, "needs_tool_approval")` should have been updated in Step 3)

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/base_agent.py \
        packages/derisk-core/tests/agent/core/test_base_agent_no_needs_tool_approval.py \
        <any other test files updated>
git commit -m "chore(agent-v2): P4 Task 2 移除未使用的 needs_tool_approval (PermissionGate 已替代)"
```

---

## Task 3: Add DeprecationWarning to legacy push_* APIs + ActionOutput.ask_user

**Files:**
- Modify: `packages/derisk-core/src/derisk/agent/core/base_agent.py` (add warning to `push_context_event`)
- Modify: `packages/derisk-core/src/derisk/agent/core/memory/gpts/gpts_memory.py` (add warning to `push_message`, `queue_iterator`)
- Modify: `packages/derisk-core/src/derisk/agent/core/action/base.py` (add warning to `ActionOutput.ask_user` property)
- Test: `packages/derisk-core/tests/agent/core/test_legacy_deprecation_warnings.py` (new)

**Interfaces:**
- Each deprecated API emits `DeprecationWarning` when called, with a message pointing to the V2 replacement.
- `push_context_event` → "Use BAIZESubsystemAdapter.on_system_event() instead (V2 runtime)."
- `push_message` → "Use EventStream.emit() or BAIZESubsystemAdapter.on_worklog() instead (V2 runtime)."
- `queue_iterator` → "Use EventStream.subscribe() or step_event_to_stream_event() instead (V2 runtime)."
- `ActionOutput.ask_user` → "Return {'ask_user': ...} dict from acting_fn; runtime auto-converts via AskUserAdapter (V2 runtime)."

- [ ] **Step 1: Write the failing test**

```python
# packages/derisk-core/tests/agent/core/test_legacy_deprecation_warnings.py
"""P4 Task 3: legacy APIs emit DeprecationWarning pointing to V2 replacements."""
import warnings
import pytest


def test_push_context_event_emits_deprecation():
    from derisk.agent.core.base_agent import BaseAgent
    # Use a minimal subclass that doesn't require full init
    class MinimalAgent(BaseAgent):
        def __init__(self):
            pass
    agent = MinimalAgent()
    with pytest.warns(DeprecationWarning, match="BAIZESubsystemAdapter"):
        # push_context_event signature varies; call with empty args and catch TypeError after warning
        try:
            agent.push_context_event()
        except TypeError:
            pass  # signature mismatch is fine — we only care the warning fired


def test_push_message_emits_deprecation():
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
    # Memory classes often need init; use minimal stub
    class MinimalMemory(GptsMemory):
        def __init__(self):
            pass
    mem = MinimalMemory()
    with pytest.warns(DeprecationWarning, match="EventStream"):
        try:
            mem.push_message()
        except TypeError:
            pass


def test_action_output_ask_user_emits_deprecation():
    from derisk.agent.core.action.base import ActionOutput
    ao = ActionOutput(ask_user={"message": "hi"})
    with pytest.warns(DeprecationWarning, match="AskUserAdapter"):
        _ = ao.ask_user
```

Note: The exact constructor signatures of `BaseAgent`, `GptsMemory`, `ActionOutput` may differ. Inspect them first and adapt the tests. If a class can't be instantiated minimally, use `unittest.mock.MagicMock` for the instance and call the method via `type(mock).method_name(mock, ...)` to bypass `__init__`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/test_legacy_deprecation_warnings.py -v`
Expected: FAIL — no DeprecationWarning currently emitted.

- [ ] **Step 3: Write minimal implementation**

For each deprecated API, add `warnings.warn(..., DeprecationWarning, stacklevel=2)` at the top of the function/method/property.

Example for `ActionOutput.ask_user` (likely a `@property`):
```python
@property
def ask_user(self):
    import warnings
    warnings.warn(
        "ActionOutput.ask_user is deprecated. Return {'ask_user': ...} dict from acting_fn; "
        "runtime auto-converts via AskUserAdapter (V2 runtime).",
        DeprecationWarning,
        stacklevel=2,
    )
    return self._ask_user
```

Apply the same pattern to the other 3 APIs. Preserve existing behavior — the warning fires, then the original code runs unchanged.

- [ ] **Step 4: Run test to verify it passes + regression**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/test_legacy_deprecation_warnings.py -v`
Expected: PASS (3 tests)

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/ -v`
Expected: PASS — V2 runtime's `AskUserAdapter` path triggers the `ActionOutput.ask_user` deprecation warning, but tests should still pass (warnings don't fail tests unless `filterwarnings=error` is set).

If any V2 test fails because of the new warning, add `@pytest.mark.filterwarnings("ignore::DeprecationWarning")` to that test or filter in `pytest.ini`.

- [ ] **Step 5: Commit**

```bash
git add packages/derisk-core/src/derisk/agent/core/base_agent.py \
        packages/derisk-core/src/derisk/agent/core/memory/gpts/gpts_memory.py \
        packages/derisk-core/src/derisk/agent/core/action/base.py \
        packages/derisk-core/tests/agent/core/test_legacy_deprecation_warnings.py
git commit -m "chore(agent-v2): P4 Task 3 标记 legacy push_*/ask_user 为 Deprecated"
```

---

## Task 4: Verify V2 runtime still works end-to-end with deprecation warnings

**Files:**
- Test: `packages/derisk-core/tests/agent/core/v2/test_v2_runtime_with_deprecation.py` (new — regression)

**Interfaces:**
- Verify V2 runtime tests pass with the deprecation warnings in place.
- Verify `run_step` with an `acting_fn` that returns `{"ask_user": ...}` still works (AskUserAdapter path) — the `ActionOutput.ask_user` warning fires but doesn't break the flow.

- [ ] **Step 1: Write the test**

```python
# packages/derisk-core/tests/agent/core/v2/test_v2_runtime_with_deprecation.py
"""P4 Task 4: V2 runtime still works with deprecation warnings on legacy APIs."""
import warnings
import pytest
import tempfile
import os
from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.state_store import DbStateStore
from derisk.agent.core.v2.step_state import StepState


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DbStateStore(path)
    yield s
    os.unlink(path)


async def test_v2_ask_user_path_still_works_with_deprecation(store):
    """AskUserAdapter path still converts ask_user payloads even though
    ActionOutput.ask_user is now deprecated."""
    async def thinking(input_):
        yield {"token": "", "tool_calls": [{"tool": "legacy", "input": {}}]}

    async def acting(tc):
        return {"ask_user": {"message": "hi", "options": []}}

    events = []
    # Filter deprecation warnings to avoid noise — we just want to verify no exception
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        async for e in run_step("a", "c", {"prompt": "x"}, store, thinking, acting):
            events.append(e)

    states = [e.state for e in events]
    assert StepState.AWAITING_USER in states
```

- [ ] **Step 2: Run test**

Run: `cd packages/derisk-core && python -m pytest tests/agent/core/v2/test_v2_runtime_with_deprecation.py -v`
Expected: PASS (the AskUserAdapter path doesn't actually construct an `ActionOutput`, so the warning may not fire — but the test verifies the V2 path is unaffected).

- [ ] **Step 3: Commit**

```bash
git add packages/derisk-core/tests/agent/core/v2/test_v2_runtime_with_deprecation.py
git commit -m "test(agent-v2): P4 Task 4 V2 runtime 兼容 deprecation 回归"
```

---

## Task 5: Write §11.2 BAIZE → V2 migration follow-up plan stub

**Files:**
- Create: `docs/superpowers/plans/2026-07-02-agent-v2-runtime-p3-5-baize-migration.md`

**Interfaces:**
- A short plan stub (NOT executed in P4) documenting what §11.2 migration entails:
  - Migrate `react_master_agent.py` to call `run_step`/`resume_step` instead of `push_message`/`push_context_event`
  - Migrate the 5 BAIZE subsystems (ContextEngine/Kanban/WorkLog/Phase/SystemEventManager) to call `BAIZESubsystemAdapter` methods
  - Remove `queue_iterator` from `agent_chat.py`
  - Delete `base_agent.py` legacy code once all callers migrated
  - Estimated scope: 8-12 tasks, requires end-to-end BAIZE test setup

- [ ] **Step 1: Write the plan stub**

Write a markdown file at `docs/superpowers/plans/2026-07-02-agent-v2-runtime-p3-5-baize-migration.md` with the following sections:

```markdown
# Agent V2 Runtime P3.5: BAIZE → V2 Migration (§11.2) Plan Stub

**Status:** Not yet scheduled. This is a follow-up to P4, documenting the scope of §11.2 migration that P4 explicitly deferred.

## Why deferred

P4 could not safely remove `push_context_event` (method), `push_message`, `queue_iterator`, or `base_agent.py` because they are still used by `react_master_agent.py` and the legacy BAIZE build chain. Removing them would break the legacy build.

## Scope (estimated 8-12 tasks)

1. **Inventory BAIZE call sites** — map every `push_message`/`push_context_event`/`queue_iterator` call in `react_master_agent.py` and `agent_chat.py`.
2. **Migrate react_master_agent.py to V2 runtime** — replace `push_message` with `EventStream.emit()`; replace `push_context_event` with `BAIZESubsystemAdapter.on_system_event()`.
3. **Migrate ContextEngine** — replace internal `push_context_event` calls with `BAIZESubsystemAdapter.on_phase_change()`.
4. **Migrate Kanban** — replace with `BAIZESubsystemAdapter.on_kanban_update()`.
5. **Migrate WorkLogManager** — replace with `BAIZESubsystemAdapter.on_worklog()`.
6. **Migrate PhaseManager** — replace with `BAIZESubsystemAdapter.on_phase_change()`.
7. **Migrate SystemEventManager** — replace with `BAIZESubsystemAdapter.on_system_event()`.
8. **Remove queue_iterator from agent_chat.py** — replace with EventStream subscription.
9. **Delete base_agent.py legacy code** — once all callers migrated.
10. **End-to-end BAIZE integration tests** — crash recovery, async sub-agent detach/resume, cross-process tool auth (§11.3).

## Prerequisites

- End-to-end BAIZE test fixture (currently absent — P3 deferred §11.3 integration tests for this reason).
- Decision on whether `react_master_agent.py` is the integration point or whether a new V2 BAIZE orchestrator replaces it.

## When to schedule

After P4 cleanup is merged and the team is ready to commit to migrating the BAIZE path. This is a multi-week effort, not a single sprint.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-07-02-agent-v2-runtime-p3-5-baize-migration.md
git commit -m "docs(agent-v2): P4 Task 5 §11.2 BAIZE 迁移 follow-up plan stub"
```

---

## Self-Review

**1. Spec coverage (P4 scope = cleanup of P3-redundant legacy code):**
- ✅ Remove orphan `push_context_event` wrapper (0 callers) → Task 1
- ✅ Remove `needs_tool_approval` (0 production callers) → Task 2
- ✅ Deprecate `push_context_event` (method), `push_message`, `queue_iterator`, `ActionOutput.ask_user` → Task 3
- ✅ V2 runtime regression with deprecation warnings → Task 4
- ✅ §11.2 BAIZE migration documented as follow-up → Task 5
- ⏭️ Actual removal of `push_context_event` (method), `push_message`, `queue_iterator`, `base_agent.py` → **Deferred to §11.2 (P3.5)**. These are still used by `react_master_agent.py`; removing them breaks the legacy build.

**2. Placeholder scan:** No TBD/TODO. Task 5 is a plan stub by design — it documents future work, not a placeholder.

**3. Type consistency:** No new types introduced. Deprecation warnings are standard library `DeprecationWarning`.

**4. P4 简化声明：**
- P4 does NOT delete `base_agent.py`, `push_context_event` (method), `push_message`, or `queue_iterator`. They are entangled with `react_master_agent.py` (legacy BAIZE path). Removing them requires §11.2 migration first.
- P4 marks them deprecated to signal intent and prepare consumers.
- The §11.2 migration is documented as a follow-up plan stub (Task 5), not executed.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-agent-v2-runtime-p4.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
