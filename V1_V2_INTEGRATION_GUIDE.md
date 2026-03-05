# V1/V2 Agent 前后端集成方案

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           前端应用                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Unified Chat Service                      │   │
│  │  ┌─────────────┐                    ┌─────────────┐         │   │
│  │  │  V1 Chat    │                    │  V2 Chat    │         │   │
│  │  │  (Original) │                    │  (Core_v2)  │         │   │
│  │  └──────┬──────┘                    └──────┬──────┘         │   │
│  └─────────┼───────────────────────────────────┼───────────────┘   │
│            │                                   │                    │
└────────────┼───────────────────────────────────┼────────────────────┘
             │                                   │
             ▼                                   ▼
    /api/v1/chat/completions           /api/v2/chat
             │                                   │
┌────────────┼───────────────────────────────────┼────────────────────┐
│            ▼                                   ▼                    │
│  ┌─────────────────┐                 ┌─────────────────┐           │
│  │   V1 Agent      │                 │   V2 Agent      │           │
│  │   (PDCA等)      │                 │   (Core_v2)     │           │
│  └─────────────────┘                 └─────────────────┘           │
│                          后端服务                                    │
└─────────────────────────────────────────────────────────────────────┘
```

## 二、版本切换机制

### 2.1 后端配置

在 App 配置中新增 `agent_version` 字段：

```python
# GptsApp 模型新增字段
class GptsApp:
    app_code: str
    app_name: str
    agent_version: str = "v1"  # 新增: "v1" 或 "v2"
    # ... 其他字段
```

### 2.2 前端自动检测

```typescript
// 自动检测版本
function detectVersion(config: ChatConfig): AgentVersion {
  // 1. 优先使用配置
  if (config.agent_version) return config.agent_version;
  
  // 2. 根据 app_code 前缀
  if (config.app_code?.startsWith('v2_')) return 'v2';
  
  // 3. 默认 V1
  return 'v1';
}
```

## 三、前端使用方式

### 3.1 方式一：使用统一 Chat 服务 (推荐)

```tsx
import { getChatService } from '@/services/unified-chat';

const chatService = getChatService();

// 发送消息 - 自动切换版本
await chatService.sendMessage(
  {
    app_code: 'my_app',
    agent_version: 'v2',  // 可选，不填自动检测
    conv_uid: 'xxx',
    user_input: '你好',
  },
  {
    onMessage: (msg) => console.log('消息:', msg),
    onChunk: (chunk) => console.log('V2 Chunk:', chunk),  // V2 特有
    onError: (err) => console.error('错误:', err),
    onDone: () => console.log('完成'),
  }
);

// 停止
chatService.abort();
```

### 3.2 方式二：直接使用 V2 组件

```tsx
import V2Chat from '@/components/v2-chat';

<V2Chat
  agentName="tool_agent"
  height={500}
  onSessionChange={(id) => console.log('Session:', id)}
/>
```

### 3.3 方式三：在现有页面集成

修改 `chat-context.tsx`：

```tsx
import { getChatService } from '@/services/unified-chat';

// 在 ChatContextProvider 中添加
const chatService = getChatService();

// 修改发送消息逻辑
const sendMessage = async (input: string) => {
  await chatService.sendMessage(
    {
      app_code: currentDialogInfo.app_code,
      agent_version: currentDialogInfo.agent_version,  // 新增
      conv_uid: chatId,
      user_input: input,
    },
    {
      onMessage: (msg) => { /* 更新 UI */ },
      onChunk: (chunk) => { /* V2 特殊渲染 */ },
      onDone: () => { /* 完成 */ },
    }
  );
};
```

## 四、应用构建集成

### 4.1 后端修改

修改 `CreateAppParams`:

```python
class CreateAppParams:
    app_name: str
    team_mode: str
    agent_version: str = "v1"  # 新增
    # ...
