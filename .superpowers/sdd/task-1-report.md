# Task 1 Report: Backend -- start_task truly creates Task and emits task_created event

## Status
DONE

## Commits
`8dfeee49` — feat(workspace): make start_task create task and emit task_created event

## What I implemented

1. **`_task_creator.py` (new)**: Helper module `create_task_from_tool()` that calls `TaskService.create` via `system_app.get_component`. Handles playbook lookup, title fallback, and user_id validation.

2. **`write_tools.py` (modified)**: `start_task` now uses `create_task_from_tool` and emits `task_created` via the `on_event` callback. Other tools (`close_task`, `publish_asset`, `create_delivery`, `update_workspace`) continue to create interventions as before. Added `WorkspaceEventCallback` type alias and `on_event` parameter to `build_write_tools`.

3. **`toolkit.py` (modified)**: Added `on_event` parameter to `build_workspace_toolkit` and passes it through to both `build_write_tools` and `build_playbook_tools`.

4. **`playbook_tools.py` (modified)**: Added `on_event` parameter (forward-compatible, no behavior change yet) and `Callable` import.

5. **`agent_chat.py` (modified)**:
   - Added `event_queue` parameter to `_inject_workspace_context`
   - Created `_on_workspace_event` callback inside `_inject_workspace_context` that puts events into the queue
   - Passes `on_event=_on_workspace_event` to `build_workspace_toolkit`
   - Creates `workspace_event_queue: asyncio.Queue` in `aggregation_chat`
   - Drains the queue in the SSE generator loop before each message chunk yield

6. **Existing tests updated**: `test_write_tool_creates_intervention_with_null_task` now tests `close_task` instead of `start_task`; `test_each_write_tool_uses_its_own_name_in_question` skips `start_task`.

## Test summary

### New tests (7/7 passing)
- `test_creates_task_with_playbook` - creates task with playbook_id, title defaults to playbook name
- `test_creates_task_with_custom_title` - custom title overrides playbook name
- `test_creates_task_without_playbook` - no playbook, title defaults to "手动创建任务"
- `test_user_id_non_digit` - non-digit user_id produces None created_by_user_id
- `test_start_task_emits_event` - verify on_event is called with task_created
- `test_start_task_without_event_callback` - no error when on_event is None
- `test_non_start_task_tools_still_create_interventions` - close_task still creates intervention

### All workspace tests (68/68 passing)
- 7 new tests in `tests/workspace/agent_tools/test_write_tools.py`
- 61 existing tests across `tests/derisk_serve/workspace/` - all pass, no regressions

### TDD Evidence
- RED: Tests were written before implementation. Initial failures were due to `FunctionTool` using `.execute()` not `.func()` - fixed by using the public API.
- GREEN: All 7 tests pass after implementation. All 68 workspace tests pass.

### Test output
```
68 passed, 31 warnings in 3.39s
```
Warnings are all pre-existing Pydantic deprecation warnings, not from our changes.

## Files changed

- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py` (new)
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py` (modified)
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py` (modified)
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/playbook_tools.py` (modified)
- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` (modified)
- `packages/derisk-serve/tests/derisk_serve/workspace/test_agent_tools.py` (modified)
- `packages/derisk-serve/tests/workspace/agent_tools/test_write_tools.py` (new)
- `packages/derisk-serve/tests/workspace/__init__.py` (new)
- `packages/derisk-serve/tests/workspace/agent_tools/__init__.py` (new)

## Self-review findings

- **Correctness**: The `start_task` tool now creates a real Task via `TaskService.create` and emits `task_created` event through the SSE stream. The `format_workspace_event` helper and `WORKSPACE_EVENT_TYPES` whitelist (already containing `task_created`) ensure the event protocol is correct.
- **Edge cases**: Handled `user_id` being non-digit, missing `playbook_id`, `on_event` being None, `event_queue` being None.
- **No breaking changes**: All other write tools still create interventions. The `on_event` parameter is optional with default `None`, so existing callers are unaffected.
- **No overbuilding**: Only modified what was specified. No extra abstractions.

## Concerns

None. The implementation is straightforward and follows the plan exactly.

## Fix Report (2026-07-06)

Addressed three Important test-quality issues and two Minor cleanups from the Task 1 review.

### Important 1: `test_user_id_non_digit` asserts `created_by_user_id=None`

Added `request.created_by_user_id is None` assertion by capturing the `TaskRequest` from `mock_task_service.create.call_args.args[0]`.

### Important 2: `TaskRequest` field assertions in all three create tests

Added `TaskRequest` field assertions to `test_creates_task_without_playbook`, `test_creates_task_with_playbook`, and `test_creates_task_with_custom_title`. Each test now verifies `workspace_id`, `title`, `type`, `triggered_by`, `created_by_user_id`, and (where applicable) `playbook_id`, `description`.

### Important 3: Removed unused mocks from `test_non_start_task_tools_still_create_interventions`

Removed `mock_task_service` and `mock_playbook_service` from the `get_component` function. `close_task` only needs the intervention service.

### Minor 1: Trailing newlines

Added trailing newlines to `_task_creator.py`, `write_tools.py`, and `test_write_tools.py`.

### Minor 2: Extracted shared `_build_system_app` helper in `TestWriteToolsStartTask`

Refactored `test_start_task_emits_event` and `test_start_task_without_event_callback` to use a shared `_build_system_app` helper.

### Test results

- `tests/workspace/agent_tools/test_write_tools.py`: 7 passed, 31 warnings
- `tests/derisk_serve/workspace/`: 61 passed, 31 warnings
- All warnings are pre-existing Pydantic deprecation warnings.
