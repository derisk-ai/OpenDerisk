# 场景空间任务列表重做 — 设计稿

- 日期: 2026-07-11
- 分支: `feat/scene-agent-workspace-input`
- 范围: 场景空间内左侧任务栏(`scene-task-rail`)+ 后端剧本任务执行修复
- 不在范围: 全页任务表(`/workspaces/detail/tasks`)、场景空间中央任务详情卡(`scene-space`)

## 1. 背景与问题

场景空间内左侧任务栏当前每项只显示:状态 Tag / 更新时间 / 标题(缺失回退 `task_<id>`) / "进入对话"。没有过滤分类,看不出任务来自哪个剧本、跑了多久、什么来源,信息密度低、设计粗糙。

更严重的问题:通过 `AgentWorkspaceInput` 选剧本发起的任务**没有真正用 Agent 跑起来**。

### 1.1 现状链路(已勘探确认)

**前端两个任务列表**(本次只改任务栏):
- 场景空间左侧任务栏 `web/src/app/workspaces/detail/scene-task-rail.tsx`
- 全页任务表 `web/src/app/workspaces/detail/tasks/client.tsx`(不动)

**后端 Task 模型** `packages/derisk-serve/src/derisk_serve/task/`:
- `TaskEntity` 表 `server_app_task`,字段齐全:`id, workspace_id, parent_task_id, type, title, description, status, priority, triggered_by, trigger_ref, playbook_id, playbook_version_id, conv_session_id, created_by_user_id, assigned_agents, context, due_at, started_at, closed_at, gmt_created, gmt_modified, is_archived`。
- 状态枚举(应用层 `VALID_TRANSITIONS` 约束,DB 是 `String(32)`):`draft / pending_trigger / running / awaiting_human / blocked / delivered / closed / archived / failed`。注意:**没有 `completed`,对应 `delivered`;没有"待介入",对应 `awaiting_human`**。
- `TaskListFilter` 已支持按 `status` / `type` 过滤(`task/api/schemas.py:57-63`,`TaskDao.list_by_filter`)。
- `TaskResponse`(`task/api/schemas.py:31-54`)字段:`id, workspace_id, parent_task_id, type, title, description, status, priority, triggered_by, trigger_ref, playbook_id, playbook_version_id, conv_session_id, created_by_user_id, assigned_agents, context, due_at, started_at, closed_at, gmt_created, gmt_modified`。

**发起任务的链路**:
1. 前端 `AgentWorkspaceInput` → `useSceneAgentChat.send` → `POST /api/v1/chat/completions`(SSE)。
2. 后端 `aggregation_chat`(`agent/agents/chat/agent_chat.py`):`chat_in_params` 带 `playbook_command` 且 `ext_info.workspace_id` 存在时,走 `playbook_command` 分支(`agent_chat.py:1095-1140`):
   - 调 `create_task_from_tool`(`workspace/agent_tools/_task_creator.py:5-52`) → 只调 `task_service.create(...)` 持久化一条 `draft` 记录(`type='adhoc'`, `triggered_by='manual'`)。
   - `yield` `task_created` workspace 事件 + `[DONE]`,立即 `return`,**跳过 LLM 回合**。
3. `task_created` 事件搭在这次聊天 SSE 流上到达前端 → `scene-workspace-shell` 的 `handleWorkspaceEvent` 调 `onRefreshLists`(`scene-workspace-shell.tsx:124-127`)刷新任务栏。

**问题根因**:`create_task_from_tool` 只创建记录,**从不调 `task_service.start()`,也不调 `playbook_runtime.run_task`**。真正能跑 Agent 的是 `POST /tasks/{task_id}/start` 端点(`task/api/endpoints.py:95-115`,借 FastAPI `BackgroundTasks` 调 `playbook_runtime.run_task`)和介入服务,聊天发起任务的路径完全没接上。

**标题**:无任何 LLM 总结。`title=_user_text or playbook_command.playbook_name`,原始输入或剧本名直接做标题。

**workspace 事件机制(关键约束)**:workspace 事件**没有独立的发布/订阅通道**。事件是搭在"发起那次对话的 chat SSE 流"上、编码成普通 `data:` chunk 传给浏览器的。`format_workspace_event`(`agent_chat.py:259-274`)把事件包成 `{"vis":{"type":<event_type>,"payload":{...}}}`,白名单见 `WORKSPACE_EVENT_TYPES`(`agent_chat.py:247-255`)。

后端 `playbook_runtime.run_task` 是 **FastAPI fire-and-forget 后台任务**,内部走 `app_chat_v3`(ASYNC 非流式),**主动丢弃所有 yield 的 chunk**。它跑任务时没有任何浏览器 SSE 连接绑着。因此:**从 `run_task` 里发 `task_status_changed` → 进黑洞,到不了浏览器**。同样,创建后异步的标题总结也不在任何活跃 SSE 流上。

