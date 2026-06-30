# 场景空间对话系统增强 — 设计文档

**日期**: 2026-06-30
**主题**: 会话管理后端化 + 任务/空间上下文区分 + 空间 Agent 工具集注入
**前置**: 2026-06-29-scenario-workspace-product-form-design.md（P0 已完成）

## 1. 背景与目标

P0 完成后场景空间已有 Lobby（空间大厅）+ Workbench（任务工作台）+ 物化链路 + SSE 事件流。但当前对话系统存在四个缺口：

1. **会话与任务不隔离**：Lobby 与 Workbench 共用一个 convUid（localStorage 持久化），任务执行日志串台到大厅历史
2. **无会话管理 UI**：用户不能查看/切换/重置会话，convUid 只存在浏览器 localStorage，换设备即丢
3. **convUid 映射游离**：后端已有 `WorkspaceConversationLink` 表 + 3 个 endpoint + DAO + service 方法，但前端完全没用
4. **Agent 不能控制空间**：当前 `_inject_workspace_context` 只注入 system_prompt 摘要 + 物化只读资源（MCP/datasource/skill/kb/app/llm），Agent 无法 list_tasks / create_task / send_delivery / bind_resource / publish_asset

**目标**：让场景空间 Agent 既能"了解"空间（已部分实现），又能"控制"空间（新做），且区分空间级与任务级两种上下文。

## 2. 核心设计原则

> **空间 = 一组资源 + 权限 + 工具集合**。同一空间下，任务上下文 vs 非任务上下文加载的内容不同。
>
> **任务模式更干净简单**：Workbench 只挂当前任务相关上下文与工具，不挂空间全局操作工具；Lobby 挂空间全局视角。

注入差异矩阵：

| 注入项 | Lobby (task_id=NULL) | Workbench (task_id=N) |
|---|---|---|
| system_prompt 摘要 | 空间身份/成员/资源/最近任务/最近资产 | **仅** current_task 详情 + task_artifacts + task_interventions（不带空间全量信息） |
| dynamic_resources | 空间级绑定资源（已有 materializer） | 同空间级（资源仍属空间） |
| 读工具 | 7 个空间级只读工具 | 3 个任务级只读工具 |
| 写工具 | 5 个空间级写工具 | 3 个任务级写工具 |
| 权限 | 起任务/发空间交付/绑资源/publish asset | 仅限本 task：提交 artifact / 更新本 task 状态 / 为本 task 请求 intervention |

**关键原则**：
- Workbench 模式**不挂** `list_tasks` / `create_task` / `bind_resource` / `list_workspace_assets` / `get_workspace_growth` 等空间级工具——任务模式下 Agent 视野应聚焦本任务，不被空间全局能力干扰
- Lobby 模式**不挂** `submit_artifact_for_task` / `update_task_status` / `request_intervention` / `get_current_task_detail` 等任务级工具——大厅无任务上下文，不能"代表任务"操作
- 上下文摘要同样精简：Workbench 的 system_prompt 不拼空间成员/最近任务/最近资产，只拼 current_task + task_artifacts + task_interventions
- `build_workspace_toolkit(system_app, workspace_id, user_id, task_id=None)` 的 task_id 参数决定加载**哪套**（不是叠加）工具

## 3. 架构总览

```
┌─ Workspace ─────────────────────────────────────────────────────┐
│  default_agent_app_code = "chat_normal"  (or override)           │
│  conv_links[]  ← WorkspaceConversationLink 表 (已有, 扩展)       │
│    ├─ conv_uid_lobby   task_id=NULL   is_current=true  ← Lobby   │
│    ├─ conv_uid_task_42 task_id=42     (runtime 也用这个)          │
│    └─ conv_uid_task_43 task_id=43                               │
│                                                                  │
│  Agent (chat_normal) 执行时 ext_info 注入 (基于 task_id 互斥区分):   │
│    1. workspace_context (已有, build_workspace_context, 按 mode 精简) │
│       Lobby: 空间身份/成员/资源/最近任务/最近资产                     │
│       Workbench: 仅 current_task + task_artifacts + task_interventions │
│    2. materialized dynamic_resources (已有, 空间级资源两模式都注入)   │
│    3. workspace_control_tools (新, WorkspaceControlAgent, 互斥加载):  │
│       Lobby: 7 空间级读 + 5 空间级写                                  │
│       Workbench: 3 任务级读 + 3 任务级写                              │
│       写工具内部 → intervention_service.create() → SSE 事件           │
│       → 前端 VisConfirmCard → 用户 resolve → 后端执行写操作           │
│       → 结果作为新 human 消息送回同一 conv_uid 下一轮                  │
└──────────────────────────────────────────────────────────────────┘
```

