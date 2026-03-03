# Derisk 前后端 Agent 交互链路架构文档

> 最后更新: 2026-03-03

## 一、整体架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (Frontend)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │ V2Chat组件   │───>│ use-v2-chat  │───>│unified-chat  │───>│v2.ts API │  │
│  │ (UI渲染)     │    │   (状态Hook)  │    │   (服务层)    │    │ (HTTP)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ SSE (Server-Sent Events)
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API 层 (Backend)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                    POST /api/v2/chat (StreamingResponse)                     │
│                              │                                               │
│                    ┌─────────┴─────────┐                                     │
│                    │    core_v2_api    │                                     │
│                    │    (FastAPI路由)   │                                     │
│                    └─────────┬─────────┘                                     │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          调度执行层 (Core_v2)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │ Dispatcher   │───>│   Runtime    │───>│   Adapter    │───>│  Agent   │  │
│  │ (任务调度)    │    │ (会话管理)    │    │ (消息转换)    │    │  (执行)  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、前端组件分析

### 2.1 组件层级结构

```
/web/src/components/v2-chat/index.tsx
│
├── V2Chat (主容器组件)
│   │
│   ├── 状态管理
│   │   ├── input - 用户输入
│   │   ├── session - 当前会话
│   │   └── messages - 消息列表
│   │
│   ├── 消息渲染组件
│   │   └── MessageItem
│   │       └── ChunkRenderer
│   │           ├── thinking - 思考过程 (蓝色卡片)
│   │           ├── tool_call - 工具调用 (紫色卡片)
│   │           ├── error - 错误提示 (红色Alert)
│   │           └── warning - 警告提示 (黄色Alert)
│   │
│   └── 交互控件
│       ├── TextArea - 输入框
│       ├── Send Button - 发送/停止按钮
│       └── Clear Button - 清空按钮
│
├── useV2Chat Hook ➜ /web/src/hooks/use-v2-chat.ts
└── UnifiedChatService ➜ /web/src/services/unified-chat.ts
```

### 2.2 Hook 与 Service 职责

| 文件 | 主要职责 |
|------|---------|
| `use-v2-chat.ts` | 管理 V2 会话状态、发送消息、停止流、处理消息回调 |
| `use-chat.ts` | 兼容 V1/V2 的双版本聊天 Hook，根据 agent_version 路由 |
| `unified-chat.ts` | 统一聊天服务，自动识别 V1/V2 并调用对应 API |
| `v2.ts` | V2 API 封装，包含 SSE 流处理 |

### 2.3 前端数据类型

```typescript
// 流式消息块
interface V2StreamChunk {
  type: 'response' | 'thinking' | 'tool_call' | 'error';
  content: string;
  metadata: Record<string, any>;
  is_final: boolean;
}

// 会话状态
interface V2Session {
  session_id: string;
  conv_id: string;
  user_id?: string;
  agent_name: string;
  state: 'idle' | 'running' | 'paused' | 'error' | 'terminated';
  message_count: number;
}

// 聊天请求
interface ChatRequest {
  message: string;
  session_id?: string;
  agent_name?: string;
}
```

---

## 三、API 端点设计

### 3.1 V2 API 路由表

| 端点 | 方法 | 功能 | 文件位置 |
|------|------|------|---------|
| `/api/v2/chat` | POST | 发送消息 (SSE 流式) | core_v2_api.py:50 |
| `/api/v2/session` | POST | 创建会话 | core_v2_api.py:123 |
| `/api/v2/session/{id}` | GET | 获取会话 | core_v2_api.py:163 |
| `/api/v2/session/{id}` | DELETE | 关闭会话 | core_v2_api.py:180 |
| `/api/v2/status` | GET | 服务状态 | core_v2_api.py:190 |

### 3.2 请求/响应格式

**请求格式 (ChatRequest):**
```python
class ChatRequest(BaseModel):
    message: Optional[str] = None
    user_input: Optional[str] = None      # 兼容前端
    session_id: Optional[str] = None
    conv_uid: Optional[str] = None        # 兼容前端
    agent_name: Optional[str] = None
    app_code: Optional[str] = None
    user_id: Optional[str] = None
```

**SSE 流式响应格式:**
```
# 正常消息块
data: {"vis": "...markdown content..."}

# 流式结束标记
data: {"vis": "[DONE]"}

# 错误响应
data: {"vis": "[ERROR]error message[/ERROR]"}
```

---

## 四、后端调度执行架构

### 4.1 V2AgentDispatcher (调度器)

