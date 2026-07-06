# 场景空间三种工作状态实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让场景空间 `/workspaces/detail` 页面的三种工作状态（S0 大厅概览 / S1 大厅对话 / S2 任务工作台）完整可用，并对齐产品形态终态。

**Architecture:** 在前端新增 `viewMode` 三态管理；大厅默认展示概览，首次输入后切到完整对话视图；任务工作台改为上下分区（进展 / 交付物 / 折叠协作对话 / 执行轨迹）。后端改造 `start_task` Agent 工具，使其真正创建 Task 并通过 SSE 发送 `task_created` 事件，前端在消息流中渲染任务卡片。

**Tech Stack:** Next.js / React / TypeScript / Ant Design（前端），Python / FastAPI（后端）。

## Global Constraints

- 不动 HomeChat (`/`) / Application Builder (`/application/app/`) / Agent / Skill / MCP / Knowledge Vault / DataResource。
- 场景空间前端自治，不复用 HomeChat 组件做主体视图。
- 不破坏现有 `/chat` 页面行为。
- 所有写操作后端先走现有 Service 层，不直接操作 DAO。
- TypeScript 严格模式通过；后端单测通过。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py` | 后端：`start_task` 真正创建 Task，并通过 callback 发送 workspace event。 |
| `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py` | 后端：为 write tools 注入 event callback。 |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | 后端：在 SSE 生成器与子 Agent 之间桥接 workspace event queue。 |
| `web/src/components/chat/task-created-card.tsx` | 前端：新建，消息流中的任务卡片组件。 |
| `web/src/components/chat/chat-content-container.tsx` | 前端：识别 `task_created` 事件并渲染任务卡片。 |
| `web/src/app/workspaces/detail/lobby-chat-input.tsx` | 前端：新建，大厅底部轻量输入框。 |
| `web/src/app/workspaces/detail/client.tsx` | 前端：新增 `viewMode` 三态管理。 |
| `web/src/app/workspaces/detail/lobby.tsx` | 前端：删除重复标题，快捷发起真实创建任务，底部改用 `LobbyChatInput`。 |
| `web/src/app/workspaces/detail/workbench.tsx` | 前端：改为上下分区布局，协作对话区用完整 `ChatSession`。 |
| `web/src/app/workspaces/detail/lobby.css` | 前端：调整大厅布局。 |
| `web/src/app/workspaces/detail/workbench.css` | 前端：调整工作台上下分区样式。 |

---

### Task 1: 后端 —— `start_task` 真正创建 Task 并发送 `task_created` 事件

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py`
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py`
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py`
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`
- Test: `packages/derisk-serve/tests/workspace/agent_tools/test_write_tools.py`

**Interfaces:**
- Consumes: `TaskService.create` API；`format_workspace_event` helper。
- Produces: `start_task` tool 返回 `{"task_id": int, "status": "running"}`；SSE 中 yield `{"vis": {"type": "task_created", "payload": {...}}}`。

- [ ] **Step 1: 新建任务创建辅助模块**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py
from typing import Any, Dict, Optional


def create_task_from_tool(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    playbook_id: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """真正创建 Task，返回 task 元数据。"""
    from derisk_serve.task.api.schemas import TaskRequest
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME,
        TaskService,
    )
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )

    task_service: TaskService = system_app.get_component(
        TASK_SERVICE_COMPONENT_NAME, TaskService
    )
    playbook_service: PlaybookService = system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
    )

    playbook = None
    if playbook_id:
        playbook = playbook_service.get_by_id(playbook_id)

    request = TaskRequest(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        title=title or (playbook.name if playbook else "手动创建任务"),
        description=description or "",
        type="adhoc",
        triggered_by="manual",
        created_by_user_id=int(user_id) if user_id and user_id.isdigit() else None,
    )
    entity = task_service.create(request)
    return {
        "task_id": entity.id,
        "title": entity.title,
        "status": entity.status,
        "playbook_id": entity.playbook_id,
        "playbook_name": playbook.name if playbook else None,
        "triggered_by": entity.triggered_by,
    }
```

