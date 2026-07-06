# 场景空间三种工作状态设计

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-07-06 |
| 作者 | yhjun1026 + Claude |
| 关联文档 | `docs/superpowers/specs/2026-06-29-scenario-workspace-product-form-design.md` |

---

## 1. 背景与问题

当前 `/workspaces/detail` 页面已经具备"空间大厅 + 任务工作台"的两态骨架，但实际使用中存在三个关键断裂：

1. **对话没有展示区域**：`Lobby` 和 `Workbench` 中的 `<ChatSession>` 都传了 `inputSlot` prop，导致 ChatSession 只渲染输入框、不渲染消息历史区域。用户输入后看不到对话流。
2. **三种状态没有完整实现**：
   - 大厅默认态：信息架构存在双标题重复，快捷发起没有真正创建任务。
   - 大厅对话态：代码里没有独立状态，输入框和大厅主体没有联动。
   - 任务工作台态：协作对话只显示 workspace events，不是真正的消息流；布局与 §5.2 终态形态不一致。
3. **状态切换不自然**：点击任务卡片能进入工作台，但对话中创建的任务无法点击切入；快捷发起只是改 URL query。

本文档定义三种工作状态的终态形态，以及让三种状态都可用所需的最小改造集。

---

## 2. 三种工作状态

| 状态 | 名称 | 触发条件 | 主体显示 | 输入框语义 |
|---|---|---|---|---|
| **S0 大厅概览** | 默认态 | 进入空间；点击"返回大厅" | 空间大厅（四块主线 + 右侧栏） | "发起新任务..." |
| **S1 大厅对话** | 对话态 | 在大厅底部输入框发送任意消息 | 完整对话消息流 | 普通对话输入 |
| **S2 任务工作台** | 任务态 | 点击任务卡片 / 快捷发起 / 对话中的任务卡片 | 进展 + 交付物 + 折叠协作对话 + 执行轨迹 | "给 task_xxx 下指令..." |

### 2.1 状态关系图

```
                    ┌─────────────────┐
                    │   S0 大厅概览   │
                    │  （默认进入）   │
                    └────────┬────────┘
                             │ 底部输入框发送第一条消息
                             ▼
                    ┌─────────────────┐
                    │  S1 大厅对话    │
                    │ （完整消息流）  │
                    └────────┬────────┘
                             │ 点击 Agent 创建的任务卡片
                             │ 或点击"返回大厅"
              ┌──────────────┴──────────────┐
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │  S2 任务工作台  │           │   S0 大厅概览   │
    │ （上下分区）    │           │   （回到默认）  │
    └────────┬────────┘           └─────────────────┘
             │ 点击"返回大厅"
             ▼
    ┌─────────────────┐
    │   S0 大厅概览   │
    └─────────────────┘
```

---

## 3. S0 空间大厅

对齐 `2026-06-29-scenario-workspace-product-form-design.md` §5.1 终态。

### 3.1 页面结构