```
┌─────────────────────────────────────────────────────────────┐
│                    V2AgentDispatcher                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐    ┌─────────────────────────────┐    │
│  │  Priority Queue │───>│        Worker Pool          │    │
│  │                 │    │   (max_workers = 10)        │    │
│  │  - task_id      │    │                             │    │
│  │  - priority     │    │  ┌────────┐ ┌────────┐     │    │
│  │  - session_id   │    │  │Worker-0│ │Worker-1│ ... │    │
│  │  - message      │    │  └───┬────┘ └────┬───┘     │    │
│  └─────────────────┘    └──────┼───────────┼───────────┘    │
│                                │           │                │
│                                ▼           ▼                │
│                         ┌─────────────────────┐             │
│                         │  V2AgentRuntime     │             │
│                         │  .execute(session)  │             │
│                         └─────────────────────┘             │
│                                                               │
│  职责:                                                        │
│  - 消息队列管理                                               │
│  - Agent 调度执行                                             │
│  - 流式响应处理                                               │
│  - 任务优先级管理 (LOW/NORMAL/HIGH/URGENT)                    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 V2AgentRuntime (运行时)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           V2AgentRuntime                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────┐   ┌─────────────────┐   ┌─────────────────────┐   │
│  │  Session Manager │   │ Agent Factory   │   │ GptsMemory          │   │
│  │                  │   │                 │   │  (消息持久化)        │   │
│  │  - _sessions{}   │   │  - _agent_fact{}│   │  - gpts_messages 表 │   │
│  │  - create()      │   │  - register()   │   │  - VIS 转换器       │   │
│  │  - close()       │   │  - _create()    │   │  - 消息队列         │   │
│  └────────┬─────────┘   └────────┬────────┘   └─────────────────────┘   │
│           │                        │                                      │
│           └────────────────────────┘                                      │
│                      │                                                    │
│                      ▼                                                    │
│           ┌───────────────────┐                                          │
│           │    execute()      │                                          │
│           │  (stream/sync)    │                                          │
│           └───────────────────┘                                          │
│                                                                            │
│  扩展功能:                                                                 │
│  ┌──────────────────┐   ┌──────────────────┐                            │
│  │ 分层上下文中间件 │   │ 项目记忆系统     │                            │
│  │                  │   │ (CLAUDE.md风格)  │                            │
│  └──────────────────┘   └──────────────────┘                            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Agent 输出解析规则

| 输出前缀 | Chunk 类型 | 说明 |
|---------|-----------|------|
| `[THINKING]...[/THINKING]` | `thinking` | 思考过程 |
| `[TOOL:name]...[/TOOL]` | `tool_call` | 工具调用 |
| `[ERROR]...[/ERROR]` | `error` | 错误信息 |
| `[TERMINATE]...[/TERMINATE]` | `response` | 最终响应，is_final=true |
| `[WARNING]...[/WARNING]` | `warning` | 警告信息 |
| default | `response` | 普通响应内容 |

---

## 五、VIS 可视化协议

### 5.1 VIS 窗口协议 (vis_window3)

```
┌─────────────────────────────────────────────────────────────┐
│                     VisWindow3Data                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────┐    ┌──────────────────────────┐   │
│  │   PlanningWindow    │    │     RunningWindow        │   │
│  │   (规划窗口)         │    │     (运行窗口)            │   │
│  │                     │    │                          │   │
│  │  - steps[]          │    │  - current_step          │   │
│  │    - step_id        │    │  - thinking              │   │
│  │    - title          │    │  - content               │   │
│  │    - status         │    │  - artifacts[]           │   │
│  │    - result_summary │    │    - artifact_id         │   │
│  │    - agent_name     │    │    - type                │   │
│  │  - current_step_id  │    │    - content             │   │
│  │                     │    │    - metadata            │   │
│  └─────────────────────┘    └──────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 VIS 协议转换流程

```
Agent 输出
    │
    ▼
┌─────────────────┐
│ GptsMessage     │
│ - sender        │
│ - content       │
│ - thinking      │
│ - chat_round    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐    ┌─────────────────────┐
│ visualization() │────>│ 处理增量状态 │───>│ 生成 vis_window3    │
│                 │     │  - steps     │    │ JSON 格式           │
│ - messages[]    │     │  - current   │    │                      │
│ - stream_msg    │     │  - thinking  │    │                     │
└─────────────────┘     └──────────────┘    └─────────────────────┘
```

---

## 六、完整交互流程

### 6.1 用户发送消息流程

