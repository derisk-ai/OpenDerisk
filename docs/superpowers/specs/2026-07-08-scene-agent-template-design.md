# 场景空间 Agent 模板设计

**Goal:** 为场景空间（Scene Workspace）引入一个独立的 GptsApp Agent 模板，让场景空间助手拥有清晰的身份定义、工作逻辑、工具使用规范和输出风格，并能在每次对话时自动注入当前 workspace / task / playbook 等动态上下文。

**Architecture:** 新增内置 GptsApp `scene-workspace-agent`，沿用 `agent: BAIZE` 运行时（复用现有 ReAct 工具调用、vis_manus 布局、memory、intervention 能力），通过 `system_prompt_template` 固化静态身份与行为；动态部分继续由 `_inject_workspace_context` 在对话入口处注入。创建 workspace 时自动把 `default_agent_app_code` 指向该模板。

**Tech Stack:** Python (derisk-serve), JSON app definition, FastAPI chat endpoint, React/Next.js workspace page。

---

## 1. System Prompt 结构（参考 Claude Code 分层）

最终送入 LLM 的 system prompt 由 **静态模板** + **动态上下文** 拼接而成：

```
[静态块 1] 身份前缀
[静态块 2] 行为与工作逻辑
[静态块 3] 可用工具与调用时机
[静态块 4] 输出风格
[动态块 5] 当前场景上下文（workspace / task / playbook / tools）
```

### 1.1 身份前缀

```text
你是 OpenDerisk 场景空间助手（Scene Workspace Agent），当前工作空间的协作者。
你不是通用聊天助手；你的目标是理解用户在该场景空间中的工作目标，调用合适的工具推进任务，并把结果沉淀为可复用的资产或报告。
```

### 1.2 行为与工作逻辑

- **先理解上下文，再行动。** 每次收到用户消息，先结合下方的“当前场景上下文”判断用户处于 lobby 还是某个 task 详情页。
- **任务触发方式：**
  - 普通输入：自主判断用户意图，若需要走剧本则调用 `run_playbook_*` 或 `start_task` 创建任务。
  - `/剧本名 xxx` 前缀：直接匹配名为“剧本名”的 playbook 并创建任务。
- **工具调用原则：** 能用工具获取的事实不要靠推测；调用工具前简要说明意图；工具失败时告知用户并给出替代方案。
- **确认原则：** 删除/归档/发送外部分发/修改生产配置等破坏性操作，必须显式请求用户确认。
- **诚实原则：** 不知道就直说，不要编造数据或假设 playbook 行为。

### 1.3 可用工具与调用时机

```text
# Workspace 读工具（lobby / task 均可用）
- list_tasks: 列出当前空间任务，用于了解背景。
- get_task_info: 获取指定任务详情。
- list_artifacts / list_deliveries: 列出任务交付物/分发记录。
- list_playbooks / get_playbook_detail: 查看空间默认剧本及声明。
- list_workspace_members: 获取成员与权限。

# Workspace 写工具
- start_task: 用户确认目标后，创建并启动一个任务。
- create_intervention: 需要人工确认/审批时发起介入。
- publish_asset: 把产出物发布为空间资产。

# Playbook 工具
- run_playbook_by_name / run_playbook_by_id: 明确走某个剧本时调用。
```

### 1.4 输出风格

```text
- 简洁行动导向：先判断是否需要工具，需要则直接调用，不要长篇解释。
- 使用中文回复用户。
- 在 vis_manus 左侧面板中，重要结论优先，过程性内容可折叠或仅通过工具调用展示。
- 不要重复渲染完整历史消息。
```

### 1.5 动态上下文（由运行时注入）

由 `_inject_workspace_context` 及新增渲染函数生成，包含：

- **Workspace 基础信息**：名称、场景类型、成员、绑定资源（复用现有 `render_workspace_context_summary`）。
- **可用 Playbook 列表**：名称 + 场景类型 + 触发方式，方便 Agent 做意图匹配。
- **当前 Task 详情**：进入 task 详情页时注入。
- **进行中任务列表**：Dashboard 视图下注入，便于 Agent 了解活跃工作。
- **可用工具清单摘要**：把当前 mode（lobby/workbench）下实际挂载的工具名与用途列出。

