# 场景空间 AgentWorkspace 输入与渲染设计

日期: 2026-07-09
状态: Approved (待 spec review)

## 背景

场景空间右侧的 Agent 空间当前存在两套半成品实现,均不满足需求:

1. `agent-workspace.tsx`(活路径,被 `scene-workspace-shell.tsx:185` 挂载):
   - 输入框是 `agent-chat-input.tsx` 的简版 `AgentChatInput` —— 一个 60 行的 antd `Input.TextArea` + 发送/重试按钮,无文件拖拽、无模型选择、无 `/` 剧本命令。
   - 输出区是 `AgentProcessPanel` —— 纯文本步骤列表(只渲染 `AgentStep.title` + 状态图标),不渲染 markdown/vis,也不接 vis_manus。
   - 数据流是 `useSceneAgentChat`,`useChat().chat` → `POST /api/v1/chat/completions`,但只发 `user_input: string` + `conv_uid/workspace_id/task_id`,不发 `chat_in_params/model_name/ext_info.vis_render`。

2. `scene-agent-chat.tsx`(死代码,无任何 import):
   - 挂 `<ChatSession minimal hideRightPanel forceVisRender="vis_manus" inputSlot=...>`,复用 ManusChatContent 左面板渲染,但 ManusChatContent 内部又自渲染了一个 `UnifiedChatInput`,导致"中间多一个对话框"。
   - 输入框 `AgentChatInputSlot` 走 `ChatContentContext.handleChat`,非独立。

后端侧,场景 Agent(workspace_id 路径)走 `gpt_vis_all` → `GptVisConverter`,产出 markdown vis-string;vis_manus 协议数据结构(`vis_manus_protocol.py`)完整存在但未接此路径。SSE 流上的 structured step 事件(`task_created/context_loaded`)只带标量元数据,无 vis 渲染内容。

后端 `/api/v1/chat/completions`(`api_v1.py:394` / `ConversationVo`)已支持多模态 `user_input`、`chat_in_params`、`model_name`、`ext_info.workspace_id/task_id`,**前后端多模态/资源/模型对接无需后端改动**。

## 目标

`AgentWorkspace` 是场景空间里 Agent 的独立输出/指挥空间,定位为:
- 输入框 = 标准多模态(文本 + 文件拖拽 + 模型选择 + `/` 唤起剧本命令),独立组件,不依赖 `ChatContentContext`。
- 输出区 = 渲染结构化 VIS(planning / steps / vis 片段),由后端新增 `scene_agent_workspace` converter 产出;步骤卡片可联动(点击指挥场景空间内容变化)。
- 架构上保留独立渲染管线,不与首页 ChatSession 耦合,支持后续持续演化(更多独立内容)。

非目标(本期):
- 输入框不做工具栏 / skills / MCP / temperature / max_tokens。
- 步骤卡片与场景空间的联动交互第一期只留 `onStepClick` 接口,shell 侧接入可后续。
- 不做"结构化 step 事件队列发富 payload"方案(已评估并放弃,改用 converter 产物通道)。

## 数据协议(后端 converter 产物 ↔ 前端渲染 schema)

`SceneAgentWorkspaceConverter`(render_name = `scene_agent_workspace`)产出结构化对象,作为 `vis` 内容经 SSE 流式下发,前端 `use-chat.ts` 路由后由独立 vis 渲染器消费。

```python
{
  "render_name": "scene_agent_workspace",
  "planning": {                      # 可选
    "goal": str,
    "steps": [{ "id": str, "title": str, "status": "pending|running|done|failed" }]
  },
  "execution": [                     # 执行步骤流,增量下发
    {
      "id": str,
      "type": "tool_call|thinking|artifact|delivery",
      "title": str,
      "status": "running|done|failed",
      "action": str | None,          # 工具名
      "action_input": dict | None,   # 工具参数
      "output": str | None,          # 结果/产物描述(markdown 片段)
      "artifact": { "file_path": str, "mime_type": str, "preview_url": str | None } | None,
      "vis": <vis片段> | None        # 嵌套 vis 组件内容(可选)
    }
  ],
  "summary": str | None
}
```

