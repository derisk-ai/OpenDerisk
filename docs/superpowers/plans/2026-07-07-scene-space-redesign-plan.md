# Scene Space Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `/workspaces/detail` as a 3-column operational console: task/intervention rail on the left, context-aware scene space in the middle, and a persistent single-Agent workspace on the right.

**Architecture:** A thin `WorkspaceDetailPage` loads workspace data and renders `SceneWorkspaceShell`. The shell owns the 3-column layout and shared selection state. Each column is a focused component: `SceneTaskRail`, `SceneSpace`, and `AgentWorkspace`. The right panel uses a custom `useSceneAgentChat` hook to stream Agent steps into `AgentProcessPanel` while keeping a single persistent input.

**Tech Stack:** Next.js 15, React 18, TypeScript, Ant Design 5, ahooks, styled-components (existing patterns), Jest + ts-jest for hook/pure-function tests.

## Global Constraints

- Do not reuse `/chat` via iframe.
- No conversation history list or conversation switcher in the workspace.
- Right panel is a persistent single-Agent interface: recent steps above, input below.
- Left rail has two click modes: body click previews in scene space; “进入对话” enters task Agent mode.
- Middle space defaults to scenario dashboard and switches to context-aware detail views.
- Signal chain and Loop strip are removed; their counts move into the dashboard.
- Follow existing file organization under `web/src/app/workspaces/detail/`.
- Prefer focused files; keep `client.tsx` as a thin loader.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `client.tsx` | Data loader, header, renders `SceneWorkspaceShell`. Remove `ConversationSwitcher`, `SignalChain`, `Loop`, and `Workbench` usage. |
| `scene-workspace-shell.tsx` | 3-column layout, shared state (`previewItem`, `activeTaskId`, `detailContext`), mode transitions. |
| `scene-task-rail.tsx` | Left panel: mixed task/intervention feed, search/filter, two click actions. |
| `scene-space.tsx` | Middle panel: context-aware renderer (dashboard, task detail, file preview, tool result, entity card). |
| `agent-workspace.tsx` | Right panel: composes `AgentProcessPanel` + `AgentChatInput`, manages active conversation. |
| `agent-process-panel.tsx` | Compact vertical timeline of recent Agent steps. |
| `agent-chat-input.tsx` | Single persistent textarea + send button. |
| `use-scene-agent-chat.ts` | Hook wrapping `useChat` for persistent single-Agent streaming. |
| `agent-types.ts` | Shared `AgentStep` type and related types. |
| `parse-agent-steps.ts` | Pure function converting `vis` payloads to `AgentStep` items (testable). |
| `__tests__/parse-agent-steps.test.ts` | Unit tests for `parseAgentSteps`. |
| `scene-workspace.css` | Layout CSS for the 3-column shell and panels. |

---

### Task 1: Add jest test script to package.json

**Files:**
- Modify: `web/package.json`

**Interfaces:**
- Consumes: existing `jest.config.js`.
- Produces: `npm test` command in `web/`.

- [ ] **Step 1: Add test script**

Add `"test": "jest"` to `scripts` in `web/package.json`:

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "export": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "jest"
  }
}
```

- [ ] **Step 2: Verify script is valid**

Run:
```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npm test -- --listTests
```

Expected: lists existing `V2SimplifiedVisParser.test.ts` and exits 0.

- [ ] **Step 3: Commit**

```bash
git add web/package.json
git commit -m "chore(web): add jest test script"
```

---

### Task 2: Define AgentStep types and parse-agent-steps pure function

**Files:**
- Create: `web/src/app/workspaces/detail/agent-types.ts`
- Create: `web/src/app/workspaces/detail/parse-agent-steps.ts`
- Create: `web/src/app/workspaces/detail/__tests__/parse-agent-steps.test.ts`

**Interfaces:**
- Consumes: backend `vis` payloads (shape documented below).
- Produces: `AgentStep` type, `parseAgentSteps(vis: unknown): AgentStep | null`.

- [ ] **Step 1: Write the failing test**

Create `web/src/app/workspaces/detail/__tests__/parse-agent-steps.test.ts`:

```typescript
import { parseAgentSteps } from '../parse-agent-steps';