## 4. 详细设计

### 4.1 会话管理后端化（#1 + #3）

#### 4.1.1 数据模型扩展

`WorkspaceConversationLinkEntity` 新增列：

```python
# packages/derisk-serve/src/derisk_serve/workspace/models/models.py
class WorkspaceConversationLinkEntity(Model):
    # ... 已有字段 ...
    is_current = Column(Boolean, nullable=False, default=False, index=True)
    title = Column(String(255), nullable=True)  # 用户可重命名，默认 "lobby" 或 "task_{id}"
```

`InterventionEntity.task_id` 改为可空（已有 `workspace_id` 非空即可定位）：

```python
# packages/derisk-serve/src/derisk_serve/intervention/models/models.py
class InterventionEntity(Model):
    task_id = Column(Integer, nullable=True, index=True)  # was: nullable=False
```

迁移脚本：`assets/migrations/workspaces/add_conv_link_is_current.sql`、`assets/migrations/interventions/allow_null_task_id.sql`。

#### 4.1.2 后端 service + endpoint

`WorkspaceService` 新增方法：

```python
def get_current_conversation(
    self, workspace_id: int, user_id: int,
) -> Optional[Dict[str, Any]]:
    """返回当前用户的当前会话 link，无则 None。"""

def set_current_conversation(
    self, workspace_id: int, user_id: int, conv_uid: str,
) -> Dict[str, Any]:
    """把同 workspace+user 的其它 link 置 is_current=False，目标置 True。
    若目标 link 不存在则按 conv_uid 查找并更新（不创建）。"""

def rename_conversation(
    self, conv_uid: str, title: str,
) -> Dict[str, Any]:
    """更新 link.title。"""
```

`WorkspaceConversationLinkDao` 对应实现 `get_current(workspace_id, user_id)` 和 `set_current(workspace_id, user_id, conv_uid)`（事务内更新）。

新 endpoint（`packages/derisk-serve/src/derisk_serve/workspace/api/endpoints.py`）：

- `GET /workspaces/{workspace_id}/conversations/current?user_id={user_id}` → 当前会话 link 或 null
- `POST /workspaces/{workspace_id}/conversations/set-current` body=`{conv_uid, user_id}` → 设置当前
- `PATCH /conversations/{conv_uid}/rename` body=`{title}` → 重命名

`link_conversation` 修改：当 workspace+user 下无 is_current=True 时，新 link 自动置 is_current=True。

#### 4.1.3 前端流程

`web/src/app/workspaces/detail/client.tsx`：移除 localStorage 逻辑，改为：

```ts
const [convUid, setConvUid] = useState<string>('');

useEffect(() => {
  if (!workspaceId) return;
  // 1. 查当前会话
  getCurrentConversation(workspaceId).then(res => {
    const current = res?.data?.data;
    if (current?.conv_uid) { setConvUid(current.conv_uid); return; }
    // 2. 无则创建 + link + set_current
    createConversation({ workspace_id: workspaceId, app_code: appCode })
      .then(r => {
        const uid = r?.data?.data?.conv_uid;
        if (!uid) return;
        linkConversation({ workspace_id: workspaceId, conv_uid: uid, user_id, title: 'lobby' });
        setCurrentConversation(workspaceId, { conv_uid: uid, user_id });
        setConvUid(uid);
      });
  });
}, [workspaceId, appCode, user_id]);
```

Workbench 不参与 is_current 竞争：直接用 `task.conv_session_id`（已有字段，task 创建时自动生成）。

#### 4.1.4 会话切换 UI（#2）

