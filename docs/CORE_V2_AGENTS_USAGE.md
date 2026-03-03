# CoreV2 Built-in Agents 使用文档

## 概述

CoreV2架构提供三种内置Agent，开箱即用：

1. **ReActReasoningAgent** - 长程任务推理Agent
2. **FileExplorerAgent** - 文件探索Agent
3. **CodingAgent** - 编程开发Agent

## 快速开始

### 1. ReActReasoningAgent - 长程任务推理

**特性**：
- 末日循环检测
- 上下文压缩
- 输出截断
- 历史修剪
- 原生Function Call支持

**使用方法**：

```python
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

# 创建Agent
agent = ReActReasoningAgent.create(
    name="my-reasoning-agent",
    model="gpt-4",
    api_key="sk-xxx",
    max_steps=30,
    enable_doom_loop_detection=True
)

# 执行任务
async for chunk in agent.run("帮我完成数据分析项目"):
    print(chunk, end="")
```

### 2. FileExplorerAgent - 文件探索

**特性**：
- 主动探索项目结构
- 自动识别项目类型
- 查找关键文件
- 生成项目文档

**使用方法**：

```python
from derisk.agent.core_v2.builtin_agents import FileExplorerAgent

# 创建Agent
agent = FileExplorerAgent.create(
    name="explorer",
    project_path="/path/to/project",
    enable_auto_exploration=True
)

# 探索项目
async for chunk in agent.run("分析这个项目的结构"):
    print(chunk, end="")
```

### 3. CodingAgent - 编程开发

**特性**：
- 自主探索代码库
- 智能代码定位
- 功能开发与重构
- 代码质量检查
- 软件工程最佳实践

**使用方法**：

```python
from derisk.agent.core_v2.builtin_agents import CodingAgent

# 创建Agent
agent = CodingAgent.create(
    name="coder",
    workspace_path="/path/to/workspace",
    enable_auto_exploration=True,
    enable_code_quality_check=True
)

# 开发功能
async for chunk in agent.run("实现用户登录功能"):
    print(chunk, end="")
```

## 从配置文件创建

### 配置文件示例

**react_reasoning_agent.yaml**:

```yaml
agent:
  type: "react_reasoning"
  name: "react-reasoning-agent"
  model: "gpt-4"
  api_key: "${OPENAI_API_KEY}"
  
  options:
    max_steps: 30
    enable_doom_loop_detection: true
    enable_output_truncation: true
```

**使用配置创建**：

```python
from derisk.agent.core_v2.builtin_agents import create_agent_from_config

agent = create_agent_from_config("configs/agents/react_reasoning_agent.yaml")
```

## 工具系统

### 默认工具集

**ReActReasoningAgent**:
- bash, read, write, grep, glob, think

**FileExplorerAgent**:
- glob, grep, read, bash, think

**CodingAgent**:
- read, write, bash, grep, glob, think

### 自定义工具

参考 `tools_v2` 模块，可以注册自定义工具：

```python
from derisk.agent.core_v2.tools_v2 import ToolRegistry, tool

@tool
def my_custom_tool(param: str) -> str:
    """自定义工具描述"""
    return f"处理: {param}"

# 注册到Agent
agent = ReActReasoningAgent.create(...)
agent.tools.register(my_custom_tool)
```

## 核心特性详解

### 1. 末日循环检测

自动检测重复的工具调用模式，防止无限循环：

```python
agent = ReActReasoningAgent.create(
    enable_doom_loop_detection=True,
    doom_loop_threshold=3  # 连续3次相同调用触发警告
)
```

### 2. 上下文压缩

当上下文超过窗口限制时，自动压缩：

```python
agent = ReActReasoningAgent.create(
    enable_context_compaction=True,
    context_window=128000  # 128K tokens
)
```

### 3. 输出截断

大型工具输出自动截断并保存：

```python
agent = ReActReasoningAgent.create(
    enable_output_truncation=True,
    max_output_lines=2000,
    max_output_bytes=50000
)
```

### 4. 主动探索

FileExplorerAgent和CodingAgent支持自动探索项目：

```python
# 文件探索
agent = FileExplorerAgent.create(
    enable_auto_exploration=True
)

# 代码探索
agent = CodingAgent.create(
    enable_auto_exploration=True
)
```

## 最佳实践

### 1. 选择合适的Agent

- **长程推理任务** → ReActReasoningAgent
- **项目探索分析** → FileExplorerAgent
- **代码开发重构** → CodingAgent

### 2. 配置API Key

建议使用环境变量：

```bash
export OPENAI_API_KEY="sk-xxx"
```

或者在代码中：

```python
import os
os.environ["OPENAI_API_KEY"] = "sk-xxx"
```

### 3. 监控执行

使用统计信息监控Agent执行：

```python
stats = agent.get_statistics()
print(f"当前步骤: {stats['current_step']}/{stats['max_steps']}")
print(f"消息数量: {stats['messages_count']}")
```

### 4. 流式输出

推荐使用流式输出获得更好的用户体验：

```python
async for chunk in agent.run("任务"):
    print(chunk, end="", flush=True)
```

## 完整示例

```python
import asyncio
from derisk.agent.core_v2.builtin_agents import ReActReasoningAgent

async def main():
    # 创建Agent
    agent = ReActReasoningAgent.create(
        name="my-agent",
        model="gpt-4",
        max_steps=30
    )
    
    # 执行任务
    print("开始执行任务...\n")
    
    async for chunk in agent.run("帮我分析当前目录的Python项目结构"):
        print(chunk, end="", flush=True)
    
    # 获取统计
    stats = agent.get_statistics()
    print(f"\n\n执行统计: {stats}")

if __name__ == "__main__":
    asyncio.run(main())
```

## 更多信息

- **API文档**: 参考 `agent_base.py` 和各个Agent的实现
- **工具系统**: 参考 `tools_v2/` 目录
- **场景策略**: 参考 `scene_strategies_builtin.py`
- **配置示例**: 参考 `configs/agents/` 目录