---

## 2. 数据流

```text
1. 用户打开场景空间页面
   -> 前端读取 workspace.default_agent_app_code
   -> 若为空则前端回退到 'main'（后端创建时已自动绑定）

2. 用户发送消息
   -> /chat/completions 收到请求，ext_info 含 workspace_id / task_id / app_code
   -> aggregation_chat 加载 gpts_app（scene-workspace-agent）
   -> gpts_app.system_prompt_template 写入 agent profile

3. 动态注入
   -> _inject_workspace_context 读取 workspace/task/playbook/tools
   -> 拼接静态模板 + 动态上下文 -> ext_info["system_prompt"]

4. LLM 调用
   -> Agent 按完整 system prompt 执行 ReAct 循环
   -> 工具调用通过 WorkspaceControlAgent / FunctionTool 落地
```

---

## 3. 组件与文件变更

### 3.1 新增文件

- `packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/scene-workspace-agent.json`
  - `app_code`: `scene-workspace-agent`
  - `app_name`: `场景空间助手`
  - `agent`: `BAIZE`
  - `team_mode`: `auto_plan`
  - `layout.chat_layout.name/reuse_name`: `vis_manus`, `incremental: true`
  - `system_prompt_template`: 第 1 节静态块（不含动态占位）。

- `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/__init__.py`
- `packages/derisk-serve/src/derisk_serve/workspace/agent_prompts/scene_agent_prompt.py`
  - `SCENE_AGENT_STATIC_PROMPT`: 静态 system prompt 字符串。
  - `render_scene_dynamic_context(ctx, mode) -> str`：渲染 playbook 列表、进行中任务、当前任务、工具清单。

### 3.2 修改文件

- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`
  - `_inject_workspace_context` 调用新增 `render_scene_dynamic_context`，把动态块追加到 `system_prompt`。

- `packages/derisk-serve/src/derisk_serve/workspace/service/service.py`
  - `WorkspaceService.create`：创建 workspace 时，若 `default_agent_app_code` 为空，自动设置为 `scene-workspace-agent`（失败时打 warning，不阻塞创建）。

- `packages/derisk-serve/src/derisk_serve/building/app/service/service.py`
  - 无变更，`load_define_app` 会自动加载新 JSON。

- `web/src/app/workspaces/detail/client.tsx`
  - 保持 `appCode = ws?.default_agent_app_code || 'main'`；后端已确保新空间有值。

### 3.3 向后兼容

- 旧 workspace 若已有 `default_agent_app_code` 则保持不变。
- 若 `scene-workspace-agent` 应用尚未被系统加载（例如旧环境未重启），回退到现有 `main`/`chat_normal` 行为。

---

## 4. 测试策略

- **单元测试**
  - 断言 `scene-workspace-agent.json` 可通过 `ServeRequest.from_dict` 解析。
  - 断言 `render_scene_dynamic_context` 在 lobby 模式下包含 playbook 列表和进行中任务；在 workbench 模式下包含当前 task 详情。
  - 断言 `WorkspaceService.create` 在无显式 `default_agent_app_code` 时写入 `scene-workspace-agent`。

- **集成测试**
  - 调用 chat endpoint 携带 `workspace_id`，验证最终 `ext_info["system_prompt"]` 同时包含静态模板和动态上下文。
  - 验证 `_serialize_extra_for_db` 不会因新模板引入不可序列化对象。

---

## 5. 非目标 / 后续迭代

- **本次不做 BAIZE 通用 prompt 框架重构。** 只在场景空间模板上验证 Claude Code 式分层；若效果好，再考虑把分层能力抽象给所有 Agent。
- **本次不做 prompt 缓存分层。** 静态块和动态块暂时直接拼接；后续若 token 成本敏感，再按 cache scope 拆分。
- **本次不新增 Agent 子类。** 继续基于 BAIZE 运行时，通过 system prompt 和动态注入实现场景化。
