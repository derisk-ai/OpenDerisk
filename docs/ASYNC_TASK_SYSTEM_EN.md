# AsyncTaskManager - Async Task Execution System

## 1. Overview

AsyncTaskManager provides Claude Code Agent Tool-like async task capabilities for the OpenDerisk Agent framework. The main Agent can launch background sub-Agent tasks through standard Tool calls during its ReAct loop, continue its own work without blocking, query or wait for results at any time, and completed results are automatically injected into the next LLM reasoning context.

### Core Capabilities

| Capability | Description |
|-----------|-------------|
| Async Submit | `spawn_agent_task` launches background tasks, returns task_id immediately |
| Status Query | `check_tasks` views task status without blocking |
| Wait for Results | `wait_tasks` blocks until specified or any tasks complete |
| Cancel Task | `cancel_task` cancels running or pending tasks |
| DAG Dependencies | `depend_on` parameter supports task dependency orchestration |
| Auto Notification | Completed task results auto-injected before next think() |

### Design Principles

1. **Tool-driven** — LLM decides when to go async via standard Tools
2. **Reuse existing architecture** — Delegates to `SubagentManager.delegate()` for execution
3. **Auto-injection** — Completed results flow naturally into LLM reasoning context
4. **asyncio native** — Built on Python asyncio Semaphore/Future/Event
5. **Progressive enhancement** — Zero breaking changes, opt-in via resource injection

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Agent (ReAct Loop)                    │
│                                                               │
│  think() ──► decide() ──► act() ──► [inject] ──► think()    │
│                              │            ▲                    │
│              ┌───────────────┼────────────┤                   │
│              ▼               ▼            ▼                    │
│     ┌──────────────┐ ┌────────────┐ ┌──────────────┐        │
│     │ spawn_agent  │ │ check_tasks│ │ wait_tasks   │        │
│     │   _task      │ │   (Tool)   │ │   (Tool)     │        │
│     └──────┬───────┘ └─────┬──────┘ └──────┬───────┘        │
└────────────┼───────────────┼────────────────┼─────────────────┘
             │               │                │
    ┌────────▼───────────────▼────────────────▼────────┐
    │              AsyncTaskManager                     │
    │  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
    │  │ Task A  │  │ Task B  │  │ Task C  │          │
    │  │ RUNNING │  │ DONE    │  │ PENDING │          │
    │  └─────────┘  └─────────┘  └─────────┘          │
    │       ↓                                           │
    │  SubagentManager.delegate() + asyncio controls   │
    └──────────────────────────────────────────────────┘
```

## 3. Quick Start

### Automatic Integration (Recommended)

When an Agent has `AppResource` (multi-agent scenario) and `SubagentManager`, `BaseBuiltinAgent` automatically injects async task tools. No extra configuration needed.

### Manual Integration

```python
from derisk.agent.core_v2.async_task_manager import AsyncTaskManager
from derisk.agent.tools.builtin.async_task import register_async_task_tools

# 1. Create AsyncTaskManager
async_manager = AsyncTaskManager(
    subagent_manager=my_subagent_manager,
    max_concurrent=5,
    parent_session_id="session_abc",
)

# 2. Register tools
register_async_task_tools(
    registry=agent.tools,
    async_task_manager=async_manager,
)

# 3. Save reference for auto-notification
agent._async_task_manager = async_manager
```

## 4. Tool Reference

### spawn_agent_task

Launches a background Agent task. Returns immediately with task_id.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| agent_name | string | Yes | Target sub-Agent name |
| task | string | Yes | Task description |
| context | object | No | Context information |
| timeout | integer | No | Timeout in seconds (default 300) |
| depend_on | string[] | No | List of task_ids to depend on |

### check_tasks

Views current status of background tasks without blocking.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task_ids | string[] | No | Specific task_ids to query (empty = all) |

### wait_tasks

Blocks until tasks complete and returns results.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task_ids | string[] | No | Task_ids to wait for (empty = wait for any) |
| timeout | integer | No | Max wait seconds (default 60) |

### cancel_task

Cancels a running or pending task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task_id | string | Yes | Task ID to cancel |

## 5. DAG Dependency Orchestration

Use `depend_on` to build task dependency graphs:

```
spawn_agent_task(agent="collector", task="Collect data")           -> task_001
spawn_agent_task(agent="scanner",  task="Scan environment")        -> task_002
spawn_agent_task(agent="analyzer", task="Analyze",
                 depend_on=["task_001", "task_002"])                -> task_003
spawn_agent_task(agent="reporter", task="Generate report",
                 depend_on=["task_003"])                           -> task_004

Execution graph:
  task_001 (collect) ──┐
                        ├──► task_003 (analyze) ──► task_004 (report)
  task_002 (scan)    ──┘
