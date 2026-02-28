# Web + Canvas 可视化方案使用指南

## 概述

Core_v2 提供了两层可视化方案：
1. **Progress 实时进度推送** - 简单的进度事件广播
2. **Canvas 可视化工作区** - 结构化的块级内容组织

## 一、架构设计

```
┌─────────────────────────────────────────────────────────┐
│                      前端应用                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Canvas Renderer                      │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │  │
│  │  │Thinking│ │ToolCall│ │ Message│ │  Task  │    │  │
│  │  │ Block  │ │ Block  │ │ Block  │ │ Block  │    │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘    │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
                          ▲
                          │ WebSocket / SSE
                          │
┌─────────────────────────────────────────────────────────┐
│                    Core_v2 可视化层                      │
│  ┌──────────────────┐    ┌──────────────────┐          │
│  │ ProgressBroadcaster    │     Canvas       │          │
│  │  - thinking()          │  - add_thinking()│          │
│  │  - tool_execution()    │  - add_tool_call()         │
│  │  - error()             │  - add_message() │          │
│  │  - success()           │  - add_task()    │          │
│  └──────────────────┘    └──────────────────┘          │
└────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                    GptsMemory 集成                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │              VisConverter                         │  │
│  │  Block → Vis 文本 → 前端渲染                       │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

## 二、Progress 实时进度推送

### 2.1 基本使用

```python
from derisk.agent.visualization import create_broadcaster

# 创建广播器
broadcaster = create_broadcaster("session-123")

# 思考进度
await broadcaster.thinking("正在分析问题...")

# 工具执行进度
await broadcaster.tool_started("bash", {"command": "ls -la"})
await broadcaster.tool_completed("bash", "执行完成")

# 错误
await broadcaster.error("执行失败", {"error": "permission denied"})

# 成功
await broadcaster.success("任务完成")
```

### 2.2 集成到 Agent

```python
from derisk.agent.core_v2 import AgentBase
from derisk.agent.visualization import create_broadcaster

class MyAgent(AgentBase):
    async def think(self, message: str):
        broadcaster = create_broadcaster(self.context.session_id)
        
        await broadcaster.thinking(f"正在分析: {message[:50]}...")
        # ... 思考逻辑
        yield "思考完成"
    
    async def act(self, tool_name: str, tool_args: Dict):
        broadcaster = create_broadcaster(self.context.session_id)
        
        await broadcaster.tool_execution(tool_name, tool_args, "started")
        result = await self.execute_tool(tool_name, tool_args)
        await broadcaster.tool_execution(tool_name, tool_args, "completed")
        
        return result
```

### 2.3 订阅进度事件

```python
from derisk.agent.visualization import get_progress_manager

manager = get_progress_manager()
broadcaster = manager.create_broadcaster("session-123")

# 订阅事件
def on_progress(event):
    print(f"[{event.type}] {event.message}")

broadcaster.subscribe(on_progress)
```

## 三、Canvas 可视化工作区

### 3.1 基本使用

```python
from derisk.agent.visualization import Canvas, get_canvas_manager

# 获取 Canvas
manager = get_canvas_manager()
canvas = manager.get_canvas("session-123")

# 添加思考块
block_id = await canvas.add_thinking(
    content="正在分析项目结构",
    thoughts=["读取目录", "分析代码", "生成报告"],
    reasoning="需要先了解项目结构"
)

# 更新思考块
await canvas.update_thinking(block_id, thought="完成目录读取")

# 添加工具调用块
tool_id = await canvas.add_tool_call("bash", {"command": "find . -type f"})
await canvas.complete_tool_call(tool_id, "找到 100 个文件", execution_time=1.5)

# 添加消息块
await canvas.add_message("user", "帮我分析项目")

# 添加任务块
task_id = await canvas.add_task("代码分析", "分析项目代码结构")
await canvas.update_task_status(task_id, "completed")

# 添加计划块
await canvas.add_plan([
    {"name": "阶段1", "description": "扫描目录"},
    {"name": "阶段2", "description": "分析代码"},
    {"name": "阶段3", "description": "生成报告"},
])

# 添加代码块
await canvas.add_code(
    code="def hello(): print('hello')",
    language="python",
    title="示例代码"
)

# 添加错误块
await canvas.add_error("ValueError", "参数错误", stack_trace="...")
```

### 3.2 集成 GptsMemory

```python
from derisk.agent.visualization import CanvasManager
from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

# 创建 CanvasManager 并关联 GptsMemory
gpts_memory = GptsMemory()
canvas_manager = CanvasManager(gpts_memory=gpts_memory)

canvas = canvas_manager.get_canvas("conv-123")

# 添加的 Block 会自动同步到 GptsMemory
await canvas.add_thinking("分析中...")  # → 推送到 GptsMemory → 前端渲染
```

### 3.3 在 Runtime 中使用

```python
from derisk.agent.core_v2.integration import V2AgentRuntime
from derisk.agent.visualization import get_canvas_manager

runtime = V2AgentRuntime()

# 注册 Agent 时绑定 Canvas
async def create_agent_with_canvas(context, **kwargs):
    from derisk.agent.core_v2.integration import create_v2_agent
    
    canvas_manager = get_canvas_manager()
    canvas = canvas_manager.get_canvas(context.session_id)
    
    agent = create_v2_agent(name="canvas_agent", mode="planner")
    agent.canvas = canvas  # 绑定 Canvas
    
    return agent

runtime.register_agent_factory("canvas_agent", create_agent_with_canvas)
```

## 四、前端集成

### 4.1 WebSocket 消息格式

```json
// Progress 事件
{
  "type": "progress",
  "session_id": "session-123",
  "event": {
    "type": "thinking",
    "message": "正在分析...",
    "details": {},
    "percent": 50
  }
}