约定:
- 字段命名复用 `packages/derisk-core/src/derisk/vis/vis_manus_protocol.py`(`action`/`action_input`/`output`、`ManusArtifactItem`)。
- 流式:converter 在 `_chat_messages` 迭代中增量产出;前端按 `execution[]` 追加,按 `id` 去重并更新状态。
- 场景 Agent 路径(`agent_chat.py` 存在 `workspace_id`)默认 `render_name = scene_agent_workspace`,不走 `gpt_vis_all`。

## 后端 converter 实现

- 新文件 `packages/derisk-ext/src/derisk/vis/derisk/scene_agent_workspace_converter.py`,注册 render_name `scene_agent_workspace`。
- 参照 `DeriskIncrVisManusConverter`(`derisk_vis_manus_converter.py:113-148`)的结构;从 `agent-messages` vis 标签 + `_messages_to_agents_vis` 抽取 action_report(`action`/`action_input`/`observation`),组装为 `execution[]`;planning 取自 planning vis 片段(若有)。
- `agent_chat.py` 的 render_name 解析:有 `workspace_id` 时优先 `scene_agent_workspace`,回退现有逻辑(约 `agent_chat.py:1076-1081`)。
- 剧本命令模式入口:workspace 路径开头检测 `chat_in_params` 的 `playbook_command`,命中则走 `start_task`(playbook + `user_input` 作任务主题),跳过 LLM 回合,发 `task_created` 事件(复用现有 `start_task` 工具 + `task_created` 事件链,`write_tools.py:54-63`)。

## 前端 useSceneAgentChat 扩展

- 当前 `use-scene-agent-chat.ts` 只把流消息喂 `parseAgentSteps`(产出 `AgentStep[]` 的 title)。
- 扩展:同时消费流上 `scene_agent_workspace` 结构化 `vis` 产物(经 `use-chat.ts:108-135` 路由),产出本地状态 `workspaceView: { planning, execution[], summary }`。
- `send` 类型扩展:接受 `{ text, resources, model, playbookCommand? }`,对齐标准载荷(见输入框节),不再只发 string。
- 保留 `onWorkspaceEvent` 透传(用于 `task_created` 等结构化事件)。

## 独立 vis 渲染器(AgentWorkspaceRenderer)

- 新文件 `web/src/app/workspaces/detail/agent-workspace-renderer.tsx`,**不依赖 `ChatContentContext`**。
- 按 `execution[]` 渲染可联动卡片:
  - 状态图标 + title,可折叠 `action_input`/`output`(markdown)。
  - `artifact` 渲染产物预览(`file-preview.tsx`),`vis` 嵌套渲染。
  - planning 区(若有)渲染计划步骤概览。
- markdown/vis 渲染:复用 `GPTVis` + `markdownComponents`;核实 `markdownComponents`/`VisWrapper` 对 `ChatContentContext` 的依赖,依赖的部分抽取无 Context 版本(只渲染,不读全局 history/appInfo)。
- `onStepClick(step)` 透出 → shell 可指挥场景空间内容变化(第一期留接口)。
- 替换 `AgentProcessPanel`;`AgentProcessPanel` 退役。

## 独立多模态输入框(AgentWorkspaceInput)

- 新文件 `web/src/app/workspaces/detail/agent-workspace-input.tsx`,**不依赖 `ChatContentContext`**。
- 第一期能力:文本(TextArea,回车发送 / shift+回车换行)+ 文件拖拽/选择上传 + 模型选择 + 重试 + `/` 唤起剧本选择。
- 复用积木(均无 Context 依赖):
  - API:`postChatModeParamsFileLoad`(`request.ts:271`)、`getModelList`(`request.ts:364`)。
  - utils:`parseResourceValue`/`transformFileUrl`、`getFileIcon`/`formatFileSize`。
  - 展示:`file-preview.tsx`。
  - 从 `unified-chat-input.tsx` 抽纯逻辑:`UploadingFile` 接口(L67)、`ParsedResourceItem`(L88)、`getAcceptTypes`(L100)、`handleFileUpload` 纯核心(L803-931,去掉 L938-947 的 `setChatInParams`/`setResourceValue` 写回,改用本地 `resources[]`)、`handleDrop`/`handlePaste`(L1686-1721)、模型列表过滤(L314-339)。