→ 结论:`task_created`(发起那一刻搭聊天流)能工作,**后台任务状态变更/标题更新无法走事件流推送**。需要一个不依赖后端事件架构的刷新机制。

## 2. 目标与成功标准

1. 任务栏支持 Tab/Chip 分组过滤:全部 / 运行中 / 待介入 / 已完成 / 失败。
2. 每张卡片显示:剧本名 Chip + LLM 总结标题(≤16 字) + 人话化状态(状态点+文案+已耗时) + 来源(`triggered_by`+`type`) + 创建时间 + "进入对话"。
3. 通过 `AgentWorkspaceInput` 选剧本发起的任务**真正用 Agent 跑起来**:创建后直接 `start` → 走 `playbook_runtime.run_task`。
4. 用户选了剧本但没输入任务目标时,不能发起(前端禁用 + 后端拒绝)。
5. 任务栏在任务跑起来后能"跟手"刷新状态/标题(运行时轮询,无后端事件架构改动)。
6. 整体视觉按"方向 B 分层呼吸卡"重做,用现有 design token(`--ws-*`)。

**成功标准**:
- 选剧本发起任务 → 任务栏 4s 内出现该任务且状态为 `running` → Agent 真实跑(vis 流推到该任务对话)→ 跑完状态自动变 `delivered`/`awaiting_human`/`failed` → 无活跃任务后轮询停止。
- 标题从原始输入在几秒内变成 ≤16 字 LLM 总结。
- 切换 Tab 实时过滤,不发请求;空态有引导文案。
- 选剧本 + 空文本点发送被拦截,前端禁用 + 后端不建任务。

## 3. 设计

### 3.1 后端:让发起的剧本任务真正跑 Agent(§1)

**改动文件**:`packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py`、`packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`(playbook_command 分支)。

**`create_task_from_tool` 改动**:
当前只调 `task_service.create(...)`。改为:创建成功后,用 `asyncio.create_task` 挂一个 detached 协程,内部调 `task_service.start(task_id)` → `playbook_runtime.run_task`(同 `/tasks/{id}/start` 端点那条真能跑的路),`create_task_from_tool` 立即返回。

- SSE 流:`aggregation_chat` 仍先 `yield` `task_created` + `[DONE]` 立即返回,前端体验不变。
- 后台:`run_task` detached 跑,`draft → running`,跑完自动 `delivered`/`awaiting_human`/`failed`。
- 不重写 Agent 调度,复用现有 `task_service.start` + `playbook_runtime.run_task`。

**为何用 `asyncio.create_task` 而非借 `BackgroundTasks`**:`create_task_from_tool` 从 `aggregation_chat`(在 chat SSE 流里)调进来,没有 FastAPI `BackgroundTasks` 依赖可借。`asyncio.create_task` 是 `app_chat_v3` 内部已在用的同款机制,`run_task` 本身是 asyncio 协程,detached 跑符合现有架构。

**输入校验**:`agent_chat.py` 的 `playbook_command` 分支,`_user_text` 为空时不创建任务,回一个错误 vis 提示(后端兜底)。剧本指定资源/能力,任务目标由用户输入提供,二者缺一不可。

**`model_name` 透传**:`create_task_from_tool` 当前签名没收 `model_name`,§3.2 的标题总结需要。`aggregation_chat` 把 `chat_in_params` 里的 model 作为参数透进 `create_task_from_tool`。

**边界**:`create_task_from_tool` 只在 `playbook_command` 分支被调,已有 playbook → `playbook_id` 非空,`run_task` 安全。大厅模式(无剧本裸文本)不会进这条路径,不创建任务。

### 3.2 后端:异步 LLM 标题总结(§2)

**改动文件**:`_task_creator.py`(同 §3.1)。

新增 helper:`async def _summarize_task_title(user_text: str, playbook_name: str | None, model: str | None) -> str`。按 `packages/derisk-serve/src/derisk_serve/knowledge/ingest.py:517-589`(_call_llm)的已有模式,用 `AIWrapper` + `ModelConfigCache`(`derisk.agent.util.llm.llm_client` / `model_config_cache`)做单次 LLM 调用。不需 `system_app`(这两个是模块级单洞,启动时已注册模型)。

Prompt 大意:
> 把下面这条任务发起文本压缩成 ≤16 字的简短中文标题,只输出标题,不要任何解释:
> 用户输入:{user_text}
> 剧本:{playbook_name}

