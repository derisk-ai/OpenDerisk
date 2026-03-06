# 服务启动指南

## 一、正确启动方式

### 使用原有的 derisk_server 启动 (推荐)

V1/V2 已经集成到同一个服务中，使用原有的启动方式即可：

```bash
# 方式1: 使用配置文件启动
python -m derisk_app.derisk_server -c configs/derisk-siliconflow.toml

# 方式2: 使用默认配置
python -m derisk_app.derisk_server

# 方式3: 使用其他环境配置
python -m derisk_app.derisk_server -c configs/derisk-prod.toml
```

### 启动后的 API 端点

服务启动后，同时可用：

**V1 API (原有):**
- POST /api/v1/chat/completions - V1 聊天
- 其他原有 API...

**V2 API (新增):**
- POST /api/v2/session - 创建会话
- POST /api/v2/chat - V2 聊天 (流式)
- GET /api/v2/session/:id - 获取会话
- DELETE /api/v2/session/:id - 关闭会话
- GET /api/v2/status - 获取状态

## 二、版本自动切换机制

### 配置方式

在应用配置中指定 `agent_version`:

```python
# 创建 V1 应用
agent_version = "v1"  # 或不填写，默认 v1

# 创建 V2 应用
agent_version = "v2"
```

### 前端自动路由

前端 `unified-chat.ts` 会根据 `agent_version` 自动选择 API:

```typescript
// 自动检测版本
const version = config.agent_version || 'v1';

if (version === 'v2') {
  // 使用 /api/v2/chat
} else {
  // 使用 /api/v1/chat/completions
}
```

## 三、独立启动 V2 Agent (测试/开发)

如果只想测试 V2 Agent:

```bash
cd packages/derisk-serve
python start_v2_agent.py --api   # API 模式
python start_v2_agent.py          # CLI 交互模式
python start_v2_agent.py --demo   # 演示模式
```

注意: 独立启动只包含 V2 功能，不包含 V1。

## 四、集成说明

### 已修改的文件

1. **derisk_app/app.py**
   - `mount_routers()`: 添加了 Core_v2 路由
   - `initialize_app()`: 注册了 Core_v2 组件

2. **derisk_serve/building/app/api/schema_app.py**
   - 添加了 `agent_version` 字段

### 新增的文件

**后端:**
- `derisk-core/agent/core_v2/integration/*.py`
- `derisk-core/agent/visualization/*.py`
- `derisk-serve/agent/core_v2_adapter.py`
- `derisk-serve/agent/core_v2_api.py`
- `derisk-serve/agent/core_v2_startup.py`

**前端:**
- `web/src/types/v2.ts`
- `web/src/client/api/v2/index.ts`
- `web/src/hooks/use-v2-chat.ts`
- `web/src/services/unified-chat.ts`
- `web/src/components/v2-chat/index.tsx`
- `web/src/components/canvas-renderer/index.tsx`
- `web/src/components/agent-version-selector/index.tsx`
- `web/src/app/v2-agent/page.tsx`

## 五、验证启动

```bash
# 启动服务
python -m derisk_app.derisk_server

# 测试 V1 API
curl -X POST http://localhost:5670/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"user_input": "hello"}'

# 测试 V2 API
curl -X POST http://localhost:5670/api/v2/session \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "simple_chat"}'

curl -X POST http://localhost:5670/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "agent_name": "simple_chat"}'
```

## 六、前端访问

- V1 应用: 原有页面，自动使用 V1 API
- V2 Agent 页面: http://localhost:3000/v2-agent
- 应用构建时选择 Agent 版本即可