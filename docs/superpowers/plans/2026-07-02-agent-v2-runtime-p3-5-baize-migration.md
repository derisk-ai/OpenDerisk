# Agent V2 Runtime P3.5: BAIZE → V2 Migration (§11.2) Plan Stub

**Status:** Not yet scheduled. This is a follow-up to P4, documenting the scope of §11.2 migration that P4 explicitly deferred.

## Why deferred

P4 could not safely remove `push_context_event` (method on `BaseAgent`), `push_message`, `queue_iterator`, or `base_agent.py` because they are still used by `react_master_agent.py` and the legacy BAIZE build chain. Removing them would break the legacy build.

Investigation findings (P4 scoping, 2026-07-02):
- `push_context_event` (method): 14 call sites — `base_agent.py`, `role.py`, `scheduled_agent.py`, `react_master_agent.py`.
- `push_message`: 19 call sites — `agent_chat.py`, `react_master_agent.py`, `tool_action.py`, `reasoning_action.py`.
- `queue_iterator`: 1 call site — `agent_chat.py:2889`.
- `ActionOutput.ask_user`: ~30 references; V2 compat at `runtime.py:161` + `ask_user_adapter.py`.
- `base_agent.py`: imported by `react_master_agent.py`, `simple_assistant_agent.py`, `user_proxy_agent.py`, `agent_chat.py`, vis converters.

The 5 BAIZE subsystems (`ContextEngine`/`Kanban`/`WorkLogManager`/`PhaseManager`/`SystemEventManager`) do NOT call `push_*` directly — only `react_master_agent.py` (the orchestrator) does. Migration is therefore primarily about replacing the orchestrator's calls, not rewriting the subsystems.

## Scope (estimated 8-12 tasks)

1. **Inventory BAIZE call sites** — map every `push_message`/`push_context_event`/`queue_iterator` call in `react_master_agent.py` and `agent_chat.py`. Document the data flow (what payload each call carries, where it ends up in the SSE stream).

2. **Migrate `react_master_agent.py` to V2 runtime** — replace `push_message` calls with `EventStream.emit()`; replace `push_context_event` calls with `BAIZESubsystemAdapter.on_system_event()`. This is the central task — likely 2-3 sub-tasks.

3. **Migrate ContextEngine** — replace internal `push_context_event` calls (if any) with `BAIZESubsystemAdapter.on_phase_change()`.

4. **Migrate Kanban** — replace with `BAIZESubsystemAdapter.on_kanban_update()`.

5. **Migrate WorkLogManager** — replace with `BAIZESubsystemAdapter.on_worklog()`.

6. **Migrate PhaseManager** — replace with `BAIZESubsystemAdapter.on_phase_change()`.

7. **Migrate SystemEventManager** — replace with `BAIZESubsystemAdapter.on_system_event()`.

8. **Remove `queue_iterator` from `agent_chat.py`** — replace with `EventStream` subscription.

9. **Delete `base_agent.py` legacy code** — once all callers migrated. Verify with grep that no imports remain.

10. **End-to-end BAIZE integration tests** — crash recovery, async sub-agent detach/resume, cross-process tool auth (§11.3). Requires a BAIZE test fixture (currently absent).

## Prerequisites

- End-to-end BAIZE test fixture (currently absent — P3 deferred §11.3 integration tests for this reason).
- Decision on whether `react_master_agent.py` is the integration point or whether a new V2 BAIZE orchestrator replaces it.
- Product decision on whether the legacy serve/agent stream protocol is preserved or replaced by V2 SSE.

## When to schedule

After P4 cleanup is merged and the team is ready to commit to migrating the BAIZE path. This is a multi-week effort, not a single sprint.

## References

- P3 plan: `docs/superpowers/plans/2026-07-01-agent-v2-runtime-p3.md` (BAIZESubsystemAdapter skeleton, §10.6/§11.1)
- P4 plan: `docs/superpowers/plans/2026-07-02-agent-v2-runtime-p4.md` (deprecation markings, this stub's parent)
- Spec sections: §10.4 (三管道归并), §11.1 (BAIZE 子系统适配层细化), §11.2 (ReactMasterAgent.bind), §11.3 (集成测试)
