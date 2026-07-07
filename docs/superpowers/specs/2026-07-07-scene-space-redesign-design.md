# Scene Space Redesign — Design Spec

## Status

Approved by product owner. Ready for implementation planning.

## Problem Statement

The current scenario workspace detail page (`/workspaces/detail`) mixes lobby overview, full-page chat, and task workbench in a single switching canvas. The layout does not match the operational mental model: a user wants a persistent Agent companion on the right, a task/intervention feed on the left, and a central scene space that acts as an interactive canvas linked to Agent actions.

## Goals

1. Provide a 3-column layout: task/intervention rail | scene space | Agent workspace.
2. Make the right Agent workspace a persistent single-Agent interface: recent work steps above, standard chat input below, no conversation history list.
3. Let the middle scene space default to a scenario dashboard and switch to context-aware detail views when the user or Agent selects a task, file, tool result, or entity.
4. Support two distinct left-rail actions: preview a task in the scene space vs. enter that task’s Agent conversation.

## Non-Goals

- Reuse `/chat` via iframe.
- Support multiple concurrent chat histories or a conversation list in the workspace.
- Transform the page into a generic chat application.

## Reference

- Reference UI: 3-column operational console (event list | detail | AI assistant panel).
- Existing components: `VisRunningWindowV2`, `VisAgentFolder`, `VisStepListCard`, `ChatSession`, `Lobby`.

## Architecture & Layout

```
┌─────────────────┬───────────────────────────────┬─────────────────────────────┐
│  SceneTaskRail  │         SceneSpace            │       AgentWorkspace        │
│  (left, fixed   │      (middle, flexible)       │    (right, fixed ~420px)    │
│   width ~280px) │                               │                             │
│                 │                               │  ┌───────────────────────┐  │
│  Mixed task/    │  Default: scenario dashboard  │  │  AgentProcessPanel    │  │
│  intervention   │  (lobby cards).               │  │  (compact timeline of │  │
│  feed.          │                               │  │   recent Agent steps) │  │
│                 │  On selection: context-aware  │  │                       │  │
│  Each item has  │  renderer switches to task    │  └───────────────────────┘  │
│  two click      │  detail / file preview /      │  ┌───────────────────────┐  │
│  targets.       │  tool result / entity card.   │  │   AgentChatInput      │  │
│                 │                               │  │  (single persistent   │  │
│                 │                               │  │   input; no history)  │  │
│                 │                               │  └───────────────────────┘  │
└─────────────────┴───────────────────────────────┴─────────────────────────────┘
```

### Page header (retained from current design)

- Workspace title and metadata.
- Nav links: 触发源 / 任务 / 交付空间 / 产出物 / 介入 / 设置.
- **Removed**: the conversation switcher button.

### Signal chain and Loop strip

- The existing `SignalChain` and `Loop` strip are removed from the main layout to avoid clutter in the 3-column design.
- Their key status counts (queued, running, needs review, delivered, in memory) are absorbed into the `SceneSpace` default dashboard cards.

## Components & Responsibilities

### `WorkspaceDetailPage` (`web/src/app/workspaces/detail/client.tsx`)

- Fetch workspace info, tasks, interventions, artifacts, deliveries, playbooks, triggers.
- Fetch or create the single workspace-level `conv_uid`.
- Render header (without conversation switcher) + `SceneWorkspaceShell`.

### `SceneWorkspaceShell`

- Owns the 3-column layout CSS.
- Owns shared state:
  - `previewItem` — task/intervention being previewed in the middle.
  - `activeTaskId` — task whose Agent process + input is loaded into the right panel; `null` means workspace-level Agent.
  - `detailContext` — what the middle space renders (`dashboard`, `task-detail`, `file-preview`, `tool-result`, `entity-card`).
- Handles mode transitions:
  - Left task body click → set `previewItem`, `detailContext='task-detail'`, keep `activeTaskId=null`.
  - Left task “进入对话” click → set `activeTaskId=task.id`, load task’s `conv_session_id` into right panel.
  - Exit task mode → set `activeTaskId=null`, return to workspace `convUid`.
  - Agent step/tool click → set `detailContext='file-preview' | 'tool-result' | 'entity-card'`.

### `SceneTaskRail` (left panel)

- Renders mixed chronological list of tasks + interventions, sorted by `updated_at` descending (most recently changed first).
- Each item shows title, status badge, timestamp, and two actions:
  - Body click → preview in middle.
  - “进入对话” button → switch right panel to task-scoped Agent.
- Supports filtering by status and search by title.

### `SceneSpace` (middle panel)

- **Default view**: scenario dashboard — running tasks, recent deliveries, hosted artifacts, quick-start playbooks (reuses current Lobby content).
- **Task detail view**: task conclusion/delivery records + interaction cards (buttons like “确认”, “重新打开”, etc.).
- **File preview view**: render file content (code, markdown, image) when Agent reads/writes a file.
- **Tool result view**: render tool output.
- **Entity card view**: task/artifact/asset summary when Agent queries an entity.
- Provides a “返回 dashboard” action.

### `AgentWorkspace` (right panel)

- **Top: `AgentProcessPanel`** — compact vertical timeline of recent Agent steps. Derives steps from streaming vis data / workspace events. Limit to ~5–8 recent steps, auto-scroll to latest.
- **Bottom: `AgentChatInput`** — single persistent textarea + send button. Sends to the active conversation (workspace or task). No message history list.

### `useSceneAgentChat` hook