空间身份条右侧加 `<ConversationSwitcher workspaceId={workspaceId} userId={userId} currentConvUid={convUid} onSwitch={setConvUid} onReset={handleReset} />`：

- 下拉列出 `listConversations({workspace_id, user_id})` 返回的所有会话，按 gmt_modified 倒序
- 每条显示：`title` (默认 `lobby` 或 `task_{id}`) + 最后修改时间 + (可选) `task_id` Tag
- 当前会话高亮
- 底部三个按钮：
  - 「新会话」→ 创建新 conv_uid + link + set_current + 调 onSwitch
  - 「重命名」→ 弹 Modal 调 rename API
  - 「重置」→ 等价于「新会话」（旧会话保留在列表里可切回）

切换后：`setConvUid(newUid)` → ChatSession 重置 history → 调 `history-list?conv_uid=newUid` 拉新会话历史。

### 4.2 空间 Agent 工具集（#4）

#### 4.2.1 模块结构

新建 `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/`：

```
agent_tools/
  __init__.py
  read_tools.py        # 10 个只读 FunctionTool (7 空间级 + 3 任务级)
  write_tools.py       # 8 个写工具 (5 空间级 + 3 任务级)
  toolkit.py           # build_workspace_toolkit(system_app, ws_id, user_id, task_id=None) → List[FunctionTool]
  intervention_guard.py # 写工具公共护栏
  control_agent.py     # WorkspaceControlAgent: ConversableAgent 子类，挂载这些 tools
```

#### 4.2.2 工具清单

**空间级只读（7 个，仅 Lobby / task_id=NULL 时注册）**：

| 工具名 | 参数 | 调用 |
|---|---|---|
| `list_tasks` | `status?: str, limit?: int` | `TaskService.list_tasks(TaskListFilter(workspace_id, status, limit))` |
| `get_task` | `task_id: int` | `TaskService.get_by_id` |
| `list_artifacts` | `task_id?: int, limit?: int` | `ArtifactService.list_artifacts` |
| `list_deliveries` | `task_id?: int, limit?: int` | `DeliveryService.list_deliveries` |
| `list_workspace_resources` | (无) | `WorkspaceService.list_resources` |
| `list_workspace_assets` | `limit?: int` | `AssetService.list_assets` |
| `get_workspace_growth` | (无) | `WorkspaceService.get_growth` |

**任务级只读（3 个，仅 Workbench / task_id=N 时注册）**：

| 工具名 | 参数 | 调用 |
|---|---|---|
| `get_current_task_detail` | (无) | `TaskService.get_by_id(task_id)` |
| `list_task_artifacts` | (无) | `ArtifactService.list_artifacts(task_id=task_id)` |
| `list_task_interventions` | `status?: str` | `InterventionService.list_interventions(task_id=task_id)` |

**空间级写工具（5 个，仅 Lobby 时注册，每个内部走 intervention）**：

| 工具名 | 参数 | 调用 |
|---|---|---|
| `create_task` | `title: str, playbook_id: int, context?: dict` | intervention → `TaskService.create` |
| `send_delivery` | `channel: str, content: str, category?: str` | intervention → `DeliveryService.send` (task_id=NULL) |
| `bind_resource` | `type: str, name: str, physical_ref: str, access_mode?: str` | intervention → `WorkspaceService.add_resource` |
| `publish_asset` | `artifact_id: int, name: str, description?: str, tags?: list` | intervention → `AssetService.publish` |
| `trigger_playbook` | `playbook_id: int, context?: dict` | intervention → 等价 create_task + run_task |

**任务级写工具（3 个，仅 Workbench 时注册）**：

| 工具名 | 参数 | 调用 |
|---|---|---|
| `submit_artifact_for_task` | `type: str, title: str, content: str` | intervention → `ArtifactService.create(task_id=task_id)` |
| `update_task_status` | `status: str, note?: str` | intervention → `TaskService.update({id: task_id, status})` |
| `request_intervention` | `question: str, context?: dict` | `InterventionService.create(task_id=task_id, type='review')` |

**互斥原则**：Lobby 与 Workbench 工具集**不重叠**——同一 Agent 在不同上下文看到的工具列表完全不同，确保任务模式干净聚焦。