- [ ] **Step 2: 修改 write_tools.py，让 `start_task` 真正创建任务并通过 callback 发事件**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py
from typing import Callable, List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.workspace.agent_tools._task_creator import create_task_from_tool

WorkspaceEventCallback = Callable[[str, dict], None]


def build_write_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
    on_event: Optional[WorkspaceEventCallback] = None,
) -> List[FunctionTool]:
    def start_task(**kwargs):
        playbook_id = kwargs.get("playbook_id")
        title = kwargs.get("title")
        description = kwargs.get("description")
        result = create_task_from_tool(
            system_app,
            workspace_id=workspace_id,
            user_id=user_id,
            playbook_id=playbook_id,
            title=title,
            description=description,
        )
        if on_event:
            on_event("task_created", {
                "task_id": result["task_id"],
                "title": result["title"],
                "status": result["status"],
                "playbook_id": result["playbook_id"],
                "playbook_name": result["playbook_name"],
                "triggered_by": result["triggered_by"],
                "workspace_id": workspace_id,
            })
        return result

    specs = [
        ("start_task", "在当前空间下发起一个任务", start_task),
        ("close_task", "关闭指定任务", _make_close_task_tool),
        ("publish_asset", "将一个交付物沉淀为空间级 Asset", _make_publish_asset_tool),
        ("create_delivery", "创建一条投递记录", _make_create_delivery_tool),
        ("update_workspace", "更新空间基本信息", _make_update_workspace_tool),
    ]
    tools: List[FunctionTool] = []
    for name, desc, fn in specs:
        tools.append(FunctionTool(name=name, description=desc, func=fn, args_schema=None))
    return tools
```

> 注：`close_task` / `publish_asset` / `create_delivery` / `update_workspace` 保持创建 intervention 的安全行为，本次只改造 `start_task`。

- [ ] **Step 3: 修改 toolkit.py，传入 event callback**

```python
# packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py

def build_workspace_toolkit(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: Optional[str],
    task_id: Optional[int] = None,
    mode: str = "lobby",
    llm_config: Optional[LLMConfig] = None,
    on_event: Optional[Callable[[str, dict], None]] = None,
) -> Optional[WorkspaceControlAgent]:
    # ...
    if mode == "lobby":
        # ...
        write = build_write_tools(
            system_app, workspace_id, user_id, conv_uid, task_id=task_id, on_event=on_event
        )
        tools = layer1 + layer2_read + write
    elif mode == "workbench":
        # ...
        playbook_write = build_playbook_tools(
            system_app, workspace_id, user_id, conv_uid, task_id=task_id, on_event=on_event
        )
        tools = layer1 + layer3_read + playbook_write
    # ...
```

- [ ] **Step 4: 修改 agent_chat.py，桥接 event queue 到 SSE 生成器**

修改 `_inject_workspace_context` 函数签名，增加 `event_queue` 参数：

```python
def _inject_workspace_context(
    system_app,
    workspace_id,
    user_id,
    conv_uid,
    task_id,
    system_prompt,
    extra_agents,
    ext_info,
    llm_config,
    event_queue: Optional[asyncio.Queue] = None,
):
    # ... existing code ...
    def _on_workspace_event(event_type: str, payload: dict):
        if event_queue is not None:
            event_queue.put_nowait((event_type, payload))

    agent = build_workspace_toolkit(
        system_app=system_app,
        workspace_id=int(workspace_id),
        user_id=user_id,
        conv_uid=conv_uid,
        task_id=int(task_id) if task_id else None,
        mode=mode,
        llm_config=llm_config,
        on_event=_on_workspace_event,
    )
    # ... rest unchanged ...
```

在 `aggregation_chat` 方法中创建 queue 并传入：

```python
workspace_event_queue: asyncio.Queue = asyncio.Queue()