```

**Rules:**
- All dependencies must complete successfully before the current task starts
- If any dependency fails/times out/is cancelled, the current task also fails
- Circular dependencies are not detected (timeout mechanism provides safety net)

## 6. Auto-Notification Injection

In `ReActReasoningAgent.think()`, before each LLM call, completed async task results are automatically injected as a user message:

```
[Async Task Completion Notification]
The following background tasks have completed:

### Task atask_a1b2c3d4 (code_reviewer)
Status: completed
Result:
Code review complete. Found 2 security issues...
```

This allows the LLM to naturally incorporate background task results into its reasoning without explicit polling.

## 7. Concurrency & Safety

- **Concurrency limit**: `AsyncTaskManager(max_concurrent=5)` — at most 5 tasks running simultaneously
- **Per-task timeout**: `spec.timeout` (default 300s)
- **Wait timeout**: `wait_tasks(timeout=60)`
- **Context isolation**: Each sub-Agent task runs via `SubagentManager` with session isolation

## 8. Data Models

### AsyncTaskStatus

```python
class AsyncTaskStatus(str, Enum):
    PENDING = "pending"      # Queued
    RUNNING = "running"      # Executing
    COMPLETED = "completed"  # Success
    FAILED = "failed"        # Error
    TIMEOUT = "timeout"      # Timed out
    CANCELLED = "cancelled"  # Cancelled
```

### AsyncTaskSpec

```python
class AsyncTaskSpec(BaseModel):
    task_id: str            # Auto-generated "atask_{8hex}"
    agent_name: str         # Target agent
    task_description: str   # Task prompt
    context: Dict = {}      # Extra context
    timeout: int = 300      # Timeout seconds
    depend_on: List[str] = []  # Dependency task_ids
```

### AsyncTaskState

```python
class AsyncTaskState(BaseModel):
    spec: AsyncTaskSpec
    status: AsyncTaskStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[str]    # Success output
    error: Optional[str]     # Error message
    artifacts: Dict          # Output artifacts
    consumed: bool           # Whether consumed by main agent
```

## 9. File Locations

| File | Description |
|------|-------------|
| `core_v2/async_task_manager.py` | Core manager + data models |
| `tools/builtin/async_task/async_task_tools.py` | 4 Tool implementations |
| `tools/builtin/async_task/__init__.py` | Module registration |
| `core_v2/builtin_agents/base_builtin_agent.py` | Core V2 auto-injection logic |
| `core_v2/builtin_agents/react_reasoning_agent.py` | Core V2 notification injection |
| `expand/react_master_agent/react_master_agent.py` | Core V1 integration (tool + notification injection) |
| `tests/agent/core_v2/test_async_task_manager.py` | Manager unit tests |
| `tests/agent/core_v2/test_async_task_tools.py` | Tool unit tests |

## 10. Core V1 Integration (ReActMasterAgent)

Async task capabilities are also integrated into the Core V1 `ReActMasterAgent`.

### How It Works

Core V1 uses `FunctionTool` + `AgentAction` pattern (different from Core V2's `ToolBase`). Integration is achieved through:

1. **CoreV1SubagentAdapter**: Adapts Core V1's `send()/receive()` pattern to `SubagentManager.delegate()` interface
2. **4 FunctionTool wrappers**: `_spawn_agent_task`, `_check_tasks`, `_wait_tasks`, `_cancel_task`
3. **Notification injection**: In `thinking()`, completed task notifications are injected via `tool_messages`

### Differences from Core V2

| Feature | Core V2 | Core V1 |
|---------|---------|---------|
| Tool type | `ToolBase` subclass | `FunctionTool` wrapper |
| Tool registry | `ToolRegistry` | `available_system_tools` dict |
| Notification injection | `think()` → messages list | `thinking()` → tool_messages |
| `depend_on` param | JSON array | Comma-separated string |
| `task_ids` param | JSON array | Comma-separated string |
| Auto-inject condition | AppResource + SubagentManager | available_agents non-empty |

### Core V1 Notes

- Core V1's `FunctionTool` doesn't support array parameters, so `depend_on` and `task_ids` use comma-separated strings (e.g., `"task_001,task_002"`)
- Tools are injected during `preload_resource()` when multi-agent scenario is detected
- Notifications are automatically injected in each `thinking()` call

## 11. Comparison with Claude Code Agent Tool

| Capability | Claude Code | OpenDerisk AsyncTask |
|-----------|-------------|---------------------|
| Launch sub-Agent | `Agent` tool | `spawn_agent_task` tool |
| Sync wait | Default foreground | `wait_tasks` explicit wait |
| Background run | `run_in_background: true` | Default async |
| Result notification | Auto notify | `_collect_async_task_notifications` auto-inject |
| Parallel tasks | Multiple Agent tool calls | Multiple `spawn_agent_task` |
| Task dependencies | None | `depend_on` DAG |
| Isolation | `isolation: "worktree"` | `SubagentContextConfig` |
| Cancel | `TaskStop` | `cancel_task` |
| Status query | `TaskOutput` | `check_tasks` |