#### 4.2.3 写工具 intervention 流程（非阻塞）

```python
# write_tools.py 示意
def make_create_task_tool(system_app, workspace_id, user_id, task_id=None):
    async def create_task(title: str, playbook_id: int, context: dict = None) -> str:
        intervention_service = system_app.get_component(
            INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
        )
        intervention = intervention_service.create(InterventionRequest(
            workspace_id=workspace_id,
            task_id=task_id,  # 可空
            type="agent_tool_call",
            requested_by=f"agent:user_{user_id}",
            question_json=json.dumps({
                "tool": "create_task",
                "args": {"title": title, "playbook_id": playbook_id, "context": context},
            }),
            context_json=json.dumps({"workspace_id": workspace_id, "task_id": task_id}),
        ))
        # 通过 SSE 推 intervention_triggered 事件
        # Agent 收到下面的返回字符串后向用户转述
        return (
            f"已提交 create_task 请求 (intervention #{intervention.id})。"
            f"等待用户确认后执行。请告知用户去确认。"
        )
    return FunctionTool(
        name="create_task",
        func=create_task,
        description="在当前空间创建一个新任务。需要用户确认。",
        args={
            "title": ToolParameter(type="string", name="title", description="任务标题", required=True),
            "playbook_id": ToolParameter(type="integer", name="playbook_id", description="剧本 ID", required=True),
            "context": ToolParameter(type="object", name="context", description="任务上下文", required=False),
        },
    )
```

#### 4.2.4 resolve 后回灌

新增 `InterventionService.execute_resolved(intervention_id)`：

```python
def execute_resolved(self, intervention_id: int) -> Dict[str, Any]:
    """用户 resolve intervention 后，根据 question_json.tool 执行真正的写操作。
    返回 {success: bool, result: Any, message: str}。"""
    entity = self.get_by_id(intervention_id)
    question = json.loads(entity.question_json)
    tool_name = question["tool"]
    args = question["args"]
    # 路由到对应 service
    if tool_name == "create_task":
        result = task_service.create(TaskRequest(...))
    elif tool_name == "send_delivery":
        ...
    # 把结果作为新 human 消息送回 conv_uid
    self._post_message_back(entity.conv_uid, f"[intervention #{intervention_id} resolved] {tool_name} executed: {result}")
    return {"success": True, "result": result}
```

新 endpoint：`POST /interventions/{id}/resolve-and-execute` body=`{decision, distillation?, linked_asset_id?, resolved_by_user_id}` → 调 `resolve` + `execute_resolved`。

注意：intervention 表当前没有 `conv_uid` 字段——需要从 `WorkspaceConversationLink` 反查。`InterventionEntity` 新增 `conv_uid` 列（写工具创建 intervention 时填入当前会话的 conv_uid），方便 resolve 后回灌。

#### 4.2.5 工具挂载 — WorkspaceControlAgent

新建 `WorkspaceControlAgent(ConversableAgent)`：

```python
class WorkspaceControlAgent(ConversableAgent):
    """挂载空间控制工具的子 Agent。通过 extra_agents 注入到 aggregation_chat。
    工具集按 task_id 互斥：Lobby 模式挂空间级（7读+5写），Workbench 模式挂任务级（3读+3写）。"""
    def __init__(self, system_app, workspace_id, user_id, task_id=None):
        tools = build_workspace_toolkit(system_app, workspace_id, user_id, task_id)
        super().__init__(
            name="workspace_control" if not task_id else f"workspace_control_task_{task_id}",
            llm_config=...,  # 用父 Agent 的 llm
            function_map={t.name: t.execute for t in tools},
        )
```

注入路径（`_inject_workspace_context` 末尾追加）：

```python
# 已有: ext_info["extra_agents"] 已扩展 materialized.extra_agents
# 新增:
if ext_info.get("workspace_id"):
    control_agent = WorkspaceControlAgent(
        agent_chat.system_app,
        int(workspace_id),
        user_id=ext_info.get("user_id"),
        task_id=int(task_id) if task_id else None,
    )
    existing_extra = ext_info.get("extra_agents") or []
    existing_extra.append(control_agent)
    ext_info["extra_agents"] = existing_extra
```