_inject_workspace_context(
    system_app=self.system_app,
    workspace_id=ext_info.get("workspace_id"),
    user_id=user_code,
    conv_uid=conv_id,
    task_id=ext_info.get("task_id"),
    system_prompt=system_prompt_parts,
    extra_agents=ext_info.setdefault("extra_agents", []),
    ext_info=ext_info,
    llm_config=LLMConfig(llm_client=self.llm_provider),
    event_queue=workspace_event_queue,
)
```

在 SSE 生成器循环中，每次 yield 消息前检查 queue：

```python
# 在生成器循环内，yield message 之前
while not workspace_event_queue.empty():
    event_type, payload = workspace_event_queue.get_nowait()
    yield task, format_workspace_event(event_type, payload), agent_conv_id
```

- [ ] **Step 5: 写后端单元测试**

```python
# packages/derisk-serve/tests/workspace/agent_tools/test_write_tools.py
import pytest
from unittest.mock import MagicMock

from derisk_serve.workspace.agent_tools._task_creator import create_task_from_tool


def test_create_task_from_tool():
    mock_task = MagicMock()
    mock_task.id = 42
    mock_task.title = "测试任务"
    mock_task.status = "pending_trigger"
    mock_task.playbook_id = 7
    mock_task.triggered_by = "manual"

    mock_task_service = MagicMock()
    mock_task_service.create.return_value = mock_task

    mock_playbook = MagicMock()
    mock_playbook.name = "容量巡检"

    mock_playbook_service = MagicMock()
    mock_playbook_service.get_by_id.return_value = mock_playbook

    system_app = MagicMock()
    def get_component(name, cls):
        if name == "task_service":
            return mock_task_service
        if name == "playbook_service":
            return mock_playbook_service
        return None
    system_app.get_component = get_component

    result = create_task_from_tool(
        system_app, workspace_id=1, user_id="100", playbook_id=7
    )
    assert result["task_id"] == 42
    assert result["playbook_name"] == "容量巡检"
```

Run: `cd packages/derisk-serve && python -m pytest tests/workspace/agent_tools/test_write_tools.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py
 git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py
 git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py
 git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py
 git add packages/derisk-serve/tests/workspace/agent_tools/test_write_tools.py
 git commit -m "feat(workspace): make start_task create task and emit task_created event"
```

---

### Task 2: 前端 —— 新建 `TaskCreatedCard` 组件

**Files:**
- Create: `web/src/components/chat/task-created-card.tsx`
- Test: 手动验证（通过 Storybook 或直接集成到 ChatContentContainer 后验证）

**Interfaces:**
- Consumes: `WorkspaceEvent['payload']`（含 task_id, title, status, playbook_name, triggered_by）。
- Produces: `TaskCreatedCard` 组件，接收 `payload` 和 `onViewTask` callback。

- [ ] **Step 1: 实现组件**

```tsx
// web/src/components/chat/task-created-card.tsx
'use client';

import { Button, Card, Tag } from 'antd';

export interface TaskCreatedCardPayload {
  task_id: number;
  title: string;
  status: string;
  playbook_id?: number;
  playbook_name?: string;
  triggered_by?: string;
  workspace_id?: number;
}

export interface TaskCreatedCardProps {
  payload: TaskCreatedCardPayload;
  onViewTask?: (taskId: number) => void;
}