- Wraps `useChat` for the persistent single-Agent input.
- Manages the SSE stream.
- Parses `vis` payloads into Agent steps for `AgentProcessPanel`.
- Emits workspace events for middle-space linkage.
- Aborts previous request on new input.

## Data Flow

### 1. Persistent workspace Agent conversation

- On page load, `WorkspaceDetailPage` fetches or creates one workspace-level `conv_uid`.
- `AgentWorkspace` mounts with this `conv_uid`.
- `AgentChatInput` calls `useSceneAgentChat({ convUid, appCode })`.
- On send, `useSceneAgentChat` posts user input to `/api/v1/chat/completions`.
- SSE stream returns:
  - `vis` objects (Agent step/plan data) → parsed into step items and appended to `AgentProcessPanel`.
  - `workspace_event` objects (file read/write, task query, etc.) → forwarded to `SceneWorkspaceShell` to update `detailContext` or show toast hints.
  - Final text/markdown → ignored in the right panel because there is no chat history list; task completion summaries are shown via `AgentProcessPanel` step updates or `SceneSpace` dashboard cards.

### 2. Task preview from left rail

- User clicks a task body in `SceneTaskRail`.
- `SceneWorkspaceShell` sets `previewItem={task}`, `detailContext='task-detail'`.
- `SceneSpace` fetches task info + artifacts + deliveries for that task.
- Right panel stays on workspace-level Agent; no conversation switch.

### 3. Enter task conversation

- User clicks “进入对话” on a task.
- `SceneWorkspaceShell` sets `activeTaskId=task.id`.
- `AgentWorkspace` fetches the task’s `conv_session_id` and switches `useSceneAgentChat` to that `conv_uid`.
- `AgentProcessPanel` clears/loads steps for that task.
- `SceneSpace` also switches to that task’s detail view (or stays if already previewing it).

### 4. Agent step → middle detail linkage

- `AgentProcessPanel` renders step items. Some steps carry metadata like `file_id`, `tool_name`, `task_id`.
- User clicks a step.
- `SceneWorkspaceShell` sets `detailContext` to `file-preview`, `tool-result`, or `entity-card`, and passes the step payload to `SceneSpace`.
- `SceneSpace` fetches/renders the relevant detail.

### 5. Exit task conversation

- User clicks “退出任务对话”.
- `SceneWorkspaceShell` clears `activeTaskId`.
- `AgentWorkspace` switches back to workspace `conv_uid`.
- `AgentProcessPanel` resets to workspace steps.
- `SceneSpace` returns to dashboard (or keeps previewing the last task).

## Error Handling & Edge Cases

### Conversation load failure

- If workspace `conv_uid` cannot be fetched/created, show an error state in `AgentWorkspace` with a “Retry” button; disable input.
- If a task’s `conv_session_id` fails to load, show inline error in `AgentWorkspace` and keep workspace-level Agent active.

### SSE stream errors

- On network error or non-OK response, `useSceneAgentChat` aborts and shows an error toast.
- The last step in `AgentProcessPanel` is marked `failed`.
- User can retry the last input.

### Empty / idle states

- `AgentProcessPanel`: when no steps yet, show “Agent 就绪，输入指令开始工作”.
- `SceneTaskRail`: empty list → “暂无任务或介入请求”.
- `SceneSpace` dashboard: empty sections show empty placeholders (reuses current Lobby empty states).

### File / detail fetch failures

- If a clicked file preview fails, `SceneSpace` shows error card with retry.
- If a task detail fetch fails, show error with retry and a “返回列表” button.

### Mode transitions

- While switching task conversations, show a loading overlay in `AgentWorkspace`.
- If user clicks “进入对话” while another request is in flight, queue or disable the action to avoid race conditions.

### Responsiveness

- On narrow screens, collapse left rail into a toggle; right panel becomes full-width overlay or slides in.

## Testing & Verification

### Unit tests

- `useSceneAgentChat`: mock SSE stream; verify steps are parsed and emitted correctly; verify abort on new input; verify error handling.
- `SceneTaskRail` filtering/search: verify mixed list renders tasks and interventions; verify click handlers fire correct action.
- `SceneSpace` context switching: verify dashboard → task-detail → file-preview transitions render correct sub-component.

### Integration tests

- Load a workspace detail page; verify the 3-column layout renders.
- Send a message via `AgentChatInput`; verify `AgentProcessPanel` receives and displays steps.
- Click a task body; verify `SceneSpace` shows task detail without switching right panel.
- Click “进入对话”; verify `AgentWorkspace` switches to task conversation and loads task steps.
- Click an Agent step carrying a `file_id`; verify `SceneSpace` opens file preview.

### Manual verification

- Header nav links work and conversation switcher is removed.
- Responsive behavior on narrow viewport.
- Empty states display correctly.
- SSE error recovery.

### Success criteria

- Page loads with the 3-column layout.
- Right panel shows persistent input + recent Agent steps.
- Middle space switches between dashboard and detail views based on user/Agent actions.
- Left rail supports preview vs. conversation modes.

## Open Questions Resolved

- Layout: 3 columns (left rail | middle scene space | right Agent workspace).
- Right panel: top compact Agent step timeline, bottom single persistent chat input, no chat history list.
- Middle panel: default scenario dashboard; context-aware detail views on selection.
- Left rail: mixed chronological feed of tasks + interventions; body click previews, “进入对话” enters task Agent mode.
- Chat scope: workspace-level by default; task-scoped when user enters a task conversation.
- Agent process window: compact recent-steps timeline (list style), not a full plan tree.