#### 4.2.6 build_workspace_context 精简（Workbench 模式）

当前 `build_workspace_context` 在 task_id 非空时仍会拼空间全量信息（workspace/members/resources/recent_tasks/recent_assets）。改为：

- task_id=NULL（Lobby）：保持当前行为，拼空间身份/成员/资源/最近任务/最近资产
- task_id=N（Workbench）：**不拼** workspace/members/recent_tasks/recent_assets，只拼 current_task + task_artifacts + task_interventions

实现：`render_workspace_context_summary(ctx, mode="lobby"|"workbench")` 加 mode 参数。Workbench 模式下 ws=None / members=[] / recent_tasks=[] / recent_assets=[] 直接跳过对应 section。

#### 4.2.7 前端 VisConfirmCard 接入

`intervention_triggered` 事件流已经走通（P0 完成）。VisConfirmCard 已存在。改造点：

- `intervention_triggered` payload 增加 `tool_name` / `args` / `intervention_id` 字段
- VisConfirmCard 在 workspace 上下文下显示"Agent 提议执行：{tool_name}({args})"，按钮：「同意并执行」「拒绝」
- 同意 → 调 `POST /interventions/{id}/resolve-and-execute`
- 拒绝 → 调 `POST /interventions/{id}/abort`
- 两者的结果都通过 execute_resolved → _post_message_back 送回 conv_uid，前端在历史区看到 Agent 的后续回复

### 4.3 Workbench 任务隔离（#1）

`web/src/app/workspaces/detail/client.tsx` 改造：

- Lobby 用空间级 convUid（来自 is_current）
- Workbench 用 `task.conv_session_id`（直接从 task 详情拿，不走 is_current）

```tsx
{view === 'lobby' && <Lobby convUid={lobbyConvUid} ... />}
{view === 'workbench' && selectedTask && (
  <Workbench taskId={selectedTask.id} convUid={selectedTask.conv_session_id} ... />
)}
```

`task.conv_session_id` 来自 `TaskService.create` 自动生成的 uuid（已有逻辑），并已 link 到 workspace+task（已有逻辑）。前端只需在 task 详情接口里取这个字段。

Workbench 进入时若 `task.conv_session_id` 为空（老 task），fallback 到 lobbyConvUid 并打 warning 日志。

## 5. 数据流总览

### 5.1 Lobby 大厅对话 → 起任务

```
用户在 Lobby 输入 "帮我起一个 SRE 巡检任务"
  ↓
ChatSession.streamMessage → 后端 agent_chat
  ↓
_inject_workspace_context (task_id=NULL)
  → system_prompt 拼空间摘要
  → dynamic_resources 注入空间绑定资源
  → extra_agents 注入 WorkspaceControlAgent (task_id=NULL, 5 个空间级写工具)
  ↓
Agent 决定调 create_task(title="SRE 巡检", playbook_id=...)
  ↓
create_task tool 执行
  → InterventionService.create(workspace_id, task_id=NULL, type="agent_tool_call", question_json={tool, args})
  → SSE 推 intervention_triggered 事件
  → tool 返回 "已提交 create_task 请求 (intervention #N)，等待用户确认"
  ↓
Agent 把这句话告诉用户
  ↓
前端 VisConfirmCard 渲染卡片，用户点「同意并执行」
  ↓
POST /interventions/{N}/resolve-and-execute
  → TaskService.create → 生成新 task + conv_session_id + 自动 link
  → _post_message_back(conv_uid, "[intervention #N resolved] create_task executed: task #M created")
  ↓
下一轮 Agent 收到这条 human 消息 → 告诉用户 "已创建 task #M"
```

### 5.2 Workbench 任务对话 → 提交 artifact

