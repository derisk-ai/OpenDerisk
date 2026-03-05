# 统一用户产品层架构改造文档

## 📋 改造概述

本次架构改造旨在解决core_v2 Agent架构与产品层完全割裂的问题，建立统一的用户产品层，使底层Agent架构可以独立演进迭代，同时保证产品层的稳定性和一致性。

## 🎯 核心目标

1. **应用构建统一** - 提供统一的应用构建接口，自动适配V1/V2 Agent
2. **会话管理统一** - 统一会话创建、管理和历史消息查询
3. **用户交互统一** - 统一用户输入和文件上传接口
4. **可视化渲染统一** - 统一消息渲染和VIS输出格式

## 🏗️ 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────┐
│             用户产品层 (User Product Layer)         │
├─────────────────────────────────────────────────────┤
│ 应用管理 │ 会话管理 │ 用户交互 │ 可视化渲染         │
│ UnifiedAppBuilder │ UnifiedSessionManager │ ...    │
├─────────────────────────────────────────────────────┤
│              适配层 (Adapter Layer)                 │
│  ┌──────────────────┬──────────────────┐           │
│  │   V1适配器       │   V2适配器       │           │
│  └──────────────────┴──────────────────┘           │
├─────────────────────────────────────────────────────┤
│  Agent架构层 (Agent Architecture Layer)            │
│  ┌──────────────────┬──────────────────┐           │
│  │   V1 Agent体系   │   V2 Agent体系   │           │
│  └──────────────────┴──────────────────┘           │
└─────────────────────────────────────────────────────┘
```

### 核心组件

#### 后端组件

1. **UnifiedAppBuilder** - 统一应用构建器
   - 统一应用配置加载
   - 统一资源解析和转换
   - 自动适配V1/V2 Agent构建

2. **UnifiedSessionManager** - 统一会话管理器
   - 统一会话创建和管理
   - 统一历史消息查询
   - 自动适配V1/V2存储

3. **UnifiedInteractionGateway** - 统一用户交互网关
   - 统一用户输入请求
   - 统一文件上传
   - 自动适配V1/V2交互协议

4. **UnifiedVisAdapter** - 统一可视化适配器
   - 统一消息渲染
   - 自动适配V1/V2消息格式
   - 统一VIS输出格式

#### 前端组件

1. **UnifiedAppService** - 统一应用服务
2. **UnifiedSessionService** - 统一会话服务
3. **useUnifiedChat** - 统一聊天Hook
4. **UnifiedMessageRenderer** - 统一消息渲染器

## 📁 文件结构

### 后端文件结构

```
packages/derisk-serve/src/derisk_serve/unified/
├── __init__.py                      # 统一入口
├── api.py                          # 统一API端点
├── application/
│   └── __init__.py                 # 统一应用构建器
├── session/
│   └── __init__.py                 # 统一会话管理器
├── interaction/
│   └── __init__.py                 # 统一用户交互网关
└── visualization/
    └── __init__.py                 # 统一可视化适配器
```

### 前端文件结构

```
web/src/
├── services/unified/
│   ├── unified-app-service.ts      # 统一应用服务
│   └── unified-session-service.ts  # 统一会话服务
├── hooks/unified/
│   └── use-unified-chat.ts         # 统一聊天Hook
└── components/chat/
    └── unified-message-renderer.tsx # 统一消息渲染器
```

## 🔌 API接口

### 应用相关

- `GET /api/unified/app/{app_code}` - 获取应用配置

### 会话相关

- `POST /api/unified/session/create` - 创建会话
- `GET /api/unified/session/{session_id}` - 获取会话信息
- `POST /api/unified/session/close` - 关闭会话
- `GET /api/unified/session/{session_id}/history` - 获取历史消息
- `POST /api/unified/session/message` - 添加消息

### 聊天相关

- `POST /api/unified/chat/stream` - 流式聊天（自动适配V1/V2）

### 交互相关

- `GET /api/unified/interaction/pending` - 获取待处理交互
- `POST /api/unified/interaction/submit` - 提交交互响应

### 可视化相关

- `POST /api/unified/vis/render` - 渲染消息可视化

### 系统相关

- `GET /api/unified/health` - 健康检查
- `GET /api/unified/status` - 获取系统状态

## 🔄 核心流程

### 1. 应用构建流程

```python
# 使用统一构建器
builder = get_unified_app_builder()
app_instance = await builder.build_app(
    app_code="my_app",
    agent_version="auto"  # 自动检测
)