**触发**:`create_task_from_tool` 创建任务(占位 `title=user_text`)后,`asyncio.create_task` 起第二个 detached 协程:
1. 调 `_summarize_task_title(...)`。
2. 成功且非空 → `task_service.update` 写回 `title`。
3. 失败/空/异常 → 静默记日志,保留占位 `title`。单次失败不重试。

与 §3.1 的 `run_task` 协程并行跑,`try/except` 兜底,互不影响,绝不影响已返回的 SSE。

**模型**:复用用户在 `AgentWorkspaceInput` 选的 `model_name`(经 §3.1 透传)。`model_name` 缺失 → `ModelConfigCache.get_all_models()[0]`,都没有则跳过总结。

**标题到前端**:不走事件流(后台任务无通道)。下次轮询(§3.4)拉到新 `title` 即显示。

### 3.3 后端数据现实确认(不改)

勘探确认 `listTasks`/`getTaskInfo` 返回的 `TaskResponse`:
- `playbook_name` **缺失** — 只有 `playbook_id`。前端用 shell 已 fetch 的 `playbooks` 列表按 `playbook_id` 本地查名(§3.4),零后端改动。
- 失败原因 **不存储** — `TaskEntity` 无此列。本期失败卡片只显"失败"状态文案,原因留详情卡/对话流。
- 交付物计数 **无批量端点**,任务栏 N+1 不可接受。本期任务栏不显示计数,保留详情卡的交付物列表。

→ §3.3 后端 **零字段改动**。

### 3.4 前端:任务栏重做(§3)

**改动文件**:`web/src/app/workspaces/detail/scene-task-rail.tsx`(主改)、`scene-workspace-shell.tsx`(透传 `playbooks`)、`scene-workspace.css`(卡片样式)。

**视觉方向**:方向 B 分层呼吸卡(已 mockup 确认)。用现有 `--ws-*` token。

**Tab/Chip 分组过滤**(组件内 `useState`,默认"全部",纯前端过滤不发请求):
- `全部` / `运行中`(`running, pending_trigger, blocked, draft`) / `待介入`(`awaiting_human`) / `已完成`(`delivered, closed`) / `失败`(`failed`)
- 每个 Tab 带数字徽标,零值灰显。
- 标题行:"任务与介入" + 聚合计数(总数 · 活跃数)。
- 保留搜索框(现有)。

**卡片信息**(全部来自 `TaskResponse` 现有字段 + 本地查剧本名):
```
┌──────────────────────────────────────────────┐
│ ●运行中  [📖 容量巡检]      已耗时 2m15s       │  ← 状态点+文案 / 剧本Chip / 已耗时
│ 本周 SRE 容量巡检报告生成                       │  ← 标题(独占一行)
│ ─────────────────────────────────────────── │
│ 手动 · adhoc   03-14 09:21       进入对话 →    │  ← 来源/类型 / 创建时间 / 进入对话(脚注分隔线)
└──────────────────────────────────────────────┘
```

- **人话状态**:状态点 + 文案映射:
  - `running`→"运行中"(蓝点脉冲动画) / `awaiting_human`→"待你介入"(橙点) / `delivered`→"已交付"(绿点) / `failed`→"失败"(红点) / `draft`→"准备中"(灰点) / `blocked`→"阻塞"(红点) / `pending_trigger`→"等待触发"(灰点) / `closed`→"已关闭"(灰点)
  - 只有 `running` 点做呼吸动画,其余静态 — 视觉焦点天然落在"需要看"的卡。
- **已耗时**:`running` 状态从 `started_at` 算 `now - started_at`。前端 `setInterval` 每秒更新,仅当当前过滤组里有 running 任务时开。`started_at` 缺失则不显示。非 running 不显示耗时(running 完成后保留"耗时 Xm Xs"的最终值可选,本期不显示)。
- **剧本 Chip**:props `playbooks: {playbook_id, playbook_name}[]` 透传进 rail,卡片按 `task.playbook_id` 本地查 `playbook_name`。无 `playbook_id` 不显示 Chip。
- **标题**:读 `task.title`(§3.2 后端写回,轮询拉到即变)。
- **来源/类型**:`triggered_by` · `type`。
- **创建时间**:`gmt_created` → `MM-DD HH:mm`。
- **进入对话**:脚注分隔线右侧,保留现有 `onEnterConversation(taskId)`。

**介入请求卡**:淡琥珀底(`#fffbeb`/对应 `--ws-attention-light`),跟普通任务区分。现有 `interventions` 数据走这条样式。

**最小 `Task` 类型**(任务栏内定义,不抽共享):
```ts
interface Task {
  id: number; title: string; status: string;
  type?: string; triggered_by?: string;
  playbook_id?: number;
  started_at?: string; gmt_created?: string; gmt_modified?: string;
}
```