```

### 4.2 前端应用构建页面

新增版本选择：

```tsx
<Form.Item label="Agent 版本" name="agent_version">
  <Radio.Group>
    <Radio value="v1">
      V1 (经典版)
      <span className="text-gray-400 ml-2">稳定的 PDCA Agent</span>
    </Radio>
    <Radio value="v2">
      V2 (Core_v2)
      <span className="text-gray-400 ml-2">新版架构，支持 Canvas 可视化</span>
    </Radio>
  </Radio.Group>
</Form.Item>
```

## 五、文件清单

### 5.1 后端新增/修改文件

```
packages/derisk-core/src/derisk/agent/
├── core_v2/                          # Core_v2 核心
│   └── integration/                  # 集成层
│       ├── adapter.py
│       ├── runtime.py
│       ├── dispatcher.py
│       ├── agent_impl.py
│       └── api.py
└── visualization/                    # 可视化
    ├── progress.py
    ├── canvas_blocks.py
    └── canvas.py

packages/derisk-serve/src/derisk_serve/agent/
├── core_v2_adapter.py                # 服务适配器
├── core_v2_api.py                    # V2 API 路由
├── app_to_v2_converter.py            # App 转换器
└── start_v2_agent.py                 # 启动脚本
```

### 5.2 前端新增/修改文件

```
web/src/
├── types/
│   └── v2.ts                         # V2 类型定义
├── client/api/
│   └── v2/
│       └── index.ts                  # V2 API 客户端
├── services/
│   └── unified-chat.ts               # 统一 Chat 服务
├── hooks/
│   ├── use-chat.ts                   # 原有 V1 Hook
│   └── use-v2-chat.ts                # V2 Hook
├── components/
│   └── v2-chat/
│       └── index.tsx                 # V2 Chat 组件
└── app/
    └── v2-agent/
        └── page.tsx                  # V2 Agent 页面
```

## 六、数据流

### 6.1 V1 流程

```
User Input → useChat() → /api/v1/chat/completions
    → V1 Agent (PDCA) → GptsMemory → VisConverter
    → SSE Stream → 前端渲染
```

### 6.2 V2 流程

```
User Input → useV2Chat() → /api/v2/session + /api/v2/chat
    → V2AgentRuntime → V2PDCAAgent → Tool/Gateway
    → Canvas + Progress → GptsMemory
    → SSE Stream → 前端渲染 (支持 Canvas Block)
```

## 七、启动方式

### 7.1 后端启动

```bash
# 方式一：作为现有服务的一部分
# Core_v2 组件会在服务启动时自动初始化

# 方式二：独立启动 V2 服务
cd packages/derisk-serve
python start_v2_agent.py --api
```

### 7.2 前端启动

```bash
cd web
npm run dev

# 访问 V2 Agent 页面
# http://localhost:3000/v2-agent
```

## 八、API 对比

| 功能 | V1 API | V2 API |
|-----|--------|--------|
| 创建会话 | 隐式创建 | POST /api/v2/session |
| 发送消息 | POST /api/v1/chat/completions | POST /api/v2/chat (SSE) |
| 获取状态 | - | GET /api/v2/status |
| 关闭会话 | - | DELETE /api/v2/session/{id} |

## 九、迁移指南

### 9.1 从 V1 迁移到 V2

1. **后端**: 在 App 配置中设置 `agent_version = "v2"`
2. **前端**: 无需修改，统一服务自动切换
3. **测试**: 验证消息流和 Canvas 渲染

### 9.2 兼容性

- V1 和 V2 可以共存
- 同一会话应使用同一版本
- 历史数据通过 conv_uid 继承

## 十、调试

```typescript
// 前端调试
localStorage.setItem('debug', 'v2-chat:*');

// 查看当前版本
console.log(chatService.getVersion());
```

```python
# 后端调试
import logging
logging.getLogger("derisk.agent.core_v2").setLevel(logging.DEBUG)
```