// Canvas Block 事件
{
  "type": "canvas_block",
  "session_id": "session-123",
  "action": "add",
  "block": {
    "block_id": "abc123",
    "block_type": "thinking",
    "content": "正在分析项目结构",
    "thoughts": ["步骤1", "步骤2"],
    "reasoning": "需要先了解项目"
  },
  "version": 1
}
```

### 4.2 前端渲染示例 (React)

```tsx
import React, { useEffect, useState } from 'react';

interface Block {
  block_id: string;
  block_type: string;
  content: any;
  [key: string]: any;
}

function CanvasRenderer({ sessionId }: { sessionId: string }) {
  const [blocks, setBlocks] = useState<Block[]>([]);
  
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8080/ws/${sessionId}`);
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === 'canvas_block') {
        if (message.action === 'add') {
          setBlocks(prev => [...prev, message.block]);
        }
      }
    };
    
    return () => ws.close();
  }, [sessionId]);
  
  return (
    <div className="canvas">
      {blocks.map(block => (
        <BlockRenderer key={block.block_id} block={block} />
      ))}
    </div>
  );
}

function BlockRenderer({ block }: { block: Block }) {
  switch (block.block_type) {
    case 'thinking':
      return (
        <div className="thinking-block">
          <h4>思考中</h4>
          <p>{block.content}</p>
          {block.thoughts?.map((t: string, i: number) => (
            <div key={i}>• {t}</div>
          ))}
        </div>
      );
    
    case 'tool_call':
      return (
        <div className="tool-block">
          <h4>工具: {block.tool_name}</h4>
          <pre>{JSON.stringify(block.tool_args, null, 2)}</pre>
          {block.result && <div>结果: {block.result}</div>}
        </div>
      );
    
    case 'message':
      return (
        <div className={`message ${block.role}`}>
          {block.content}
        </div>
      );
    
    case 'task':
      return (
        <div className={`task ${block.status}`}>
          {block.task_name}: {block.description}
        </div>
      );
    
    case 'code':
      return (
        <pre className="code-block">
          <code className={block.language}>{block.code}</code>
        </pre>
      );
    
    default:
      return <div>{block.content}</div>;
  }
}
```

## 五、与原有系统的集成

### 5.1 替换原有的 VisConverter

```python
from derisk.agent.visualization import Canvas
from derisk.agent.vis.vis_converter import VisProtocolConverter

class CanvasVisConverter(VisProtocolConverter):
    """将 Canvas Block 转换为 Vis 文本"""
    
    def __init__(self, canvas: Canvas):
        self.canvas = canvas
    
    async def visualization(self, messages, plans_map, **kwargs):
        # 从 Canvas 获取所有 Block
        snapshot = self.canvas.snapshot()
        
        # 转换为 Vis 文本
        vis_parts = []
        for block_data in snapshot['blocks']:
            vis_parts.append(self._block_to_vis(block_data))
        
        return '\n'.join(vis_parts)
```

### 5.2 在 PDCA Agent 中使用

```python
from derisk.agent.expand.pdca_agent import PDCAAgent
from derisk.agent.visualization import Canvas, ThinkingBlock, TaskBlock

class CanvasPDCAAgent(PDCAAgent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._canvas: Optional[Canvas] = None
    
    async def generate_reply(self, received_message, sender, **kwargs):
        # 初始化 Canvas
        from derisk.agent.visualization import get_canvas_manager
        
        canvas_manager = get_canvas_manager()
        self._canvas = canvas_manager.get_canvas(self.agent_context.conv_id)
        
        # 添加思考块
        thinking_id = await self._canvas.add_thinking(
            content=f"分析任务: {received_message.content[:50]}",
            thoughts=[]
        )
        
        # 执行过程中更新思考块
        await self._canvas.update_thinking(thinking_id, thought="读取文件")
        
        # 添加任务块
        task_id = await self._canvas.add_task(
            task_name="执行任务",
            description=received_message.current_goal
        )
        
        # 执行原有逻辑
        result = await super().generate_reply(received_message, sender, **kwargs)
        
        # 更新任务状态
        await self._canvas.update_task_status(task_id, "completed")
        
        return result
```

## 六、Block 类型速查

| Block 类型 | 用途 | 关键字段 |
|-----------|------|---------|
| ThinkingBlock | 思考过程 | thoughts, reasoning |
| ToolCallBlock | 工具调用 | tool_name, tool_args, result, status |
| MessageBlock | 对话消息 | role, content, round |
| TaskBlock | 任务状态 | task_name, description, status |
| PlanBlock | 执行计划 | stages, current_stage |
| ErrorBlock | 错误信息 | error_type, error_message, stack_trace |
| CodeBlock | 代码展示 | code, language |
| ChartBlock | 图表数据 | chart_type, data, options |
| FileBlock | 文件信息 | file_name, file_type, preview |

## 七、最佳实践

### 7.1 粒度选择

- **Progress**: 适合简单进度通知、日志流
- **Canvas**: 适合结构化内容展示、交互式 UI

### 7.2 性能优化

```python
# 批量更新 Block
async def batch_update(canvas: Canvas, updates: List[Dict]):
    for update in updates:
        await canvas.update_block(update['block_id'], update['data'])
    
    # 只在最后推送一次
    await canvas._push_block_update(...)
```

### 7.3 清理资源

```python
# 会话结束时清理
canvas_manager = get_canvas_manager()
canvas_manager.remove_canvas(session_id)
```

## 八、文件位置

```
packages/derisk-core/src/derisk/agent/visualization/
├── __init__.py          # 模块导出
├── progress.py          # Progress 进度推送
├── canvas_blocks.py     # Canvas Block 定义
└── canvas.py            # Canvas 主类
```