```
┌─────────────────────────────────────────────────────────────────────┐
│ [场景空间 ▾ 运营1组]                                  [交付空间] ... │
├─────────────────────────────────────────────────────────────────────┤
│ Signal Chain: 触发源 → 剧本 → 介入 → 任务 → 产出/交付                │
│ Loop: queued │ running │ needs review │ delivered │ in memory        │
├──────────────────────────────────────┬──────────────────────────────┤
│                                      │  待我处理 (2)                │
│  📋 进行中任务 (5)                   │   - task_123 ...             │
│  ┌──────────────────────────────┐   │                              │
│  │ task_124 容量巡检            │   │  本月空间成长                │
│  │ ◐ running · 2 项异常         │   │   - 沉淀 Asset 0             │
│  │ timer · 06-24 02:00          │   │   - Playbook 演化提议 0      │
│  └──────────────────────────────┘   │   - 任务趋势 0 次 (30 天)    │
│                                      │   - 知识图谱节点 0           │
│  🏠 栖居的交付物 (4)                 │                              │
│  ┌──────────┐ ┌──────────┐          │  最近交付物                  │
│  │ 📊 容量  │ │ 🔧 运维  │          │   - ...                      │
│  │ 看板     │ │ 历史站   │          │                              │
│  │ running  │ │ running  │          │  最近介入 (5)                │
│  │ [打开]   │ │ [打开]   │          │   - ...                      │
│  └──────────┘ └──────────┘          │                              │
│                                      │                              │
│  📨 最近交付 (3)                     │                              │
│  ┌──────────────────────────────┐   │                              │
│  │ 📄 容量巡检报告 06-24        │   │                              │
│  │ delivered · email · 2h       │   │                              │
│  └──────────────────────────────┘   │                              │
│                                      │                              │
│  ⚡ 快捷发起                         │                              │
│  [+ 容量巡检] [+ 应急响应] ...       │                              │
├──────────────────────────────────────┴──────────────────────────────┤
│  [输入框] "发起新任务..."                                [发送]      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 关键修复

- **去掉重复标题**：当前 `Lobby` 组件内有一个 `{workspaceName}` 大标题，与顶部 header 重复。删除该标题，空间身份只由顶部 header 承载。
- **快捷发起真实创建任务**：点击快捷发起按钮后，调用 `createTask({ workspace_id, playbook_id })`，创建成功后直接切换到 S2 任务工作台。
- **空剧本引导保留**：当空间没有 Playbook 时，仍显示"去剧本管理创建一个，或直接在底部输入框下指令"。

---

## 4. S1 大厅对话

### 4.1 触发与表现

- 用户在 S0 底部输入框发送任意消息后，主体从大厅概览切换为完整对话消息流。
- 该对话使用空间级会话（`convUid`），与 `ConversationSwitcher` 中选中的会话一致。
- 输入框常驻底部，语义为普通对话输入。

### 4.2 消息流中的任务卡片

当 Agent 在对话中创建 Task 时，在消息流中渲染一个结构化任务卡片：

```
┌─────────────────────────────────────┐
│ 🚀 已创建任务：容量巡检 06-24        │
│ 状态：running                        │
│ 触发：manual · playbook: 容量巡检    │
│ [查看任务进展]                       │
└─────────────────────────────────────┘
```

用户点击"查看任务进展"后，切换到 S2 任务工作台。

### 4.3 返回大厅

S1 顶部保留一个"返回大厅"入口，点击后回到 S0。

---

## 5. S2 任务工作台

严格对齐 `2026-06-29-scenario-workspace-product-form-design.md` §5.2 的上下分区终态形态。

### 5.1 页面结构

```
┌─────────────────────────────────────────────────────────────────────┐
│ [场景空间 ▾ 运营1组]                                  [交付空间] ... │
├─────────────────────────────────────────────────────────────────────┤
│ ← 返回大厅    task_124 容量巡检    timer · 06-24 02:00   [running]   │
├─────────────────────────────────────────────────────────────────────┤
│  📊 进展                                                            │
│  ✓ 上下文加载 (5 项资源)           2m                               │
│  ✓ 取数完成 (db_query)             1m                               │
│  ◐ 报告生成中 (report)             running                          │
│  ○ 待 Review                                                        │
│  ○ 待 Delivery                                                      │
├─────────────────────────────────────────────────────────────────────┤
│  📦 交付物                                                          │
│  ┌─────────────────────────────────────┐                            │
│  │ 📄 容量巡检报告 06-24               │                            │
│  │ 草稿 · v1                           │                            │
│  │ [预览] [发送] [沉淀为 Asset]        │                            │
│  └─────────────────────────────────────┘                            │
├─────────────────────────────────────────────────────────────────────┤
│  💬 协作对话 (3)  [展开完整对话]                                     │
│  > 用户: 跑一次容量巡检                                              │
│  > Agent: 已创建任务 task_124                                        │
│  > 用户: 上次报告在哪                                                │
├─────────────────────────────────────────────────────────────────────┤
│  📜 执行轨迹  [展开]                                                │
│  AgentRun #3 · running · 3m                                          │
├─────────────────────────────────────────────────────────────────────┤
│  [输入框] "给 task_124 下指令..."                        [发送]      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 各区域定义

#### 进展区

- 从 `WorkspaceEvent` 和 `task.status` 推导步骤。
- P0 简化版步骤：
  1. 上下文加载（`context_loaded` event）
  2. Agent 执行中（`task.status === 'running'`）
  3. 交付完成（`task.status === 'delivered' || 'closed'`）
- 每个步骤显示工具名和耗时，点击可展开看工具输入输出。

#### 交付物区

- 展示 `listArtifacts({ task_id })` 返回的 Artifact 列表。
- 每个 Artifact 卡片支持：预览、发送、沉淀为 Asset、托管为看板（后两者 P1/P2 真实实现，P0 可占位）。

#### 协作对话区

- 默认折叠，只显示最近 3 条消息摘要。
- 点击"展开完整对话"后显示完整消息流。
- 消息流复用 `ChatContentContainer`，显示该 task 关联会话的真实历史消息。

#### 执行轨迹区

- 展示 AgentRun 列表。
- 默认折叠，点击展开看完整日志和工具调用详情。

---

## 6. 技术实现

### 6.1 状态管理

`web/src/app/workspaces/detail/client.tsx` 中新增三态管理：

```ts
type ViewMode = 'lobby' | 'chat' | 'workbench';

const [viewMode, setViewMode] = useState<ViewMode>('lobby');
const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
```

替换现有的二态判断（`selectedTaskId === null ? <Lobby/> : <Workbench/>`）。

### 6.2 修复 ChatSession 误用

当前代码：

```tsx
<ChatSession
  convUid={convUid}
  appCode={appCode}
  workspaceId={workspaceId}
  hideRightPanel={true}
  onWorkspaceEvent={handleWorkspaceEvent}
  inputSlot={(ctrl) => <UnifiedChatInput ctrl={ctrl} />}
/>
```

`inputSlot` prop 会让 `ChatSession` 只渲染输入框、不渲染消息区域。

改造后：

- **S1 大厅对话**：直接渲染完整 `ChatSession`，不传 `inputSlot`。
- **S2 任务工作台**：在"协作对话"展开状态下渲染完整 `ChatSession`，不传 `inputSlot`。
- **S0 大厅概览**：底部只放一个轻量输入组件（负责发送第一条消息并切到 S1），不再嵌套 `ChatSession`。

