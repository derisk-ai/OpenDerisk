# Core V2 VIS 集成实施指南

## 概述

本指南详细说明了如何在 Core V2 架构的 Agent 中集成 `vis_window3` 布局能力，实现规划步骤和步骤内容的分开展示。

## 改造内容

### 1. 新增文件

```
packages/derisk-core/src/derisk/agent/core_v2/
├── vis_adapter.py           # VIS 适配器
├── vis_protocol.py           # 数据协议定义
└── examples/
    └── vis_usage.py          # 使用示例
```

### 2. 修改文件

- `production_agent.py`: 集成 VIS 能力

## 数据协议

### Planning Window (规划窗口)

展示所有步骤的列表和执行状态：

```json
{
  "steps": [
    {
      "step_id": "1",
      "title": "分析需求",
      "status": "completed",
      "result_summary": "已完成需求分析",
      "agent_name": "data-analyst",
      "agent_role": "assistant",
      "layer_count": 0,
      "start_time": "2025-03-02T10:00:00",
      "end_time": "2025-03-02T10:05:00"
    },
    {
      "step_id": "2",
      "title": "执行查询",
      "status": "running"
    }
  ],
  "current_step_id": "2"
}
```

### Running Window (运行窗口)

展示当前步骤的详细内容：

```json
{
  "current_step": {
    "step_id": "2",
    "title": "执行查询",
    "status": "running"
  },
  "thinking": "正在分析查询条件...",
  "content": "执行 SQL 查询...",
  "artifacts": [
    {
      "artifact_id": "result",
      "type": "tool_output",
      "title": "查询结果",
      "content": "..."
    }
  ]
}
```

## 使用方法

### 基本使用

```python
from derisk.agent.core_v2.production_agent import ProductionAgent

# 创建 Agent（启用 VIS）
agent = ProductionAgent.create(
    name="data-analyst",
    enable_vis=True,  # 启用 VIS
)

# 初始化
agent.init_interaction()

# 运行
async for chunk in agent.run("帮我分析数据"):
    print(chunk)

# 生成 VIS 输出
vis_output = await agent.generate_vis_output()
```

### 手动控制步骤

```python
# 添加步骤
agent.add_vis_step("1", "数据收集", status="completed")
agent.add_vis_step("2", "数据分析", status="running")
agent.add_vis_step("3", "生成报告", status="pending")

# 更新步骤
agent.update_vis_step("2", result_summary="完成分析")

# 添加产物
agent.add_vis_artifact(
    artifact_id="chart",
    artifact_type="image",
    content="![chart](chart.png)",
    title="分析图表",
)
```

### 结合 WebSocket 实时推送

```python
from fastapi import WebSocket
from derisk.agent.core_v2.visualization.progress import ProgressBroadcaster

@app.websocket("/ws/agent/{session_id}")
async def websocket_handler(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    # 创建进度广播器
    progress = ProgressBroadcaster(session_id)
    progress.add_websocket(websocket)
    
    # 创建 Agent
    agent = ProductionAgent.create(
        enable_vis=True,
        progress_broadcaster=progress,
    )
    
    # 运行并发送 VIS 数据
    async for chunk in agent.run(task):
        await websocket.send_json({"type": "chunk", "content": chunk})
    
    vis_output = await agent.generate_vis_output()
    await websocket.send_json({"type": "vis", "data": vis_output})
```

## 前端集成

### vis_window3 组件要求

前端 `vis_window3` 组件需要支持：

1. **数据接收**
   - 通过 WebSocket 或 HTTP 接收 JSON 数据
   - 支持 `planning_window` 和 `running_window` 两个区域

2. **增量更新**
   - `type: "ALL"` - 全量替换
   - `type: "INCR"` - 增量合并

3. **渲染能力**
   - Markdown 渲染
   - 代码高亮
   - 图片预览
   - 文件下载

### 示例数据流

```
后端 Agent
    ↓ (运行时收集步骤和产物)
CoreV2VisAdapter
    ↓ (转换为 GptsMessage)
DeriskIncrVisWindow3Converter
    ↓ (生成布局数据)
前端 vis_window3 组件
    ↓ (渲染)
用户界面
```

## 架构说明

### 数据转换流程

```
ProductionAgent
    ├── think() → 记录思考内容
    ├── act()   → 记录工具执行
    └── run()   → 执行主循环
         ↓
CoreV2VisAdapter
    ├── steps: Dict[str, VisStep]
    ├── artifacts: List[VisArtifact]
    └── thinking_content / content
         ↓
generate_vis_output()
    ├── 方式1: 转换为 GptsMessage → DeriskIncrVisWindow3Converter
    └── 方式2: 直接生成 JSON
         ↓
{
  "planning_window": {...},
  "running_window": {...}
}
```

### 兼容性

- **Core V1**: 使用完整的 GptsMessage 体系
- **Core V2**: 使用简化的 ProgressEvent + VisAdapter
- **统一接口**: 前端 vis_window3 组件无需修改

## 测试验证

### 单元测试

```python
import pytest
from derisk.agent.core_v2.vis_adapter import CoreV2VisAdapter

def test_add_step():
    adapter = CoreV2VisAdapter()
    
    adapter.add_step("1", "Step 1", "completed")
    assert "1" in adapter.steps
    assert adapter.steps["1"].status == "completed"

def test_generate_output():
    adapter = CoreV2VisAdapter()
    adapter.add_step("1", "Step 1", "completed")
    
    output = adapter.generate_planning_window()
    assert len(output["steps"]) == 1
```

### 集成测试

```python
@pytest.mark.asyncio
async def test_agent_vis_integration():
    agent = ProductionAgent.create(enable_vis=True)
    agent.init_interaction()
    
    agent.add_vis_step("1", "Test", "completed")
    
    vis_output = await agent.generate_vis_output()
    assert vis_output is not None
    
    data = json.loads(vis_output)
    assert "planning_window" in data
    assert "running_window" in data
```

## 性能优化建议

1. **增量更新**
   - 使用 `UpdateType.INCR` 减少数据传输
   - 只发送变更的步骤和产物

2. **流式传输**
   - 结合 WebSocket 实时推送
   - 避免等待全部完成后才展示

3. **数据压缩**
   - 大型产物考虑压缩或分片
   - 使用 CDN 托管图片等资源

## 后续优化方向

1. **多 Agent 协同可视化**
   - 支持嵌套 Agent 的步骤展示
   - 统一的任务树管理

2. **历史记录**
   - 支持查看历史执行记录
   - 步骤回放功能

3. **交互增强**
   - 步骤点击跳转
   - 产物预览和下载
   - 用户反馈和评分

## 常见问题

### Q: 为什么不直接使用 Core V1 的 VIS 体系？

A: Core V2 定位轻量级，不适合引入完整的 GptsMessage 体系。通过适配器模式，既能保持轻量，又能复用前端组件。

### Q: 前端需要修改吗？

A: 不需要。前端 `vis_window3` 组件已支持标准数据格式，后端输出符合协议即可。

### Q: 如何处理大量步骤？

A: 建议使用增量更新，只传输变更部分。前端根据 `uid` 自动合并数据。

## 联系方式

如有问题，请联系：
- 后端负责人: [your-email]
- 前端负责人: [frontend-email]