- 本地状态:`resources[]` 单数组替代 UnifiedChatInput 的 `chatInParams + resourceValue` 双存储。
- `/` 唤起剧本:输入 `/` 弹出剧本列表(来自 shell `playbooks` props),选中后组装 `playbook_command` 的 `chat_in_params` 项 + `user_input` 主题文本,发出。
- send 载荷(对齐 `chat-session.tsx:306-320`),经 `useChat().chat` 发 `/api/v1/chat/completions`:
  - `user_input`:有资源时多模态 `{ role:'user', content:[...resources, {type:'text', text}] }`,否则纯 string。
  - `chat_in_params`:[...资源 param_type=resource, ...{param_type:'model', param_value:model}(若选模型), ...{param_type:'playbook_command', sub_type:'playbook', param_value:JSON({playbook_id,playbook_name})}(若剧本命令)]。
  - `model_name`:选中模型(顶层)。
  - `ext_info`:`{ vis_render:'scene_agent_workspace', workspace_id, task_id }`。
  - `app_code`、`team_mode`、`app_config_code`、`agent_version`。
- `agent-workspace.tsx` 的简版 `AgentChatInput` 替换为 `AgentWorkspaceInput`;`agent-chat-input.tsx` 退役。

## 剧本命令模式

- 前端:输入框 `/` 选中剧本 → `chat_in_params` 加 `{param_type:'playbook_command', sub_type:'playbook', param_value: JSON.stringify({playbook_id, playbook_name})}`,`user_input` 为用户输入的任务主题。
- 后端:workspace 路径入口检测 `chat_in_params` 含 `playbook_command` → 命令模式 → 用 playbook + `user_input` 主题触发 `start_task`(发 `task_created`),跳过 LLM 回合。
- 复用现有 `start_task` 工具与 `task_created` 事件,后端改动集中在入口分发,不新增工具。

## 清理

- 删除死代码 `scene-agent-chat.tsx`(`SceneAgentChat` 无引用,含 `AgentChatInputSlot`)。
- 删除 `agent-chat-input.tsx`(被 `AgentWorkspaceInput` 取代)。
- 删除 `AgentProcessPanel`(被 `AgentWorkspaceRenderer` 取代)。
- `use-scene-agent-chat.ts` 的 `parseAgentSteps` 路径:若 `scene_agent_workspace` converter 已覆盖结构化渲染,评估是否仍需保留(若 `task_created` 等事件仍走 `onWorkspaceEvent` 单独透传给 shell,则保留 hook 的事件透传,仅渲染改走 `workspaceView`)。

## 测试与验证

- 后端 converter 单测:给定 agent-messages(含 action_report),断言 `execution[]` 结构(`id/type/action/action_input/output/artifact`)正确;planning/summary 缺省时不崩。
- 前端 `useSceneAgentChat` 单测:喂 `scene_agent_workspace` vis 产物,断言 `workspaceView` 状态增量更新 + 按 `id` 去重。
- `AgentWorkspaceInput` 单测:
  - 文件拖拽 → `resources` 构造 + `chat_in_params.resource`。
  - `/` 唤起剧本 → `playbook_command` 载荷。
  - send 载荷完整性(多模态 `user_input` / `model_name` / `ext_info.vis_render`)。
- `AgentWorkspaceRenderer` 单测:`onStepClick` 触发;execution 增量更新去重;artifact 预览渲染。
- 验证标准:
  - 场景空间 Agent 空间输入框支持文本/文件/模型/`/`剧本。
  - 输出区按结构化 VIS 渲染步骤 + 产物。
  - 选中剧本 → 创建任务(出现 `task_created`,任务主题 = 用户输入)。