### 6.3 大厅输入框组件

新建一个轻量组件 `LobbyChatInput`：

- 外观与 `UnifiedChatInput` 一致。
- 只负责收集用户输入。
- 用户点击发送后：
  1. 调用 `handleChat` 创建/复用空间会话。
  2. 发送消息。
  3. `setViewMode('chat')` 切换到 S1。

### 6.4 任务卡片事件

后端 `agent_chat` 在创建 Task 时，通过 SSE 返回一个结构化事件：

```json
{
  "type": "workspace_event",
  "event_type": "task_created",
  "payload": {
    "task_id": 124,
    "title": "容量巡检 06-24",
    "status": "running",
    "playbook_name": "容量巡检",
    "triggered_by": "manual"
  }
}
```

前端 `ChatContentContainer` 识别该事件，在消息流中渲染任务卡片组件 `TaskCreatedCard`。

### 6.5 快捷发起真实创建任务

```ts
const handleQuickStart = async (playbookId: number) => {
  const [err, task] = await apiInterceptors(
    createTask({ workspace_id: workspaceId, playbook_id: playbookId })
  );
  if (err || !task) return;
  setSelectedTaskId(task.id);
  setViewMode('workbench');
};
```

### 6.6 文件改动清单

| 文件 | 改动 |
|---|---|
| `web/src/app/workspaces/detail/client.tsx` | 新增 `viewMode` 三态，调整渲染分支 |
| `web/src/app/workspaces/detail/lobby.tsx` | 删除重复标题，底部改用 `LobbyChatInput`，快捷发起真实创建任务 |
| `web/src/app/workspaces/detail/workbench.tsx` | 改为上下分区：进展/交付物/折叠对话/执行轨迹；对话区用完整 ChatSession |
| `web/src/app/workspaces/detail/lobby-chat-input.tsx` | 新建大厅输入框组件 |
| `web/src/components/chat/chat-content-container.tsx` | 识别 `task_created` 事件，渲染任务卡片 |
| `web/src/components/chat/task-created-card.tsx` | 新建任务卡片组件 |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | 创建 Task 时发送 `task_created` workspace event |
| `web/src/app/workspaces/detail/lobby.css` | 调整布局间距 |
| `web/src/app/workspaces/detail/workbench.css` | 调整上下分区样式 |

---

## 7. 数据流

### 7.1 S0 → S1

```
用户在 LobbyChatInput 输入
  → 调用 useChat.handleChat({ user_input, conv_uid, ext_info: { workspace_id } })
  → setViewMode('chat')
  → ChatSession 渲染完整消息流
```

### 7.2 S1 → S2

```
Agent 在 aggregation_chat 中创建 Task
  → SSE 返回 workspace_event/task_created
  → ChatContentContainer 渲染 TaskCreatedCard
  → 用户点击卡片
  → setSelectedTaskId(task_id); setViewMode('workbench')
  → Workbench 加载 task info + task conversation + artifacts + events
```

### 7.3 S0 → S2

```
用户点击进行中任务卡片 / 快捷发起按钮
  → setSelectedTaskId(task_id); setViewMode('workbench')
  → Workbench 加载 task 相关数据
```

---

## 8. 范围边界

### 8.1 本次做

- 三种状态定义清晰、切换可用。
- 大厅四块主线数据真实、无重复标题。
- 大厅输入框能切到对话视图。
- 任务卡片可在消息流中点击切入工作台。
- 任务工作台上下分区 + 折叠协作对话。
- 消息流正常显示（修复 `inputSlot` 误用）。
- 快捷发起真实创建任务。

### 8.2 本次不做

- Playbook 可视化编辑器。
- 六种介入模式完整 UI。
- Host/Execute 类交付真实运行。
- 进展步骤从 Agent 工具调用实时结构化推导（P0 用 task status + events 简化）。
- 任务工作台右侧栏复杂化（保持现有 GrowthCard + 待我处理即可）。
- 视觉设计系统彻底重建（需 `.design-context.md`，不在本文档范围）。

---

## 9. 验证标准

- [ ] 进入空间默认显示大厅概览，无重复标题。
- [ ] 大厅底部输入框发送消息后，主体切换为完整对话消息流。
- [ ] 对话中 Agent 创建任务后，消息流里出现可点击任务卡片。
- [ ] 点击任务卡片进入任务工作台，显示任务进展、交付物、折叠对话、执行轨迹。
- [ ] 点击进行中任务卡片能进入对应任务工作台。
- [ ] 快捷发起按钮点击后真实创建任务并进入工作台。
- [ ] 任务工作台底部输入框能给该任务下指令，消息显示在协作对话区。
- [ ] 返回大厅按钮能回到 S0。

---

## 10. 下一步

1. 本 spec review 通过后，调用 `writing-plans` 生成实现计划。
2. 按实现计划分文件改造 `client.tsx`、`lobby.tsx`、`workbench.tsx` 及相关组件。
3. 后端补充 `task_created` workspace event。
4. 跑通验证清单后关闭。