export function TaskCreatedCard({ payload, onViewTask }: TaskCreatedCardProps) {
  return (
    <Card size="small" className="chat-task-created-card" style={{ margin: '12px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 18 }}>🚀</span>
        <strong>{payload.title || `任务 #${payload.task_id}`}</strong>
        <Tag>{payload.status}</Tag>
      </div>
      <div style={{ color: '#666', fontSize: 13, marginBottom: 12 }}>
        {payload.playbook_name && <span>剧本：{payload.playbook_name}</span>}
        {payload.triggered_by && (
          <span style={{ marginLeft: payload.playbook_name ? 12 : 0 }}>
            触发：{payload.triggered_by}
          </span>
        )}
      </div>
      <Button
        type="primary"
        size="small"
        onClick={() => onViewTask?.(payload.task_id)}
      >
        查看任务进展
      </Button>
    </Card>
  );
}
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd web && yarn tsc --noEmit --project tsconfig.json`
Expected: 无新增报错（可能项目已有报错，确保本组件无新增错误）。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/chat/task-created-card.tsx
 git commit -m "feat(web): add TaskCreatedCard component for workspace task events"
```

---

### Task 3: 前端 —— `ChatSession` 把 `task_created` 事件写入 history，`ChatContentContainer` 渲染任务卡片

**Files:**
- Modify: `web/src/components/chat/chat-session.tsx`
- Modify: `web/src/components/chat/chat-content-container.tsx`
- Test: 手动验证（发送消息后检查任务卡片渲染）

**Interfaces:**
- Consumes: `onWorkspaceEvent` 回调收到的 `task_created` event。
- Produces: `history` 中追加一个特殊 `view` 消息；`ChatContentContainer` 识别并渲染 `TaskCreatedCard`。

- [ ] **Step 1: 在 ChatSession 中把 workspace event 转为特殊 view 消息**

`chat-session.tsx` 中 `handleChat` 的 `onWorkspaceEvent` 回调目前只是透传。改成：

```tsx
onWorkspaceEvent: (event: WorkspaceEvent) => {
  props.onWorkspaceEvent?.(event);
  if (event.type === 'task_created') {
    setHistory((prev) => [
      ...prev,
      {
        role: 'view',
        context: JSON.stringify({ type: 'task_created', payload: event.payload }),
        order: order.current,
        time_stamp: 0,
        model_name: '',
        thinking: false,
      },
    ]);
  }
},
```

- [ ] **Step 2: ChatContentContainer 识别特殊 view 消息并渲染卡片**

```tsx
import { TaskCreatedCard, TaskCreatedCardPayload } from './task-created-card';

function isTaskCreatedMessage(item: ChatHistoryItem): TaskCreatedCardPayload | null {
  if (item.role !== 'view') return null;
  try {
    const ctx = typeof item.context === 'string' ? JSON.parse(item.context) : item.context;
    if (ctx && ctx.type === 'task_created') {
      return ctx.payload as TaskCreatedCardPayload;
    }
  } catch {
    // ignore parse error
  }
  return null;
}
```

在消息渲染循环中：

```tsx
{history.map((item, idx) => {
  const taskPayload = isTaskCreatedMessage(item);
  if (taskPayload) {
    return (
      <TaskCreatedCard
        key={idx}
        payload={taskPayload}
        onViewTask={(taskId) => {
          // 通过全局事件切换到 workbench
          window.dispatchEvent(new CustomEvent('workspace:view-task', { detail: { taskId } }));
        }}
      />
    );
  }
  return <ChatMessageItem key={idx} item={item} />;
})}
```

> 注：若项目已有消息组件名不同，请按实际名称替换 `ChatMessageItem`。

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd web && yarn tsc --noEmit --project tsconfig.json`
Expected: 无新增报错。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/chat/chat-session.tsx
 git add web/src/components/chat/chat-content-container.tsx
 git commit -m "feat(web): render task_created events as TaskCreatedCard in chat"
```

---

### Task 4: 前端 —— 新建 `LobbyChatInput` 组件

**Files:**
- Create: `web/src/app/workspaces/detail/lobby-chat-input.tsx`
- Test: 手动验证（在大厅输入消息后切换视图）

**Interfaces:**
- Consumes: `appCode`, `workspaceId`, `convUid`。
- Produces: `onSend: (text: string) => void` callback（由父组件负责切到 S1 并发送消息）。

- [ ] **Step 1: 实现轻量输入框**

```tsx
// web/src/app/workspaces/detail/lobby-chat-input.tsx
'use client';

import { useState } from 'react';
import { Button, Input } from 'antd';
import { SendOutlined } from '@ant-design/icons';

export interface LobbyChatInputProps {
  placeholder?: string;
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function LobbyChatInput({
  placeholder = '发起新任务...',
  onSend,
  disabled,
}: LobbyChatInputProps) {
  const [text, setText] = useState('');

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
    <div className="ws-lobby-chat-input">
      <Input.TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoSize={{ minRows: 1, maxRows: 6 }}
        disabled={disabled}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={handleSend}
        disabled={!text.trim() || disabled}
      />
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd web && yarn tsc --noEmit --project tsconfig.json`
Expected: 无新增报错。

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/lobby-chat-input.tsx
 git commit -m "feat(web): add LobbyChatInput component"
```

---

### Task 5: 前端 —— `client.tsx` 新增三态管理

**Files:**
- Modify: `web/src/app/workspaces/detail/client.tsx`
- Test: 手动验证（三种状态切换）

**Interfaces:**
- Consumes: `Lobby`, `Workbench`, `ChatSession`。
- Produces: `viewMode: 'lobby' | 'chat' | 'workbench'`，`selectedTaskId`。

- [ ] **Step 1: 替换二态为三态，并处理大厅首条消息**

```tsx
// web/src/app/workspaces/detail/client.tsx
import { useRef } from 'react';
import type { ChatSessionHandle } from '@/components/chat/chat-session';

type ViewMode = 'lobby' | 'chat' | 'workbench';

export default function WorkspaceDetailPage() {
  // ...
  const [viewMode, setViewMode] = useState<ViewMode>('lobby');
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string>('');
  const chatSessionRef = useRef<ChatSessionHandle>(null);

  const enterChat = (text?: string) => {
    if (text) setPendingMessage(text);
    setViewMode('chat');
  };
  const enterWorkbench = (taskId: number) => {
    setSelectedTaskId(taskId);
    setViewMode('workbench');
  };
  const backToLobby = () => {
    setSelectedTaskId(null);
    setViewMode('lobby');
  };

  // 切到对话视图后，自动发送大厅里输入的 pending message
  useEffect(() => {
    if (viewMode === 'chat' && pendingMessage && chatSessionRef.current) {
      chatSessionRef.current.sendMessage(pendingMessage);
      setPendingMessage('');
    }
  }, [viewMode, pendingMessage]);

  // 监听任务卡片点击事件（从 ChatContentContainer 派发）
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.taskId) {
        enterWorkbench(Number(detail.taskId));
      }
    };
    window.addEventListener('workspace:view-task', handler);
    return () => window.removeEventListener('workspace:view-task', handler);
  }, []);

  // ...

  return (
    <div className="ws-page">
      {/* header 和 signal chain 保持原样 */}
      <div className="ws-console">
        {viewMode === 'lobby' && (
          <Lobby
            workspaceId={workspaceId}
            workspaceCode={workspaceCode}
            workspaceName={ws.name}
            workspaceType={scenario}
            appCode={appCode}
            convUid={convUid || ''}
            onSelectTask={enterWorkbench}
            onQuickStart={(pid) => {
              // Task 6 中实现真实创建
            }}
            onSendFirstMessage={enterChat}
          />
        )}
        {viewMode === 'chat' && (
          <div className="ws-chat-view">
            <div className="ws-chat-view__header">
              <Button type="link" onClick={backToLobby}>← 返回大厅</Button>
            </div>
            <ChatSession
              ref={chatSessionRef}
              convUid={convUid}
              appCode={appCode}
              workspaceId={workspaceId}
              hideRightPanel={true}
            />
          </div>
        )}
        {viewMode === 'workbench' && selectedTaskId && taskConvUid && (
          <Workbench
            taskId={selectedTaskId}
            workspaceId={workspaceId}
            appCode={appCode}
            convUid={taskConvUid}
            onBack={backToLobby}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 编译检查**

Run: `cd web && yarn tsc --noEmit --project tsconfig.json`
Expected: 无新增报错。

- [ ] **Step 3: Commit**

```bash
git add web/src/app/workspaces/detail/client.tsx
 git commit -m "feat(web): add lobby/chat/workbench three-state management"
```

---

### Task 6: 前端 —— 改造 `Lobby`

**Files:**
- Modify: `web/src/app/workspaces/detail/lobby.tsx`
- Modify: `web/src/app/workspaces/detail/lobby.css`
- Test: 手动验证（无重复标题、快捷发起创建任务）

**Interfaces:**
- Consumes: `createTask` API；`LobbyChatInput`。
- Produces: `onSendFirstMessage` callback；真实 task 创建。

- [ ] **Step 1: 修改 LobbyProps 和组件**

在 `lobby.tsx` 顶部导入 `createTask`：

```tsx
import {
  apiInterceptors,
  createTask,
  listTasks,
  listArtifacts,
  listDeliveries,
  listPlaybooks,
} from '@/client/api';
```

修改 Props 和组件主体：

```tsx
export interface LobbyProps {
  workspaceId: number;
  workspaceCode: string;
  workspaceName: string;
  workspaceType: string;
  appCode: string;
  convUid: string;
  onSelectTask: (taskId: number) => void;
  onQuickStart: (playbookId: number) => void;
  onSendFirstMessage: (text: string) => void;
}

export function Lobby({
  // ...
  onSendFirstMessage,
}: LobbyProps) {
  // 移除 ChatSession 和 handleWorkspaceEvent
  // 保留 tasks / deliveries / artifacts / playbooks 请求

  const handleQuickStart = async (playbookId: number) => {
    const [err, task] = await apiInterceptors(
      createTask({ workspace_id: workspaceId, playbook_id: playbookId })
    );
    if (err || !task) return;
    onSelectTask(task.id);
  };

  return (
    <div className="ws-lobby">
      <div className="ws-lobby__main">
        {/* 删除 ws-lobby__identity 大标题区块 */}
        {/* 保留 Signal Chain 和 Loop strip 在 client.tsx 中 */}

        {/* 进行中任务、栖居交付物、最近交付、快捷发起 保持原样 */}
        {/* 快捷发起 onClick 改为 handleQuickStart */}

        {/* 底部输入框改用 LobbyChatInput */}
        <div className="ws-lobby__input">
          <LobbyChatInput
            placeholder="发起新任务..."
            onSend={onSendFirstMessage}
          />
        </div>
      </div>
      <aside className="ws-lobby__rail">
        <GrowthCard workspaceId={workspaceId} />
      </aside>
    </div>
  );
}
```


- [ ] **Step 2: 删除重复标题样式（可选）**

如果 `lobby.css` 中有 `.ws-lobby__identity` 相关样式且不再使用，可删除。

- [ ] **Step 3: TypeScript 编译检查**

Run: `cd web && yarn tsc --noEmit --project tsconfig.json`
Expected: 无新增报错。

- [ ] **Step 4: Commit**

```bash
git add web/src/app/workspaces/detail/lobby.tsx
 git add web/src/app/workspaces/detail/lobby.css
 git commit -m "feat(web): lobby removes duplicate title and quick-start creates real task"
```

---

### Task 7: 前端 —— 改造 `Workbench` 为上下分区终态

**Files:**
- Modify: `web/src/app/workspaces/detail/workbench.tsx`
- Modify: `web/src/app/workspaces/detail/workbench.css`
- Test: 手动验证（进展 / 交付物 / 折叠对话 / 执行轨迹 四区显示）

**Interfaces:**
- Consumes: `getTaskInfo`, `listArtifacts`, `listInterventions`, `ChatSession`。
- Produces: 上下分区布局；折叠协作对话。

- [ ] **Step 1: 重构 Workbench 布局**

```tsx
// web/src/app/workspaces/detail/workbench.tsx
export function Workbench({ taskId, workspaceId, appCode, convUid, onBack }: WorkbenchProps) {
  const [dialogExpanded, setDialogExpanded] = useState(false);
  const [events, setEvents] = useState<WorkspaceEvent[]>([]);

  // 保留 task / artifacts / interventions 请求

  const handleWorkspaceEvent = useCallback((event: WorkspaceEvent) => {
    setEvents((prev) => [...prev, event]);
  }, []);

  // 进展步骤从 events + task.status 推导（P0 简化）
  const progressSteps = useMemo(() => {
    const steps: Array<{ name: string; tool?: string; status: 'done' | 'running' | 'pending' }> = [];
    const ctxEvent = events.find((e) => e.type === 'context_loaded');
    if (ctxEvent) {
      steps.push({ name: '上下文加载', tool: `${ctxEvent.payload.materialized_count} 项资源`, status: 'done' });
    }
    if (task?.status === 'running' || task?.status === 'awaiting_human') {
      steps.push({ name: 'Agent 执行中', status: 'running' });
    }
    if (task?.status === 'delivered' || task?.status === 'closed') {
      steps.push({ name: '交付完成', status: 'done' });
    }
    return steps;
  }, [events, task]);

  return (
    <div className="ws-wb">
      <div className="ws-wb__header">
        <span className="ws-wb__back" onClick={onBack}>← 返回大厅</span>
        <span className="ws-wb__title">{task?.title || `task_${taskId}`}</span>
        {task?.triggered_by && <span className="ws-wb__meta">{task.triggered_by}</span>}
      </div>

      <div className="ws-wb__body">
        {/* 进展 */}
        <section className="ws-wb__section">
          <h3 className="ws-wb__section-title">📊 进展</h3>
          <div className="ws-wb__progress">
            {progressSteps.length === 0 && (
              <div className="ws-wb__step ws-wb__step--pending">
                <span className="ws-wb__step-icon">○</span>
                <span className="ws-wb__step-name">等待开始</span>
              </div>
            )}
            {progressSteps.map((step, i) => (
              <div key={i} className={`ws-wb__step ws-wb__step--${step.status}`}>
                <span className="ws-wb__step-icon">
                  {step.status === 'done' ? '✓' : step.status === 'running' ? '◐' : '○'}
                </span>
                <span className="ws-wb__step-name">{step.name}</span>
                {step.tool && <span className="ws-wb__step-tool">{step.tool}</span>}
              </div>
            ))}
          </div>
        </section>

        {/* 交付物 */}
        <section className="ws-wb__section">
          <h3 className="ws-wb__section-title">📦 交付物</h3>
          {artifacts && artifacts.length > 0 ? (
            <div className="ws-wb__artifact-grid">
              {artifacts.map((a: any) => (
                <Card key={a.id} size="small" className="ws-wb__artifact-card">
                  <div className="ws-wb__artifact-title">{a.title || `artifact_${a.id}`}</div>
                  <Tag>{a.type}</Tag>
                  <div className="ws-wb__artifact-actions">
                    <Button size="small">预览</Button>
                    <Button size="small">发送</Button>
                    <Button size="small">沉淀为 Asset</Button>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <div className="ws-empty">暂无交付物</div>
          )}
        </section>

        {/* 协作对话（折叠） */}
        <section className="ws-wb__section">
          <h3
            className="ws-wb__section-title ws-wb__section-title--clickable"
            onClick={() => setDialogExpanded(!dialogExpanded)}
          >
            💬 协作对话 {dialogExpanded ? '收起' : '展开'}
          </h3>
          {dialogExpanded && (
            <div className="ws-wb__dialog">
              <ChatSession
                convUid={convUid}
                appCode={appCode}
                workspaceId={String(workspaceId)}
                taskId={String(taskId)}
                hideRightPanel={true}
                onWorkspaceEvent={handleWorkspaceEvent}
              />
            </div>
          )}
        </section>

        {/* 执行轨迹 */}
        <section className="ws-wb__section">
          <h3 className="ws-wb__section-title">📜 执行轨迹</h3>
          <div className="ws-wb__trace">
            <div className="ws-wb__trace-item">
              AgentRun · {task?.status} · {task?.updated_at || '—'}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 调整 workbench.css**

确保 `.ws-wb__body` 可滚动，各 section 间距清晰：

```css
.ws-wb {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.ws-wb__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.ws-wb__section {
  margin-bottom: 24px;
}

.ws-wb__section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
}

.ws-wb__section-title--clickable {
  cursor: pointer;
  user-select: none;
}

.ws-wb__dialog {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px;
  min-height: 300px;
}
```

- [ ] **Step 3: TypeScript 编译检查**

Run: `cd web && yarn tsc --noEmit --project tsconfig.json`
Expected: 无新增报错。

- [ ] **Step 4: Commit**

```bash
git add web/src/app/workspaces/detail/workbench.tsx
 git add web/src/app/workspaces/detail/workbench.css
 git commit -m "feat(web): redesign workbench as vertical sections per spec §5.2"
```

---

### Task 8: 集成验证

**Files:**
- 全部相关文件
- Test: 端到端手动验证 + 前端构建

- [ ] **Step 1: 前端构建**

Run: `cd web && yarn build`
Expected: 构建成功，无新增报错。

- [ ] **Step 2: 后端启动**

Run: `cd packages/derisk-app && python -m derisk_app`
Expected: 服务正常启动，无 import error。

- [ ] **Step 3: 手动验证清单**

| 验证项 | 期望结果 |
|---|---|
| 进入空间 | 显示 S0 大厅概览，顶部 header 有空间名，主体无重复大标题 |
| 大厅输入消息 | 切换到 S1 对话视图，消息气泡正常显示 |
| Agent 创建任务 | 消息流中出现任务卡片，显示任务名/状态/"查看任务进展"按钮 |
| 点击任务卡片 | 切换到 S2 任务工作台 |
| 点击进行中任务卡片 | 切换到对应 S2 任务工作台 |
| 快捷发起按钮 | 真实创建任务并进入 S2 |
| 任务工作台 | 看到进展 / 交付物 / 折叠对话 / 执行轨迹 四区 |
| 展开协作对话 | 显示完整消息流，底部输入框可给任务发指令 |
| 返回大厅 | 回到 S0 |

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
 git commit -m "fix(workspace): integration fixes for three-state workflow"
```

---

## Self-Review

### 1. Spec coverage

| Spec 要求 | 对应 Task |
|---|---|
| S0 大厅概览四块主线 | Task 6 |
| S1 大厅对话主体切为消息流 | Task 4 + Task 5 |
| S2 任务工作台上下分区 | Task 7 |
| 消息流中任务卡片 | Task 1 + Task 2 + Task 3 |
| 快捷发起真实创建任务 | Task 6 |
| 去掉重复标题 | Task 6 |
| 三种状态切换 | Task 5 |

### 2. Placeholder scan

- 无 "TBD" / "TODO" / "implement later"。
- 所有代码块为可运行代码或清晰伪代码。
- 文件路径为实际项目路径。

### 3. Type consistency

- `TaskCreatedCardPayload` 字段与后端 `task_created` payload 一致。
- `viewMode: 'lobby' | 'chat' | 'workbench'` 在 client.tsx 和各子组件间一致。
- `onSelectTask` / `onQuickStart` / `onSendFirstMessage` callback 签名已对齐。

### 已知风险

- **执行轨迹实时性**：P0 只展示简单的 AgentRun 占位，真正的执行轨迹明细（工具调用链）需要后端 Agent 输出结构化事件，属于 P1 范围。
- **task_created 事件桥接**：Task 1 中通过 asyncio.Queue 桥接同步 tool 与异步 SSE，需在实际代码中验证 queue 生命周期是否覆盖整个请求。
- **全局事件通信**：Task 3 使用 `window.dispatchEvent` 从 `ChatContentContainer` 通知 `client.tsx` 切换任务工作台，是临时方案；长期应通过 React context 或路由状态管理。
