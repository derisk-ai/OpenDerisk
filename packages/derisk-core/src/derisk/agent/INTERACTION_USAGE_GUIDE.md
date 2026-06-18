# 用户交互能力生产级使用指南

## 概述

本文档说明如何在生产环境中使用 DERISK Agent 的用户交互能力，包括：
- Agent 主动提问
- 工具授权审批
- 方案选择
- 随处中断/随时恢复

---

## 1. ReActMasterAgent 使用方式

### 1.1 基本使用

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent

# 创建 Agent
agent = ReActMasterAgent()

# 主动提问
answer = await agent.ask_user(
    question="请提供数据库连接信息",
    title="需要您的输入",
    default="localhost:5432",
)

# 方案选择
plan = await agent.choose_plan(
    plans=[
        {"id": "fast", "name": "快速实现", "pros": ["快"], "cons": ["不完整"]},
        {"id": "full", "name": "完整实现", "pros": ["完整"], "cons": ["慢"]},
    ],
    title="请选择执行方案",
)

# 确认操作
confirmed = await agent.confirm_action(
    message="确定要删除这个文件吗？",
    title="确认删除",
)

# 访问交互扩展
extension = agent.interaction
```

### 1.2 工具授权

ReActMasterAgent 的 Doom Loop 检测器已集成交互授权：

```python
# 工具执行前会自动请求授权
# 授权请求会发送到前端，等待用户响应
```

### 1.3 中断恢复

```python
from derisk.agent.interaction import get_recovery_coordinator

recovery = get_recovery_coordinator()

# 检查恢复状态
if await recovery.has_recovery_state(session_id):
    result = await agent.interaction.recover(resume_mode="continue")
    if result.success:
        print(result.summary)
```

---

## 2. 完整示例

### 2.1 带中断恢复的长时间任务

```python
async def long_running_task(agent):
    # 检查恢复
    recovery = get_recovery_coordinator()
    if await recovery.has_recovery_state(session_id):
        result = await agent.interaction.recover(resume_mode="continue")
        if result.success:
            print(f"从断点恢复: {result.summary}")

    # 执行任务
    for step in range(100):
        # 每 10 步创建检查点
        if step % 10 == 0:
            await recovery.create_checkpoint(session_id, phase=f"step_{step}")

        # 执行步骤
        try:
            await do_step(step)
        except Exception:
            await recovery.create_checkpoint(session_id, phase="error")
            raise
```

---

## 3. 前端集成

### 3.1 WebSocket 连接

```typescript
// 前端连接
const ws = new WebSocket(`wss://api.example.com/ws/${sessionId}`);

// 接收交互请求
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'interaction_request') {
    // 显示交互 UI
    showInteractionModal(data.data);
  }
};

// 发送响应
function sendResponse(requestId: string, choice: string) {
  ws.send(JSON.stringify({
    type: 'interaction_response',
    data: {
      request_id: requestId,
      choice: choice,
      status: 'responsed'
    }
  }));
}
```

### 3.2 恢复检测

```typescript
// 页面加载时检查恢复状态
async function checkRecovery(sessionId: string) {
  const response = await fetch(`/api/session/${sessionId}/recovery`);
  const data = await response.json();
  
  if (data.has_recovery) {
    // 显示恢复提示
    showRecoveryPrompt(data.recovery_state);
  }
}
```

---

## 4. 生产环境配置

### 4.1 配置 InteractionGateway

```python
from derisk.agent.interaction import InteractionGateway, set_interaction_gateway

# 配置 WebSocket 管理器
gateway = InteractionGateway(
    ws_manager=your_websocket_manager,
    state_store=your_state_store,  # Redis 或 PostgreSQL
)

set_interaction_gateway(gateway)
```

### 4.2 配置 RecoveryCoordinator

```python
from derisk.agent.interaction import RecoveryCoordinator, set_recovery_coordinator

recovery = RecoveryCoordinator(
    state_store=your_state_store,
    checkpoint_interval=5,  # 每 5 步自动检查点
)

set_recovery_coordinator(recovery)
```

---

## 5. 注意事项

1. **初始化顺序**：必须先调用 `init_interaction()` 才能使用交互能力
2. **会话 ID**：每个会话需要唯一的 session_id 用于恢复
3. **超时处理**：所有交互请求都有超时，默认 300 秒
4. **授权缓存**：会话级授权会缓存，避免重复确认
5. **检查点开销**：频繁创建检查点会影响性能，建议间隔 5-10 步

---

**文档版本**: v1.0  
**最后更新**: 2026-02-27