**空态**:每个 Tab 无任务时显示带引导文案的空态(如失败 Tab:"没有失败的任务 / 目前的任务都跑通了。"),非干瘪"暂无"。

### 3.5 发起校验(§4a)

**改动文件**:`web/src/app/workspaces/detail/agent-workspace-input.tsx`(前端)、`agent_chat.py`(后端兜底)。

- 前端 `AgentWorkspaceInput`:选了 `playbookCommand` 但 `text` 为空时,禁用发送按钮,输入框下提示"选了剧本要写任务目标 — 剧本只指定资源/能力,目标由你定"。没选剧本 = 大厅对话,不受限。
- 后端 `aggregation_chat` 的 `playbook_command` 分支(§3.1):`_user_text` 为空时不创建任务,回错误 vis 提示。双保险。

### 3.6 轮询刷新机制(§4b)

**改动文件**:`scene-workspace-shell.tsx`。替代行不通的事件推送。

- 现状(保留):`task_created` 事件调 `onRefreshLists` — 仍在用且仍工作(发起那一刻搭聊天 SSE 流)。
- 新增 `useEffect`(依赖 `tasks`):当列表里有 `running`/`pending_trigger`/`blocked`/`awaiting_human`/`draft` 状态的任务时,起 `setInterval(onRefreshLists, 4000)`;无任何活跃任务时清除定时器。组件卸载/切走清定时器。
- 刷新时序:发起 → `task_created` 立即刷 → 后台 `run_task` 跑起 → 4s 轮询拉到 `running` → 卡片"运行中+已耗时" → 跑完拉到终态 → 无活跃任务后轮询自动停。
- 轮询间隙 4s(取中 3~5s),可调。无后端事件架构改动,无空转。

## 4. 改动文件清单

**后端(2 文件)**:
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/_task_creator.py` — `create_task_from_tool` 创建后 detached `start`+`run_task`;新增 `_summarize_task_title` helper + detached 标题协程;签名加 `model_name`。
- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` — `playbook_command` 分支透传 `model_name`;`_user_text` 为空时拒绝创建。

**前端(4 文件)**:
- `web/src/app/workspaces/detail/scene-task-rail.tsx` — Tab 过滤、卡片重排、人话状态、已耗时定时器、空态、最小 `Task` 类型;接收 `playbooks` props。
- `web/src/app/workspaces/detail/scene-workspace-shell.tsx` — 透传 `playbooks` 给 rail;新增轮询 `useEffect`。
- `web/src/app/workspaces/detail/scene-workspace.css` — 方向 B 卡片样式(用 `--ws-*` token)。
- `web/src/app/workspaces/detail/agent-workspace-input.tsx` — 选剧本空文本时禁用发送 + 提示。

**不动**:`tasks/client.tsx`、`scene-space.tsx`、`TaskResponse` schema、`TaskEntity` 列、workspace 事件架构、`playbook_runtime.run_task` 调度逻辑。

## 5. 风险与取舍

- **detached 协程异常隔离**:`run_task` 与标题协程都用 `asyncio.create_task` + `try/except`,任一失败不影响已返回的 SSE 和对方。但 detached 协程的未捕获异常需在协程内兜底日志,避免静默丢失 — 实现时确保每个 detached 协程最外层包 `try/except` 记日志。
- **轮询 4s 延迟**:状态变化最坏 4s 才反映到任务栏。可接受(非实时控制场景)。无活跃任务后自动停,避免空转。
- **标题总结额外 LLM 调用**:每次发起任务多一次轻量 LLM 调用。失败保留占位,不阻塞任务。
- **本期能力边界**:`playbook_name` 本地查(无后端字段)、失败原因不存(只显状态)、交付物计数不显示(留详情卡)。这些是有意的 surgical 取舍,避免漫到 schema/事件架构。后续如需可在独立 spec 推进。
- **`model_name` 透传**:`create_task_from_tool` 签名变更是从 chat 路径调用的内部函数,调用点少(仅 `agent_chat.py` playbook_command 分支),影响面可控。

## 6. 不做(YAGNI)

- 不抽共享 `Task` TS 类型(只在 rail 内定义最小类型)。全页表/详情卡仍各用各的内联类型。
- 不新建 workspace 事件持久化/订阅通道(轮询足够)。
- 不加 `task_status_changed`/`task_title_updated` 事件类型(后台任务无推送通道,加了也到不了浏览器)。
- 不做失败原因存储/`fail_reason` 列。
- 不做交付物批量计数端点/`artifact_count` 字段。
- 不改 `TaskResponse` schema、`TaskEntity` 列、`playbook_runtime` 调度。
- 标题总结不做重试、不做流式。