# app_instance包含：
# - app_code: 应用代码
# - agent: Agent实例（V1或V2）
# - version: 实际使用的版本
# - resources: 统一资源列表
```

### 2. 会话管理流程

```python
# 创建会话
manager = get_unified_session_manager()
session = await manager.create_session(
    app_code="my_app",
    user_id="user123",
    agent_version="v2"
)

# 获取历史
history = await manager.get_history(session.session_id)

# 添加消息
message = await manager.add_message(
    session.session_id,
    role="user",
    content="你好"
)
```

### 3. 前端使用流程

```typescript
// 使用统一Hook
const { session, sendMessage, loadHistory } = useUnifiedChat({
  appCode: 'my_app',
  agentVersion: 'v2',
  onMessage: (msg) => console.log(msg),
  onDone: () => console.log('完成')
});

// 发送消息
await sendMessage('你好', {
  temperature: 0.7,
  max_new_tokens: 1000
});
```

## ✅ 改造收益

### 1. 架构解耦
- Agent架构版本独立演进
- 产品层统一稳定
- 降低维护成本

### 2. 开发效率提升
- 统一的API接口
- 一致的数据模型
- 复用性增强

### 3. 用户体验优化
- 无缝切换V1/V2
- 一致的交互体验
- 更快的响应速度

### 4. 可扩展性增强
- 支持未来Agent版本演进
- 易于集成新的Agent架构
- 灵活的配置管理

## 🚀 部署指南

### 1. 后端部署

```python
# 在FastAPI应用中注册统一API
from derisk_serve.unified.api import router as unified_router

app.include_router(unified_router)
```

### 2. 前端集成

```typescript
// 使用统一服务
import { getUnifiedAppService } from '@/services/unified/unified-app-service';
import { getUnifiedSessionService } from '@/services/unified/unified-session-service';
import useUnifiedChat from '@/hooks/unified/use-unified-chat';
```

## 📊 性能考虑

1. **应用配置缓存** - UnifiedAppBuilder内置缓存机制
2. **会话管理优化** - 统一的会话缓存和清理策略
3. **流式响应优化** - 自动适配SSE流式传输
4. **历史消息分页** - 支持limit和offset参数

## 🔐 安全考虑

1. **输入验证** - 所有API接口进行参数验证
2. **权限检查** - 集成现有权限体系
3. **会话隔离** - 会话之间完全隔离
4. **错误处理** - 统一的错误处理和日志记录

## 📈 监控指标

1. **应用构建耗时** - 跟踪应用构建性能
2. **会话数量** - 监控活跃会话数
3. **API响应时间** - 监控各API响应性能
4. **错误率** - 跟踪错误发生频率

## 🔮 未来规划

1. **支持更多Agent版本** - V3、V4等未来版本
2. **增强缓存策略** - 更智能的缓存失效机制
3. **性能优化** - 进一步优化响应速度
4. **监控增强** - 更完善的监控和告警体系

## 📝 版本历史

### v1.0.0 (2026-03-01)
- ✅ 完成统一应用构建器
- ✅ 完成统一会话管理器
- ✅ 完成统一用户交互网关
- ✅ 完成统一可视化适配器
- ✅ 完成统一API端点
- ✅ 完成前端统一服务
- ✅ 完成统一聊天Hook
- ✅ 完成统一消息渲染器

---

**文档维护者**: Derisk Team  
**最后更新**: 2026-03-01