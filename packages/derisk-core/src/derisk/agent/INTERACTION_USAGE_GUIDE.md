# 用户交互能力生产级使用指南

## 概述

本文档说明如何在生产环境中使用 DERISK Agent 的用户交互能力，包括：
- Agent 主动提问
- 工具授权审批
- 方案选择
- 随处中断/随时恢复

---

## 1. Core V1 (ReActMasterAgent) 使用方式

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

## 2. Core V2 (ProductionAgent) 使用方式

### 2.1 基本使用

```python
from derisk.agent.core_v2.production_agent import ProductionAgent

# 创建 Agent
agent = ProductionAgent.create(
    name="my-agent",
    api_key="sk-xxx",
)

# 初始化交互能力
agent.init_interaction(session_id="session_001")

# 主动提问
answer = await agent.ask_user(
    question="请提供数据库连接信息",
    title="需要您的输入",
)

# 确认操作
confirmed = await agent.confirm("确定要部署吗？")

# 选择
choice = await agent.select(
    message="请选择环境",
    options=[
        {"label": "开发环境", "value": "dev"},
        {"label": "生产环境", "value": "prod"},
    ],
)

# 方案选择
plan = await agent.choose_plan([
    {"id": "blue_green", "name": "蓝绿部署"},
    {"id": "rolling", "name": "滚动更新"},
])
```

### 2.2 工具授权

```python
# 请求工具授权
authorized = await agent.request_authorization(
    tool_name="bash",
    tool_args={"command": "rm -rf /data"},
    reason="清理测试数据",
)

if authorized:
    # 执行工具
    result = await agent.execute_tool("bash", {"command": "rm -rf /data"})
```

### 2.3 通知

```python
# 进度通知
await agent.notify_progress("正在处理...", progress=0.5)

# 成功通知
await agent.notify_success("任务完成")

# 错误通知
await agent.notify_error("发生错误")
```

### 2.4 Todo 管理

```python
# 创建 Todo
todo_id = await agent.create_todo(
    content="实现用户登录功能",
    priority=1,
)

# 开始执行
await agent.start_todo(todo_id)

# 完成
await agent.complete_todo(todo_id, result="登录功能已实现")

# 获取进度
completed, total = agent.get_progress()

# 获取下一个待处理
next_todo = agent.get_next_todo()
```

### 2.5 中断恢复

```python
# 创建检查点
await agent.create_checkpoint(phase="before_critical_operation")

# 检查恢复状态
if await agent.has_recovery_state():
    # 恢复执行
    result = await agent.recover(resume_mode="continue")
    
    if result.success:
        # 恢复对话历史
        history = result.recovery_context.conversation_history
        
        # 恢复 Todo 列表
        todos = result.recovery_context.todo_list
        
        # 恢复变量
        variables = result.recovery_context.variables
```

---

## 3. 完整示例

### 3.1 带 Todo 管理的任务执行

```python
from derisk.agent.core_v2.production_agent import ProductionAgent

async def execute_with_todos():
    agent = ProductionAgent.create(name="task-agent", api_key="sk-xxx")
    agent.init_interaction(session_id="session_001")
    
    # 创建任务列表
    todos = [
        await agent.create_todo("分析需求", priority=2),
        await agent.create_todo("设计方案", priority=1, dependencies=["分析需求"]),
        await agent.create_todo("实现代码", priority=0, dependencies=["设计方案"]),
        await agent.create_todo("测试验证", priority=0, dependencies=["实现代码"]),
    ]
    
    # 执行任务
    while True:
        todo = agent.get_next_todo()
        if not todo:
            break
        
        await agent.start_todo(todo.id)
        
        try:
            # 执行任务
            result = await do_task(todo.content)
            await agent.complete_todo(todo.id, result=result)
            
            # 进度通知
            completed, total = agent.get_progress()
            await agent.notify_progress(
                f"进度: {completed}/{total}",
                progress=completed / total,
            )
            
        except Exception as e:
            await agent.fail_todo(todo.id, error=str(e))
            break
    
    # 最终报告
    completed, total = agent.get_progress()
    await agent.notify_success(f"任务完成: {completed}/{total}")
```

### 3.2 带中断恢复的长时间任务

```python
async def long_running_task():
    agent = ProductionAgent.create(name="long-task-agent", api_key="sk-xxx")
    agent.init_interaction(session_id="long_session")
    
    # 检查恢复
    if await agent.has_recovery_state():
        result = await agent.recover("continue")
        if result.success:
            print(f"从断点恢复: {result.summary}")
    
    # 执行任务
    for step in range(100):
        agent._current_step = step
        
        # 每 10 步创建检查点
        if step % 10 == 0:
            await agent.create_checkpoint(phase=f"step_{step}")
        
        # 执行步骤
        try:
            await do_step(step)
        except Exception as e:
            # 自动保存状态
            await agent.create_checkpoint(phase="error")
            raise
```

---

## 4. 前端集成

### 4.1 WebSocket 连接

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

### 4.2 恢复检测

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

## 5. 生产环境配置

### 5.1 配置 InteractionGateway

```python
from derisk.agent.interaction import InteractionGateway, set_interaction_gateway

# 配置 WebSocket 管理器
gateway = InteractionGateway(
    ws_manager=your_websocket_manager,
    state_store=your_state_store,  # Redis 或 PostgreSQL
)

set_interaction_gateway(gateway)
```

### 5.2 配置 RecoveryCoordinator

```python
from derisk.agent.interaction import RecoveryCoordinator, set_recovery_coordinator

recovery = RecoveryCoordinator(
    state_store=your_state_store,
    checkpoint_interval=5,  # 每 5 步自动检查点
)

set_recovery_coordinator(recovery)
```

---

## 6. 注意事项

1. **初始化顺序**：必须先调用 `init_interaction()` 才能使用交互能力
2. **会话 ID**：每个会话需要唯一的 session_id 用于恢复
3. **超时处理**：所有交互请求都有超时，默认 300 秒
4. **授权缓存**：会话级授权会缓存，避免重复确认
5. **检查点开销**：频繁创建检查点会影响性能，建议间隔 5-10 步

---

**文档版本**: v1.0  
**最后更新**: 2026-02-27