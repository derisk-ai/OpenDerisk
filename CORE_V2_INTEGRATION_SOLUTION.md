# Core_v2 Integration 完整解决方案

本方案展示如何利用 Core_v2 架构结合原有的 Agent 构建体系、资源系统、前端工程构建可运行的 Agent 产品。

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                       前端应用层                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Web UI  │  │  CLI     │  │ API Call │  │ WebSocket│    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
└───────┼─────────────┼─────────────┼─────────────┼───────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   V2AgentAPI (API层)                         │
│  - HTTP/REST API                                             │
│  - WebSocket 流式推送                                         │
│  - Session 管理                                               │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   V2AgentDispatcher (调度层)                  │
│  - 任务队列                                                   │
│  - 多Worker并发                                               │
│  - 流式响应处理                                               │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   V2AgentRuntime (运行时)                     │
│  - Session 生命周期                                           │
│  - Agent 执行调度                                             │
│  - GptsMemory 集成                                            │
│  - 消息流处理                                                 │
└────────────────────────────┬────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼───────┐   ┌────────▼────────┐  ┌───────▼───────┐
│  V2PDCAAgent  │   │ V2ApplicationBuilder  │   │  V2Adapter    │
│  V2SimpleAgent│   │ (Builder)        │   │ (适配层)       │
└───────┬───────┘   └────────┬────────┘  └───────┬───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                       Core_v2 核心                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │AgentBase │ │AgentInfo │ │Permission│ │ToolBase  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Gateway  │ │ Channel  │ │ Progress │ │ Sandbox  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐                                   │
│  │  Memory  │ │  Skill   │                                   │
│  └──────────┘ └──────────┘                                   │
└─────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      原有系统集成                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │GptsMemory│ │AgentRes  │ │PDCA Agent│ │FileSystem│       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │VisConvert│ │SandboxV1 │ │ToolSystem│                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

## 2. 核心模块说明

### 2.1 V2Adapter (适配层)

连接 Core_v2 与原架构，负责：
- **V2MessageConverter**: 消息格式转换（V2Message ↔ GptsMessage）
- **V2ResourceBridge**: 资源桥梁（AgentResource → V2 Tool）
- **V2ContextBridge**: 上下文桥梁（V1 Context ↔ V2 Context）

### 2.2 V2AgentRuntime (运行时)

Agent 执行的核心运行环境：
- Session 生命周期管理
- Agent 执行调度
- GptsMemory 集成（消息持久化、流式推送）
- 前端交互支持

### 2.3 V2AgentDispatcher (调度器)

统一的消息分发和调度：
- 优先级任务队列
- 多 Worker 并发处理
- 流式响应处理
- 回调事件通知

### 2.4 V2ApplicationBuilder (构建器)

从 App 配置构建可运行的 Agent

### 2.5 V2PDCAAgent / V2SimpleAgent (Agent实现)

基于 Core_v2 AgentBase 的具体实现

## 3. 使用方式

### 3.1 快速开始 - 简单 Agent

```python
from derisk.agent.core_v2.integration import create_v2_agent

agent = create_v2_agent(name="assistant", mode="primary")

async for chunk in agent.run("你好"):
    print(chunk)
```

### 3.2 带工具的 Agent

```python
from derisk.agent.tools_v2 import BashTool
from derisk.agent.core_v2.integration import create_v2_agent

agent = create_v2_agent(
    name="tool_agent",
    mode="planner",
    tools={"bash": BashTool()},
    permission={"bash": "allow"},
)

async for chunk in agent.run("执行 ls -la"):
    print(chunk)
```

### 3.3 使用 Runtime 管理会话

```python
from derisk.agent.core_v2.integration import V2AgentRuntime, create_v2_agent
from derisk.agent.tools_v2 import BashTool

runtime = V2AgentRuntime()

runtime.register_agent_factory("assistant", lambda ctx, **kw: 
    create_v2_agent(name="assistant", tools={"bash": BashTool()})
)

await runtime.start()

session = await runtime.create_session(user_id="user001", agent_name="assistant")

async for chunk in runtime.execute(session.session_id, "分析当前目录"):
    print(f"[{chunk.type}] {chunk.content}")

await runtime.stop()
```

### 3.4 集成 GptsMemory