```
┌─────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  User   │     │  Frontend   │     │  Backend API │     │   Core_v2    │
└────┬────┘     └──────┬──────┘     └──────┬───────┘     └──────┬───────┘
     │                 │                    │                    │
     │ 1. 输入消息     │                    │                    │
     │────────────────>│                    │                    │
     │                 │ 2. 创建 SSE 连接   │                    │
     │                 │───────────────────>│                    │
     │                 │                    │ 3. 分发到 Runtime  │
     │                 │                    │───────────────────>│
     │                 │                    │                    │
     │                 │                    │                    │ 4. 创建 Agent
     │                 │                    │                    │    加载上下文
     │                 │                    │                    │
     │                 │ 5. SSE 流式响应    │                    │
     │                 │<───────────────────│                    │
     │                 │                    │                    │
     │ 6. 渲染消息     │                    │                    │
     │<────────────────│                    │                    │
     │                 │                    │                    │
     │ 7. 流式更新     │                    │                    │
     │<────────────────│                    │                    │
     │                 │                    │                    │
     │ 8. 完成标记     │                    │                    │
     │<────────────────│                    │                    │
```

### 6.2 消息持久化流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   V2Agent    │     │  GptsMemory  │     │   Database       │
│   Runtime    │     │              │     │                  │
└──────┬───────┘     └──────┬───────┘     └──────────────────┘
       │                    │                    │
       │ 1. _push_stream_chunk                  │
       │───────────────────>│                    │
       │                    │ 2. VIS 转换        │
       │                    │                    │
       │                    │ 3. push_message()  │
       │                    │                    │
       │                    │ 4a. 写入           │
       │                    │    gpts_messages   │─────────────> MySQL
       │                    │                    │
       │                    │ 4b. StorageConv    │
       │                    │    (ChatHistory)   │─────────────> MySQL
```

### 6.3 SSE 流式输出时序

```
Frontend                                                Backend
    │                                                    │
    │─────────── POST /api/v2/chat ─────────────────────>│
    │  body: {message, session_id, agent_name}           │
    │                                                    │
    │<─────────── HTTP 200 (text/event-stream) ──────────│
    │                                                    │
    │<─────────── data: {"vis": "thinking..."} ──────────│  Agent 思考中
    │                                                    │
    │<─────────── data: {"vis": "tool call..."} ─────────│  工具调用
    │                                                    │
    │<─────────── data: {"vis": "response..."} ──────────│  响应内容
    │                                                    │
    │<─────────── data: {"vis": "[DONE]"} ───────────────│  流式结束
```

---

## 七、关键组件职责总结

| 组件 | 文件路径 | 核心职责 |
|------|---------|---------|
| **V2Chat** | `web/components/v2-chat/index.tsx` | 前端聊天 UI，渲染消息流 |
| **useV2Chat** | `web/hooks/use-v2-chat.ts` | V2 会话状态管理 Hook |
| **UnifiedChatService** | `web/services/unified-chat.ts` | 统一 V1/V2 聊天服务 |
| **v2.ts** | `web/client/api/v2.ts` | V2 API 客户端封装 |
| **core_v2_api** | `derisk_serve/agent/core_v2_api.py` | FastAPI 路由，SSE 响应 |
| **V2AgentDispatcher** | `derisk-core/agent/core_v2/integration/dispatcher.py` | 任务队列与调度 |
| **V2AgentRuntime** | `derisk-core/agent/core_v2/integration/runtime.py` | 会话管理与 Agent 执行 |
| **V2Adapter** | `derisk-core/agent/core_v2/integration/adapter.py` | 消息格式转换与桥梁 |
| **CoreV2VisWindow3Converter** | `derisk-core/agent/core_v2/vis_converter.py` | VIS 协议转换 |
| **CoreV2Component** | `derisk_serve/agent/core_v2_adapter.py` | 系统集成适配器 |

---

## 八、错误处理机制

| 层级 | 错误处理策略 |
|------|-------------|
| **Frontend** | `try-catch` 包裹 fetch，AbortController 支持取消流 |
| **API Layer** | FastAPI 异常处理器，返回 `[ERROR]...[/ERROR]` 格式 |
| **Dispatcher** | 工作线程异常捕获，回调通知 |
| **Runtime** | Agent 执行异常捕获，yield error chunk |

---

## 九、架构特点与设计亮点

1. **分层架构清晰**: 前端组件层 → API 层 → 调度层 → 运行时层 → Agent 层

2. **双版本兼容**: `use-chat.ts` 和 `unified-chat.ts` 同时支持 V1 和 V2

3. **流式响应**: SSE (Server-Sent Events) 实现真正的流式输出

4. **VIS 可视化协议**: 统一的 `vis_window3` 协议支持丰富的消息渲染

5. **消息双轨持久化**: 同时写入 `gpts_messages` 和 `ChatHistoryMessageEntity`

6. **分层上下文管理**: 支持项目级、会话级、消息级的上下文加载

7. **Agent 工厂模式**: 支持动态创建 Agent，从数据库加载配置