describe('parseAgentSteps', () => {
  test('returns null for non-object payload', () => {
    expect(parseAgentSteps(null)).toBeNull();
    expect(parseAgentSteps('string')).toBeNull();
  });

  test('parses workspace_event into AgentStep', () => {
    const vis = {
      type: 'task_created',
      payload: { task_id: 42, title: 'Refund check' },
    };
    const step = parseAgentSteps(vis);
    expect(step).not.toBeNull();
    expect(step?.type).toBe('task_created');
    expect(step?.title).toBe('Task created');
    expect(step?.status).toBe('done');
    expect(step?.payload?.task_id).toBe(42);
  });

  test('parses step_list item into AgentStep', () => {
    const vis = {
      type: 'step_list',
      payload: {
        steps: [
          { tool_name: 'query_db', status: 'EXECUTING' },
        ],
      },
    };
    const step = parseAgentSteps(vis);
    expect(step?.type).toBe('tool_call');
    expect(step?.title).toBe('query_db');
    expect(step?.status).toBe('running');
  });

  test('returns null for unknown vis type', () => {
    expect(parseAgentSteps({ type: 'unknown', payload: {} })).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npm test -- parse-agent-steps
```

Expected: FAIL — modules not found.

- [ ] **Step 3: Implement types and parser**

Create `web/src/app/workspaces/detail/agent-types.ts`:

```typescript
export type AgentStepType =
  | 'task_created'
  | 'context_loaded'
  | 'tool_call'
  | 'intervention_triggered'
  | 'artifact_produced'
  | 'delivery_sent'
  | 'asset_referenced'
  | 'llm'
  | 'planning'
  | 'unknown';

export type AgentStepStatus = 'running' | 'done' | 'failed' | 'pending';

export interface AgentStep {
  id: string;
  type: AgentStepType;
  title: string;
  status: AgentStepStatus;
  timestamp: number;
  payload?: Record<string, any>;
}

export type DetailContext =
  | 'dashboard'
  | 'task-detail'
  | 'file-preview'
  | 'tool-result'
  | 'entity-card';
```

Create `web/src/app/workspaces/detail/parse-agent-steps.ts`:

```typescript
import type { AgentStep, AgentStepStatus, AgentStepType } from './agent-types';

const TYPE_LABELS: Record<string, string> = {
  task_created: 'Task created',
  context_loaded: 'Context loaded',
  tool_call: 'Tool call',
  intervention_triggered: 'Intervention triggered',
  artifact_produced: 'Artifact produced',
  delivery_sent: 'Delivery sent',
  asset_referenced: 'Asset referenced',
  llm: 'LLM',
  planning: 'Planning',
};

function normalizeStatus(input?: string): AgentStepStatus {
  const s = String(input || '').toLowerCase();
  if (s === 'executing' || s === 'running' || s === 'pending_trigger' || s === 'awaiting_human') return 'running';
  if (s === 'failed' || s === 'blocked') return 'failed';
  if (s === 'complete' || s === 'finished' || s === 'done' || s === 'delivered' || s === 'closed') return 'done';
  return 'pending';
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function parseAgentSteps(vis: unknown): AgentStep | null {
  if (!vis || typeof vis !== 'object') return null;
  const v = vis as Record<string, any>;
  const payload = v.payload || {};

  if (v.type === 'step_list' && Array.isArray(payload.steps) && payload.steps.length > 0) {
    const step = payload.steps[payload.steps.length - 1];
    return {
      id: makeId(),
      type: 'tool_call',
      title: step.tool_name || step.name || 'Tool call',
      status: normalizeStatus(step.status),
      timestamp: Date.now(),
      payload: step,
    };
  }

  const allowedTypes: AgentStepType[] = [
    'task_created',
    'context_loaded',
    'intervention_triggered',
    'artifact_produced',
    'delivery_sent',
    'asset_referenced',
  ];
  if (allowedTypes.includes(v.type)) {
    return {
      id: makeId(),
      type: v.type,
      title: TYPE_LABELS[v.type] || v.type,
      status: normalizeStatus(payload.status) || 'done',
      timestamp: Date.now(),
      payload,
    };
  }

  return null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npm test -- parse-agent-steps
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/workspaces/detail/agent-types.ts \
  web/src/app/workspaces/detail/parse-agent-steps.ts \
  web/src/app/workspaces/detail/__tests__/parse-agent-steps.test.ts
git commit -m "feat(web): add AgentStep parser and types"
```

---

### Task 3: Create use-scene-agent-chat hook

**Files:**
- Create: `web/src/app/workspaces/detail/use-scene-agent-chat.ts`

**Interfaces:**
- Consumes: `useChat` from `@/hooks/use-chat`, `parseAgentSteps` from Task 2.
- Produces: `useSceneAgentChat({ convUid, appCode })` returning `{ steps, loading, error, send, abort, clearSteps }`.

- [ ] **Step 1: Implement the hook**

Create `web/src/app/workspaces/detail/use-scene-agent-chat.ts`:

```typescript
import { useCallback, useRef, useState } from 'react';
import useChat from '@/hooks/use-chat';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { parseAgentSteps } from './parse-agent-steps';

interface UseSceneAgentChatOptions {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
}

interface UseSceneAgentChatResult {
  steps: AgentStep[];
  loading: boolean;
  error: string | null;
  send: (text: string) => void;
  abort: () => void;
  clearSteps: () => void;
}

const MAX_RECENT_STEPS = 8;

export function useSceneAgentChat({
  convUid,
  appCode,
  workspaceId,
  taskId,
  onWorkspaceEvent,
}: UseSceneAgentChatOptions): UseSceneAgentChatResult {
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { chat } = useChat({ app_code: appCode || '' });

  const appendStep = useCallback((step: AgentStep) => {
    setSteps((prev) => {
      const next = [...prev, step];
      if (next.length > MAX_RECENT_STEPS) next.shift();
      return next;
    });
  }, []);

  const clearSteps = useCallback(() => setSteps([]), []);

  const send = useCallback(
    (text: string) => {
      if (!convUid || !text.trim()) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setError(null);

      chat({
        ctrl,
        data: {
          conv_uid: convUid,
          user_input: text.trim(),
          workspace_id: workspaceId,
          task_id: taskId,
        },
        onMessage: (message: any) => {
          if (message && typeof message === 'object') {
            const step = parseAgentSteps(message);
            if (step) appendStep(step);
          }
        },
        onDone: () => setLoading(false),
        onClose: () => setLoading(false),
        onError: (content: string) => {
          setError(content || 'Agent error');
          setLoading(false);
        },
        onWorkspaceEvent,
      });
    },
    [convUid, appCode, workspaceId, taskId, chat, appendStep, onWorkspaceEvent]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, []);

  return { steps, loading, error, send, abort, clearSteps };
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors from the new file.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/use-scene-agent-chat.ts
git commit -m "feat(web): add useSceneAgentChat hook"
```

---

### Task 4: Create AgentChatInput component

**Files:**
- Create: `web/src/app/workspaces/detail/agent-chat-input.tsx`

**Interfaces:**
- Consumes: `onSend(text: string): void`, `loading?: boolean`, `disabled?: boolean`. Exposes `focus()` via `forwardRef`.
- Produces: `<AgentChatInput />` UI.

- [ ] **Step 1: Implement the component**

Create `web/src/app/workspaces/detail/agent-chat-input.tsx`:

```typescript
'use client';

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Button, Input } from 'antd';
import { SendOutlined } from '@ant-design/icons';

export interface AgentChatInputProps {
  placeholder?: string;
  onSend: (text: string) => void;
  loading?: boolean;
  disabled?: boolean;
}

export interface AgentChatInputHandle {
  focus: () => void;
}

export const AgentChatInput = forwardRef<AgentChatInputHandle, AgentChatInputProps>(function AgentChatInput(
  { placeholder = '输入指令给 Agent...', onSend, loading, disabled },
  ref
) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
  }));

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="ws-agent-chat-input">
      <Input.TextArea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoSize={{ minRows: 1, maxRows: 6 }}
        disabled={disabled || loading}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={handleSend}
        loading={loading}
        disabled={!text.trim() || disabled || loading}
      />
    </div>
  );
});
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/agent-chat-input.tsx
git commit -m "feat(web): add AgentChatInput component"
```

---

### Task 5: Create AgentProcessPanel component

**Files:**
- Create: `web/src/app/workspaces/detail/agent-process-panel.tsx`

**Interfaces:**
- Consumes: `steps: AgentStep[]`, `loading?: boolean`, `onStepClick?: (step: AgentStep) => void`.
- Produces: `<AgentProcessPanel />` UI.

- [ ] **Step 1: Implement the component**

Create `web/src/app/workspaces/detail/agent-process-panel.tsx`:

```typescript
'use client';

import { CheckCircleOutlined, ExclamationCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import type { AgentStep } from './agent-types';

export interface AgentProcessPanelProps {
  steps: AgentStep[];
  loading?: boolean;
  onStepClick?: (step: AgentStep) => void;
}

const statusIcon = (status: AgentStep['status']) => {
  switch (status) {
    case 'done':
      return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    case 'failed':
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
    case 'running':
      return <LoadingOutlined style={{ color: '#1677ff' }} />;
    default:
      return <span className="ws-agent-step-dot" />;
  }
};

export function AgentProcessPanel({ steps, loading, onStepClick }: AgentProcessPanelProps) {
  return (
    <div className="ws-agent-process-panel">
      <div className="ws-agent-process-header">Agent 工作过程</div>
      {steps.length === 0 && !loading && (
        <div className="ws-agent-process-empty">Agent 就绪，输入指令开始工作</div>
      )}
      <div className="ws-agent-step-list">
        {steps.map((step) => (
          <div
            key={step.id}
            className={`ws-agent-step ws-agent-step--${step.status}`}
            onClick={() => onStepClick?.(step)}
            role={onStepClick ? 'button' : undefined}
            tabIndex={onStepClick ? 0 : undefined}
            onKeyDown={(e) => {
              if (onStepClick && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                onStepClick(step);
              }
            }}
          >
            <span className="ws-agent-step-icon">{statusIcon(step.status)}</span>
            <span className="ws-agent-step-title">{step.title}</span>
          </div>
        ))}
        {loading && (
          <div className="ws-agent-step ws-agent-step--running">
            <span className="ws-agent-step-icon"><LoadingOutlined style={{ color: '#1677ff' }} /></span>
            <span className="ws-agent-step-title">Agent 思考中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/agent-process-panel.tsx
git commit -m "feat(web): add AgentProcessPanel component"
```

---

### Task 6: Create AgentWorkspace component

**Files:**
- Create: `web/src/app/workspaces/detail/agent-workspace.tsx`

**Interfaces:**
- Consumes: `convUid?: string`, `appCode?: string`, `workspaceId?: number | string`, `taskId?: number | string`, `autoFocus?: boolean`, `onFocusHandled?: () => void`, `onStepClick?: (step: AgentStep) => void`, `onWorkspaceEvent?: (event: WorkspaceEvent) => void`.
- Produces: `<AgentWorkspace />` composing `AgentProcessPanel` + `AgentChatInput`.

- [ ] **Step 1: Implement the component**

Create `web/src/app/workspaces/detail/agent-workspace.tsx`:

```typescript
'use client';

import { useEffect, useRef } from 'react';
import { Alert, Spin } from 'antd';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { AgentChatInput, AgentChatInputHandle } from './agent-chat-input';
import { AgentProcessPanel } from './agent-process-panel';
import { useSceneAgentChat } from './use-scene-agent-chat';

export interface AgentWorkspaceProps {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  autoFocus?: boolean;
  onFocusHandled?: () => void;
  onStepClick?: (step: AgentStep) => void;
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
}

export function AgentWorkspace({
  convUid,
  appCode,
  workspaceId,
  taskId,
  autoFocus,
  onFocusHandled,
  onStepClick,
  onWorkspaceEvent,
}: AgentWorkspaceProps) {
  const inputRef = useRef<AgentChatInputHandle>(null);
  const { steps, loading, error, send, abort, clearSteps } = useSceneAgentChat({
    convUid,
    appCode,
    workspaceId,
    taskId,
    onWorkspaceEvent,
  });

  useEffect(() => {
    clearSteps();
  }, [convUid, clearSteps]);

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus();
      onFocusHandled?.();
    }
  }, [autoFocus, onFocusHandled]);

  return (
    <div className="ws-agent-workspace">
      <div className="ws-agent-workspace__process">
        {error && <Alert message={error} type="error" showIcon className="ws-agent-workspace__error" />}
        {!convUid ? (
          <div className="ws-agent-workspace__loading"><Spin /></div>
        ) : (
          <AgentProcessPanel steps={steps} loading={loading} onStepClick={onStepClick} />
        )}
      </div>
      <div className="ws-agent-workspace__input">
        <AgentChatInput ref={inputRef} onSend={send} loading={loading} disabled={!convUid} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/agent-workspace.tsx
git commit -m "feat(web): add AgentWorkspace component"
```

---

### Task 7: Create SceneTaskRail component

**Files:**
- Create: `web/src/app/workspaces/detail/scene-task-rail.tsx`

**Interfaces:**
- Consumes: `tasks: any[]`, `interventions: any[]`, `activeTaskId?: number | null`, `onPreview(item): void`, `onEnterConversation(taskId: number): void`.
- Produces: `<SceneTaskRail />` UI.

- [ ] **Step 1: Implement the component**

Create `web/src/app/workspaces/detail/scene-task-rail.tsx`:

```typescript
'use client';

import { useMemo, useState } from 'react';
import { Button, Input, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

export interface SceneTaskRailProps {
  tasks: any[];
  interventions: any[];
  activeTaskId?: number | null;
  onPreview: (item: any, kind: 'task' | 'intervention') => void;
  onEnterConversation: (taskId: number) => void;
}

interface MixedItem {
  id: number;
  kind: 'task' | 'intervention';
  title: string;
  status: string;
  updatedAt: string;
  raw: any;
}

const STATUS_COLORS: Record<string, string> = {
  running: 'blue',
  awaiting_human: 'orange',
  delivered: 'green',
  failed: 'red',
  pending_trigger: 'default',
  closed: 'default',
};

export function SceneTaskRail({
  tasks,
  interventions,
  activeTaskId,
  onPreview,
  onEnterConversation,
}: SceneTaskRailProps) {
  const [filter, setFilter] = useState('');

  const items = useMemo<MixedItem[]>(() => {
    const mappedTasks: MixedItem[] = (tasks || []).map((t) => ({
      id: t.id,
      kind: 'task',
      title: t.title || `task_${t.id}`,
      status: t.status || 'unknown',
      updatedAt: t.updated_at || t.created_at || new Date().toISOString(),
      raw: t,
    }));
    const mappedInterventions: MixedItem[] = (interventions || []).map((i) => ({
      id: i.id,
      kind: 'intervention',
      title: i.question?.title || `intervention_${i.id}`,
      status: i.status || 'requested',
      updatedAt: i.updated_at || i.created_at || new Date().toISOString(),
      raw: i,
    }));
    return [...mappedTasks, ...mappedInterventions].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    );
  }, [tasks, interventions]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.title.toLowerCase().includes(q) || String(i.id).includes(q));
  }, [items, filter]);

  return (
    <div className="ws-scene-task-rail">
      <div className="ws-scene-task-rail__header">任务与介入</div>
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索任务、介入"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="ws-scene-task-rail__search"
      />
      <div className="ws-scene-task-rail__list">
        {filtered.length === 0 && <div className="ws-scene-task-rail__empty">暂无任务或介入请求</div>}
        {filtered.map((item) => (
          <div
            key={`${item.kind}-${item.id}`}
            className={`ws-scene-task-rail__item${activeTaskId === item.id && item.kind === 'task' ? ' ws-scene-task-rail__item--active' : ''}`}
            onClick={() => onPreview(item.raw, item.kind)}
          >
            <div className="ws-scene-task-rail__item-top">
              <Tag color={STATUS_COLORS[item.status] || 'default'}>{item.status}</Tag>
              <span className="ws-scene-task-rail__time">{dayjs(item.updatedAt).format('MM-DD HH:mm')}</span>
            </div>
            <div className="ws-scene-task-rail__title">{item.title}</div>
            {item.kind === 'task' && (
              <Button
                size="small"
                type="link"
                className="ws-scene-task-rail__enter"
                onClick={(e) => {
                  e.stopPropagation();
                  onEnterConversation(item.id);
                }}
              >
                进入对话
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/scene-task-rail.tsx
git commit -m "feat(web): add SceneTaskRail component"
```

---

### Task 8: Create SceneSpace component

**Files:**
- Create: `web/src/app/workspaces/detail/scene-space.tsx`
- Modify: `web/src/app/workspaces/detail/lobby.tsx` (if needed for reuse)

**Interfaces:**
- Consumes: `context: DetailContext`, `previewItem?: any`, `workspaceId: number`, `workspaceCode: string`, `onBack(): void`, `onFocusAgentInput?: () => void`, `onSelectTask?: (taskId: number) => void`.
- Produces: `<SceneSpace />` rendering dashboard, task detail, file preview, tool result, or entity card.

- [ ] **Step 1: Implement the component**

Create `web/src/app/workspaces/detail/scene-space.tsx`:

```typescript
'use client';

import { Button, Card, Spin, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, getTaskInfo, listArtifacts, listDeliveries } from '@/client/api';
import { Lobby } from './lobby';
import type { DetailContext } from './agent-types';

export interface SceneSpaceProps {
  context: DetailContext;
  previewItem?: any;
  workspaceId: number;
  workspaceCode: string;
  onBack: () => void;
  onFocusAgentInput?: () => void;
  onSelectTask?: (taskId: number) => void;
}

export function SceneSpace({
  context,
  previewItem,
  workspaceId,
  workspaceCode,
  onBack,
  onFocusAgentInput,
  onSelectTask,
}: SceneSpaceProps) {
  const taskId = context === 'task-detail' && previewItem?.id ? previewItem.id : undefined;

  const { data: taskRes, loading: taskLoading } = useRequest(
    async () => (taskId ? apiInterceptors(getTaskInfo(taskId)) : null),
    { refreshDeps: [taskId] }
  );
  const task = taskRes?.[1];

  const { data: artifactsRes } = useRequest(
    async () => (taskId ? apiInterceptors(listArtifacts({ task_id: taskId })) : null),
    { refreshDeps: [taskId] }
  );
  const artifacts = artifactsRes?.[1] || [];

  if (context === 'dashboard') {
    return (
      <div className="ws-scene-space ws-scene-space--dashboard">
        <Lobby
          workspaceId={workspaceId}
          workspaceCode={workspaceCode}
          onSelectTask={onSelectTask || (() => {})}
          onSendFirstMessage={onFocusAgentInput || (() => {})}
        />
      </div>
    );
  }

  return (
    <div className="ws-scene-space">
      <div className="ws-scene-space__header">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack} size="small">
          返回 dashboard
        </Button>
      </div>
      {context === 'task-detail' && (
        <div className="ws-scene-space__body">
          {taskLoading && <Spin />}
          {!taskLoading && task && (
            <Card title={task.title || `Task ${task.id}`}>
              <p><Tag>{task.status}</Tag></p>
              <p>触发源: {task.triggered_by || '—'}</p>
              <p>创建时间: {task.created_at || '—'}</p>
              <p>更新时间: {task.updated_at || '—'}</p>
              {artifacts.length > 0 && (
                <div>
                  <strong>交付物:</strong>
                  {artifacts.map((a: any) => (
                    <div key={a.id}>{a.title || `artifact_${a.id}`} <Tag>{a.type}</Tag></div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
      {context === 'file-preview' && (
        <div className="ws-scene-space__body">
          <Card title="文件预览">
            <pre>{JSON.stringify(previewItem?.payload || previewItem, null, 2)}</pre>
          </Card>
        </div>
      )}
      {context === 'tool-result' && (
        <div className="ws-scene-space__body">
          <Card title="工具结果">
            <pre>{JSON.stringify(previewItem?.payload || previewItem, null, 2)}</pre>
          </Card>
        </div>
      )}
      {context === 'entity-card' && (
        <div className="ws-scene-space__body">
          <Card title="实体信息">
            <pre>{JSON.stringify(previewItem?.payload || previewItem, null, 2)}</pre>
          </Card>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/scene-space.tsx
git commit -m "feat(web): add SceneSpace context-aware renderer"
```

---

### Task 9: Create SceneWorkspaceShell

**Files:**
- Create: `web/src/app/workspaces/detail/scene-workspace-shell.tsx`

**Interfaces:**
- Consumes: workspace data + lists from `client.tsx`.
- Produces: 3-column layout with `SceneTaskRail`, `SceneSpace`, `AgentWorkspace`.

- [ ] **Step 1: Implement the shell**

Create `web/src/app/workspaces/detail/scene-workspace-shell.tsx`:

```typescript
'use client';

import { useEffect, useState } from 'react';
import { apiInterceptors, getTaskInfo } from '@/client/api';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep, DetailContext } from './agent-types';
import { AgentWorkspace } from './agent-workspace';
import { SceneSpace } from './scene-space';
import { SceneTaskRail } from './scene-task-rail';

interface SceneWorkspaceShellProps {
  workspace: any;
  tasks: any[];
  interventions: any[];
  workspaceConvUid: string;
  appCode: string;
}

export function SceneWorkspaceShell({
  workspace,
  tasks,
  interventions,
  workspaceConvUid,
  appCode,
}: SceneWorkspaceShellProps) {
  const workspaceId = workspace?.id;
  const [previewItem, setPreviewItem] = useState<any>(null);
  const [detailContext, setDetailContext] = useState<DetailContext>('dashboard');
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const [taskConvUid, setTaskConvUid] = useState<string>('');
  const [focusAgentInput, setFocusAgentInput] = useState(false);

  useEffect(() => {
    if (!activeTaskId) {
      setTaskConvUid('');
      return;
    }
    let cancelled = false;
    apiInterceptors(getTaskInfo(activeTaskId)).then(([, res]) => {
      if (!cancelled) setTaskConvUid(res?.conv_session_id || '');
    });
    return () => {
      cancelled = true;
    };
  }, [activeTaskId]);

  const handlePreview = (item: any, kind: 'task' | 'intervention') => {
    setPreviewItem(item);
    setDetailContext(kind === 'task' ? 'task-detail' : 'entity-card');
  };

  const handleEnterConversation = (taskId: number) => {
    setActiveTaskId(taskId);
    const task = tasks.find((t) => t.id === taskId);
    if (task) {
      setPreviewItem(task);
      setDetailContext('task-detail');
    }
  };

  const handleBackToDashboard = () => {
    setDetailContext('dashboard');
    setPreviewItem(null);
  };

  const handleStepClick = (step: AgentStep) => {
    if (step.type === 'tool_call') {
      setPreviewItem(step);
      setDetailContext('tool-result');
    } else if (step.payload?.file_id || step.payload?.file_name) {
      setPreviewItem(step);
      setDetailContext('file-preview');
    } else if (step.payload?.task_id || step.payload?.asset_id) {
      setPreviewItem(step);
      setDetailContext('entity-card');
    }
  };

  const handleWorkspaceEvent = (event: WorkspaceEvent) => {
    if (event.type === 'artifact_produced' && event.payload?.file_id) {
      setPreviewItem(event);
      setDetailContext('file-preview');
    }
  };

  const rightConvUid = activeTaskId ? taskConvUid : workspaceConvUid;
  const rightTaskId = activeTaskId ? activeTaskId : undefined;

  return (
    <div className="ws-scene-shell">
      <div className="ws-scene-shell__rail">
        <SceneTaskRail
          tasks={tasks}
          interventions={interventions}
          activeTaskId={activeTaskId}
          onPreview={handlePreview}
          onEnterConversation={handleEnterConversation}
        />
      </div>
      <div className="ws-scene-shell__space">
        <SceneSpace
          context={detailContext}
          previewItem={previewItem}
          workspaceId={workspaceId}
          workspaceCode={workspace?.workspace_code}
          onBack={handleBackToDashboard}
          onFocusAgentInput={() => setFocusAgentInput(true)}
          onSelectTask={(taskId) => {
            const task = tasks.find((t) => t.id === taskId);
            if (task) handlePreview(task, 'task');
          }}
        />
      </div>
      <div className="ws-scene-shell__agent">
        {activeTaskId && (
          <div className="ws-scene-shell__agent-mode">
            <span>任务对话: {activeTaskId}</span>
            <button onClick={() => setActiveTaskId(null)}>退出任务对话</button>
          </div>
        )}
        <AgentWorkspace
          convUid={rightConvUid}
          appCode={appCode}
          workspaceId={workspaceId}
          taskId={rightTaskId}
          autoFocus={focusAgentInput}
          onFocusHandled={() => setFocusAgentInput(false)}
          onStepClick={handleStepClick}
          onWorkspaceEvent={handleWorkspaceEvent}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/scene-workspace-shell.tsx
git commit -m "feat(web): add SceneWorkspaceShell"
```

---

### Task 10: Refactor WorkspaceDetailPage

**Files:**
- Modify: `web/src/app/workspaces/detail/client.tsx`

**Interfaces:**
- Consumes: existing API functions, `SceneWorkspaceShell`.
- Produces: simplified `WorkspaceDetailPage`.

- [ ] **Step 1: Replace the console body with SceneWorkspaceShell**

Edit `web/src/app/workspaces/detail/client.tsx`:

1. Remove imports for `Lobby`, `Workbench`, `ChatSession`, `ChatSessionHandle`, `ConversationSwitcher`, and all icons used only by `SignalChain` / `Loop`.
2. Remove `SignalChain` component, `Loop` strip JSX, `viewMode` state, `selectedTaskId`, `pendingMessage`, `chatSessionRef`, `taskRes`, `taskConvUid`, `enterChat`, `enterWorkbench`, `backToLobby`, and the `workspace:view-task` listener.
3. Keep workspace data fetching and `convUid` loading.
4. Replace the console div with `SceneWorkspaceShell`.

Simplified `client.tsx` should look like:

```typescript
'use client';

import {
  apiInterceptors, getWorkspaceInfo, listTasks, listInterventions,
  createConversation, getCurrentConversation, setCurrentConversation,
  linkConversation,
} from '@/client/api';
import { Button, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ThunderboltOutlined,
  FileTextOutlined,
  DeliveredProcedureOutlined,
  WarningOutlined,
  SettingOutlined,
  ClockCircleOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { SceneWorkspaceShell } from './scene-workspace-shell';
import '../workspaces.css';

export default function WorkspaceDetailPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [convUid, setConvUid] = useState<string>('');

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const workspaceId = ws?.id;
  const appCode = ws?.default_agent_app_code || 'main';

  useRequest(
    async () => {
      const [, current] = await apiInterceptors(getCurrentConversation(workspaceId));
      if (current?.conv_uid) {
        setConvUid(current.conv_uid);
        return;
      }
      const [, newConv] = await apiInterceptors(createConversation({}));
      if (!newConv?.conv_uid) return;
      await apiInterceptors(
        linkConversation({ workspace_id: workspaceId, conv_uid: newConv.conv_uid, user_id: undefined })
      );
      await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
      setConvUid(newConv.conv_uid);
    },
    { ready: !!workspaceId }
  );

  const { data: tasks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listTasks({ workspace_id: workspaceId, limit: 50 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: interventions } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listInterventions({
      workspace_id: workspaceId, status: 'requested', limit: 20,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  if (!searchParams || wsLoading) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content ws-page-content--fluid" style={{ display: 'flex', justifyContent: 'center', padding: '120px 24px' }}>
          <Spin size="large" />
        </div>
      </div>
    );
  }

  if (!ws) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content ws-page-content--fluid">
          <div className="ws-empty">
            <div className="ws-empty-icon"><AppstoreOutlined /></div>
            <p className="ws-empty-title">Workspace not found</p>
            <p className="ws-empty-desc">This workspace may have been archived or you lack access.</p>
            <Link href="/workspaces"><Button>Back to workspaces</Button></Link>
          </div>
        </div>
      </div>
    );
  }

  if (!workspaceId) {
    return null;
  }

  const scenario = ws.scenario_type || ws.type || 'scenario';
  const reviewCount = (interventions || []).length;

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content ws-page-content--fluid" style={{ paddingTop: 16, paddingBottom: 16 }}>
        <div className="ws-console-header">
          <div className="ws-console-header-left">
            <div className="ws-console-avatar"><AppstoreOutlined /></div>
            <div style={{ minWidth: 0 }}>
              <h2 className="ws-console-title">{ws.name}</h2>
              <div className="ws-console-sub">
                {ws.workspace_code} · {scenario}
              </div>
            </div>
          </div>
          <nav className="ws-console-nav" aria-label="Workspace navigation">
            <Link href={`/workspaces/detail/triggers?id=${workspaceCode}`} className="ws-console-nav-link">
              <ClockCircleOutlined />{t('workspaces.triggers') || 'Triggers'}
            </Link>
            <Link href={`/workspaces/detail/tasks?id=${workspaceCode}`} className="ws-console-nav-link">
              <ThunderboltOutlined />{t('workspaces.tasks') || 'Tasks'}
            </Link>
            <Link href={`/workspaces/detail/deliveries?id=${workspaceCode}`} className="ws-console-nav-link ws-console-nav-link--accent">
              <DeliveredProcedureOutlined />{t('workspaces.deliveries') || 'Delivery Space'}
            </Link>
            <Link href={`/workspaces/detail/artifacts?id=${workspaceCode}`} className="ws-console-nav-link">
              <FileTextOutlined />{t('workspaces.artifacts') || 'Artifacts'}
            </Link>
            <Link href={`/workspaces/detail/interventions?id=${workspaceCode}`} className={`ws-console-nav-link${reviewCount > 0 ? ' ws-console-nav-link--attention' : ''}`}>
              <WarningOutlined />{t('workspaces.interventions') || 'Interventions'}
              {reviewCount > 0 && <span style={{ fontWeight: 700 }}>{reviewCount}</span>}
            </Link>
            <Link href={`/workspaces/detail/settings?id=${workspaceCode}`} className="ws-console-nav-link">
              <SettingOutlined />{t('workspaces.settings') || 'Settings'}
            </Link>
          </nav>
        </div>

        <SceneWorkspaceShell
          workspace={ws}
          tasks={tasks || []}
          interventions={interventions || []}
          workspaceConvUid={convUid}
          appCode={appCode}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/client.tsx
git commit -m "refactor(web): simplify WorkspaceDetailPage to use SceneWorkspaceShell"
```

---

### Task 11: Add 3-column layout CSS

**Files:**
- Create: `web/src/app/workspaces/detail/scene-workspace.css`
- Modify: `web/src/app/workspaces/detail/scene-workspace-shell.tsx` (import CSS)

**Interfaces:**
- Provides layout styling for the shell and panels.

- [ ] **Step 1: Create CSS file**

Create `web/src/app/workspaces/detail/scene-workspace.css`:

```css
.ws-scene-shell {
  display: grid;
  grid-template-columns: 280px 1fr 420px;
  gap: 16px;
  height: calc(100vh - 140px);
  min-height: 600px;
  overflow: hidden;
}

.ws-scene-shell__rail,
.ws-scene-shell__space,
.ws-scene-shell__agent {
  background: var(--ws-surface);
  border: 1px solid var(--ws-border);
  border-radius: var(--ws-radius);
  box-shadow: var(--ws-shadow-sm);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ws-scene-shell__space {
  overflow-y: auto;
}

.ws-scene-shell__agent {
  display: flex;
  flex-direction: column;
}

.ws-scene-shell__agent-mode {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--ws-border);
  font-size: 12px;
  color: var(--ws-ink-2);
}

.ws-agent-workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.ws-agent-workspace__process {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}

.ws-agent-workspace__input {
  border-top: 1px solid var(--ws-border);
  padding: 12px;
  flex-shrink: 0;
}

.ws-agent-chat-input {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.ws-agent-chat-input .ant-input {
  resize: none;
}

.ws-agent-process-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ws-agent-process-header {
  font-weight: 600;
  font-size: 13px;
  color: var(--ws-ink);
  margin-bottom: 4px;
}

.ws-agent-process-empty {
  font-size: 12px;
  color: var(--ws-ink-3);
  padding: 24px 0;
  text-align: center;
}

.ws-agent-step-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ws-agent-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--ws-radius-sm);
  background: var(--ws-bg);
  font-size: 12px;
  color: var(--ws-ink);
  cursor: default;
}

.ws-agent-step[role='button'] {
  cursor: pointer;
}

.ws-agent-step[role='button']:hover {
  background: var(--ws-accent-light);
}

.ws-agent-step--running {
  background: rgba(var(--ws-accent-rgb), 0.08);
}

.ws-agent-step-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
}

.ws-agent-step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ws-ink-3);
}

.ws-scene-task-rail {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.ws-scene-task-rail__header {
  padding: 12px 14px;
  font-weight: 600;
  font-size: 13px;
  border-bottom: 1px solid var(--ws-border);
}

.ws-scene-task-rail__search {
  margin: 10px 12px;
}

.ws-scene-task-rail__list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 12px;
}

.ws-scene-task-rail__empty {
  font-size: 12px;
  color: var(--ws-ink-3);
  text-align: center;
  padding: 24px 0;
}

.ws-scene-task-rail__item {
  padding: 10px 12px;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--ws-border);
  margin-bottom: 8px;
  cursor: pointer;
  transition: all var(--ws-transition);
}

.ws-scene-task-rail__item:hover,
.ws-scene-task-rail__item--active {
  border-color: var(--ws-accent);
  background: var(--ws-accent-light);
}

.ws-scene-task-rail__item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.ws-scene-task-rail__time {
  font-size: 11px;
  color: var(--ws-ink-3);
}

.ws-scene-task-rail__title {
  font-size: 12px;
  font-weight: 500;
  color: var(--ws-ink);
  line-height: 1.4;
  margin-bottom: 4px;
}

.ws-scene-task-rail__enter {
  padding: 0;
  font-size: 12px;
}

.ws-scene-space {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.ws-scene-space--dashboard {
  overflow-y: auto;
}

.ws-scene-space__header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--ws-border);
  position: sticky;
  top: 0;
  background: var(--ws-surface);
  z-index: 1;
}

.ws-scene-space__body {
  flex: 1;
  padding: 14px;
  overflow-y: auto;
}

@media (max-width: 1280px) {
  .ws-scene-shell {
    grid-template-columns: 240px 1fr 360px;
  }
}

@media (max-width: 1024px) {
  .ws-scene-shell {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
  }
  .ws-scene-shell__rail {
    max-height: 240px;
  }
  .ws-scene-shell__agent {
    max-height: 420px;
  }
}
```

- [ ] **Step 2: Import CSS in shell**

Add to top of `web/src/app/workspaces/detail/scene-workspace-shell.tsx`:

```typescript
import './scene-workspace.css';
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/workspaces/detail/scene-workspace.css \
  web/src/app/workspaces/detail/scene-workspace-shell.tsx
git commit -m "feat(web): add scene workspace layout CSS"
```

---

### Task 12: Manual integration verification

**Files:**
- All modified files.

**Interfaces:**
- End-to-end behavior of the redesigned workspace detail page.

- [ ] **Step 1: Start dev server**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npm run dev
```

- [ ] **Step 2: Open a workspace detail page**

Navigate to `http://localhost:3000/workspaces/detail?id=<workspace_code>`.

Verify:
- 3-column layout renders.
- Header shows workspace title and nav links; no conversation switcher.
- Left rail lists tasks and interventions; search filters the list.
- Middle shows scenario dashboard by default.
- Right panel shows empty Agent process state and an input box.

- [ ] **Step 3: Test left-rail interactions**

- Click a task body → middle switches to task detail; right stays workspace-level.
- Click “进入对话” on a task → right panel switches to task mode; top shows task mode bar.
- Click “退出任务对话” → right returns to workspace mode.

- [ ] **Step 4: Test Agent interaction**

- Type a message in the right input and send.
- Verify `AgentProcessPanel` shows streaming steps.
- Click a tool step → middle switches to tool-result view.

- [ ] **Step 5: Run lint**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npm run lint
```

Expected: no errors in modified files.

- [ ] **Step 6: Run tests**

```bash
cd /Users/tuyang/GitHub/OpenDerisk/web
npm test
```

Expected: all tests pass.

- [ ] **Step 7: Commit any final fixes**

```bash
git add -A
git commit -m "fix(web): integration polish for scene workspace"
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Implementing task |
|------------------|-------------------|
| 3-column layout | Task 9 + Task 11 |
| Right panel: input + recent steps, no history | Task 3, 4, 5, 6 |
| Left rail: mixed task/intervention feed, two click modes | Task 7 |
| Middle space: dashboard default + context-aware detail | Task 8 |
| Agent step → middle detail linkage | Task 5 + Task 9 |
| Task “进入对话” enters task Agent mode | Task 7 + Task 9 |
| Remove conversation switcher, SignalChain, Loop strip | Task 10 |
| Absorb status counts into dashboard | Task 8 (via `Lobby`) |

### Placeholder scan

- No TBD/TODO/fill-in-later in steps.
- Each code step includes actual code.
- Each verification step includes exact command and expected output.

### Type consistency

- `AgentStep` defined in Task 2 and used in Tasks 3, 5, 6, 9.
- `DetailContext` defined in Task 2 and used in Tasks 8, 9.
- `parseAgentSteps` signature consistent across Task 2 tests and Task 3 usage.

### Gaps

- `SceneSpace` file/tool/entity preview cards currently render JSON fallback. A follow-up task can replace these with real renderers once file/tool APIs are available.
- Responsive behavior for very narrow screens is basic; refine based on manual testing.