```python
from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
from derisk.agent.core_v2.integration import V2AgentRuntime, V2Adapter

gpts_memory = GptsMemory()  # 从配置获取
adapter = V2Adapter()

runtime = V2AgentRuntime(gpts_memory=gpts_memory, adapter=adapter)

# 消息会自动推送到 GptsMemory 并通过 VisConverter 转换
queue_iter = await runtime.get_queue_iterator(session.session_id)

async for msg in queue_iter:
    # 前端可渲染的 Vis 文本
    print(msg)
```

### 3.5 完整 Web 应用

```python
from derisk.agent.core_v2.integration import V2AgentDispatcher, V2AgentRuntime
from derisk.agent.core_v2.integration.api import V2AgentAPI, APIConfig

runtime = V2AgentRuntime()
dispatcher = V2AgentDispatcher(runtime=runtime)
api = V2AgentAPI(dispatcher=dispatcher, config=APIConfig(port=8080))

await api.start()

# 访问:
# POST /api/v2/chat - 发送消息
# GET /api/v2/session - 查询会话
# WebSocket /ws/{session_id} - 流式接收
```

## 4. 与原架构的集成点

| 原架构组件 | Core_v2 集成方式 |
|-----------|-----------------|
| GptsMemory | V2AgentRuntime.gpts_memory |
| AgentResource | V2ResourceBridge → V2 Tool |
| VisConverter | V2Adapter.message_converter |
| PDCA Agent | V2PDCAAgent 实现 |
| AgentFileSystem | 通过 Runtime/Session 关联 |
| Sandbox | 复用 Core_v2 Sandbox |

## 5. 文件结构

```
packages/derisk-core/src/derisk/agent/core_v2/integration/
├── __init__.py          # 模块导出
├── adapter.py           # 适配层 (MessageConverter, ResourceBridge)
├── runtime.py           # 运行时 (V2AgentRuntime)
├── builder.py           # 构建器 (V2ApplicationBuilder)
├── dispatcher.py        # 调度器 (V2AgentDispatcher)
├── agent_impl.py        # Agent 实现 (V2PDCAAgent, V2SimpleAgent)
├── api.py               # API 层 (V2AgentAPI)
└── examples.py          # 使用示例
```

## 6. 前端对接方式

### 6.1 HTTP API

```javascript
// 发送消息
const response = await fetch('/api/v2/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        message: '你好',
        session_id: 'xxx',
    })
});

// 流式响应需要使用 ReadableStream
const reader = response.body.getReader();
while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    // 处理 chunk
}
```

### 6.2 WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/SESSION_ID');

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    // msg = {type: "response", content: "...", is_final: false}
    
    if (msg.type === 'response') {
        // 更新 UI 显示
    }
};

// 发送消息
ws.send(JSON.stringify({
    type: 'chat',
    content: '你好'
}));
```

## 7. 扩展指南

### 7.1 添加新的 Tool

```python
from derisk.agent.tools_v2 import ToolBase, ToolInfo

class MyTool(ToolBase):
    def __init__(self):
        super().__init__(ToolInfo(
            name="my_tool",
            description="自定义工具",
            parameters={...}
        ))
    
    async def execute(self, **kwargs):
        # 实现工具逻辑
        return {"result": "..."}

# 注册
from derisk.agent.tools_v2 import tool_registry
tool_registry.register(MyTool())
```

### 7.2 自定义 Agent

```python
from derisk.agent.core_v2 import AgentBase

class MyAgent(AgentBase):
    async def think(self, message, **kwargs):
        yield "思考中..."
    
    async def decide(self, message, **kwargs):
        return {"type": "response", "content": "回复内容"}
    
    async def act(self, tool_name, tool_args, **kwargs):
        return await self.tools[tool_name].execute(**tool_args)
```

## 8. 总结

本方案通过以下层级的集成，实现了 Core_v2 架构与原有系统的无缝对接：

1. **Adapter 层**: 消息格式转换、资源映射
2. **Runtime 层**: 会话管理、执行调度、Memory 集成
3. **Dispatcher 层**: 任务分发、并发控制
4. **API 层**: HTTP/WebSocket 接口

这使得原有的前端工程、AgentResource 体系、GptsMemory 等组件可以继续使用，同时享受 Core_v2 提供的类型安全、权限控制、Sandbox 隔离等新特性。