```
用户在 Workbench (task_id=42) 输入 "把刚才生成的报告作为 artifact 提交"
  ↓
_inject_workspace_context (task_id=42)
  → system_prompt 仅拼 current_task + task_artifacts + task_interventions（精简模式，不带空间全量信息）
  → dynamic_resources 仍注入空间级绑定资源（资源属空间）
  → extra_agents 注入 WorkspaceControlAgent (task_id=42, 仅 6 个任务级工具: 3读+3写)
  ↓
Agent 调 submit_artifact_for_task(type="report", title="巡检报告", content="...")
  ↓
InterventionService.create(workspace_id, task_id=42, type="agent_tool_call", ...)
  → SSE intervention_triggered
  → tool 返回 "已提交，等待确认"
  ↓
VisConfirmCard 同意 → resolve-and-execute
  → ArtifactService.create(task_id=42, ...)
  → _post_message_back(task_42_conv_uid, "submit_artifact_for_task executed: artifact #K created")
  ↓
Agent 告诉用户 "已提交 artifact #K"
```

**注意**：Workbench 模式下 Agent **看不到** `list_tasks` / `create_task` / `bind_resource` 等空间级工具，不会被诱导去起任务或改空间资源；只看到本任务的精简上下文与任务级操作工具。

## 6. 测试策略

### 6.1 后端单测

- `tests/derisk_serve/workspace/test_conv_link_dao.py` — is_current / set_current / get_current
- `tests/derisk_serve/workspace/test_agent_tools.py` — 18 个工具的 happy path + intervention 流转
- `tests/derisk_serve/workspace/test_intervention_execute.py` — resolve-and-execute 路由 + 回灌
- `tests/derisk_serve/workspace/test_injection.py` — task_id=NULL vs task_id=N 的工具集互斥差异（Lobby 12 工具 / Workbench 6 工具，不重叠）

### 6.2 集成测试

- Lobby 全流程：输入 → Agent 调 create_task → intervention → resolve → task 创建 → 消息回灌
- Workbench 全流程：进入 → Agent 看 current_task → 调 submit_artifact_for_task → intervention → resolve → artifact 创建

### 6.3 前端

- ConversationSwitcher 渲染/切换/重置/重命名
- VisConfirmCard 在 workspace 上下文下渲染 tool_name/args
- 切换会话后 history 重拉

## 7. 风险与边界

1. **WorkspaceControlAgent 与父 Agent 的 llm_config 共享**：若父 Agent 没配 llm，子 Agent 调工具会失败。需 fallback 到默认 llm。
2. **intervention 回灌消息格式**：`_post_message_back` 用什么 role 写入 chat_history？建议 role=human（视作用户指令续接），前缀 `[system]` 区分。
3. **is_current 并发**：多端同时操作 set_current 可能错乱。DAO 层用事务 + 行锁。
4. **task.conv_session_id 为空的老 task**：Workbench fallback 到 lobbyConvUid，但日志 warning，建议后续跑迁移补全。
5. **写工具的 question_json 格式**：必须在 spec 里冻结 schema，前端 VisConfirmCard 按 schema 渲染。
6. **trigger_playbook 与 create_task 冗余**：trigger_playbook 实质是 create_task + 自动 run_task。保留两者，前者语义更明确（直接跑），后者只是建任务。

## 8. 不在本期范围

- 写工具的 RBAC（按 member.role 限制某些写工具）— P1
- 会话搜索 / 全文检索 — P1
- 任务级资源绑定（task 另绑资源，区别于空间级）— P2
- intervention 的 distillation 自动沉淀为 asset — P1（已有 intervention 表 distillation_json 字段，但自动沉淀逻辑未做）
- WorkspaceControlAgent 的工具调用审计日志 — P1

## 9. 验收标准

1. 进入 Lobby → 底部输入 "列一下空间里的任务" → Agent 调 `list_tasks` → 返回任务列表
2. 在 Lobby 输入 "起一个巡检任务" → Agent 调 `create_task` → VisConfirmCard 弹出 → 同意 → task 创建 → Agent 告知 task id
3. 进入 Workbench → 底部输入 "把当前结果作为 artifact 提交" → Agent 调 `submit_artifact_for_task` → VisConfirmCard → 同意 → artifact 创建
4. 切换会话 → history 重拉，看到不同会话的历史
5. 重置会话 → 新会话创建，旧会话仍可在列表里看到
6. 换浏览器登录同一空间 → 当前会话从后端取，不再依赖 localStorage
