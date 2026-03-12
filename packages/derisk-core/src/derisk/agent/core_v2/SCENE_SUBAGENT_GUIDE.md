# 场景驱动的LLM自主多Agent使用指南

## 概述

本方案实现**场景驱动的LLM自主多Agent系统**，**三种模式全部支持LLM自主决策**：

| 模式 | 工具 | 用途 | LLM自主决策 |
|------|------|------|------------|
| **模式一** | `task` | 单个子Agent调用 | ✅ |
| **模式二** | `orchestrate` | 多Agent协作编排 | ✅ |
| **模式三** | `batch_task` | 分布式批量执行 | ✅ |

所有模式都是LLM通过Function Calling自主调用，**无程序硬编码流程**。

## 架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        场景配置决定可用子Agent                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SceneProfile {                                                             │
│    scene: TaskScene.CODING,                                                │
│    subagent_policy: SubagentPolicy {                                        │
│      enabled: true,                                                         │
│      subagents: ["explore", "code-reviewer", "tester", "oracle"],          │
│    }                                                                        │
│  }                                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Agent初始化时自动注入                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  注入3种工具：                                                               │
│  - task: 单个子Agent调用                                                     │
│  - orchestrate: 多Agent协作编排                                              │
│  - batch_task: 分布式批量执行                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LLM运行时自主决策                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LLM 看到工具列表：                                                          │
│  - read, write, edit, grep, glob, bash, ...                                │
│  - task (单Agent调用)                                                       │
│  - orchestrate (多Agent协作)                                                │
│  - batch_task (批量执行)                                                    │
│                                                                             │
│  LLM 自主决策：                                                              │
│  - 简单任务 → 调用 task(subagent="explore", ...)                            │
│  - 复杂协作 → 调用 orchestrate(goal="...", agents=[...])                    │
│  - 批量处理 → 调用 batch_task(subagent="...", tasks=[...])                  │
│                                                                             │
│  100% LLM自主决策，0% 程序硬编码                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 三种模式详解

### 模式一：task（单个子Agent调用）

适用于：需要专门能力的单一任务

```json
// LLM自主调用示例
{
  "name": "task",
  "arguments": {
    "subagent": "explore",
    "prompt": "搜索项目中所有认证相关的代码实现"
  }
}
```

### 模式二：orchestrate（多Agent协作编排）

适用于：复杂任务需要多个Agent协作

```json
// LLM自主调用示例
{
  "name": "orchestrate",
  "arguments": {
    "goal": "开发用户登录功能",
    "agents": ["analyst", "coder", "tester"],
    "strategy": "hierarchical"
  }
}
```

**执行策略**：
- `sequential`: 顺序执行
- `parallel`: 并行执行
- `hierarchical`: 按依赖关系层次执行

### 模式三：batch_task（分布式批量执行）

适用于：大量相似任务并行处理

```json
// LLM自主调用示例
{
  "name": "batch_task",
  "arguments": {
    "subagent": "analyst",
    "tasks": [
      "分析日志文件 log1.txt",
      "分析日志文件 log2.txt",
      "分析日志文件 log3.txt"
    ],
    "max_concurrent": 5
  }
}
```

**特性**：
- 主Agent自动休眠，不占用资源
- 支持分布式执行
- 支持中断恢复

## 快速开始

```python
from derisk.agent.core_v2 import (
    ReActReasoningAgent,
    TaskScene,
    inject_subagents_from_scene,
)

# 创建Agent
agent = ReActReasoningAgent.create(
    name="coding-assistant",
    model="gpt-4",
)

# 根据场景注入多Agent能力（自动配置3种工具）
await inject_subagents_from_scene(agent, TaskScene.CODING)

# LLM现在可以自主调用 task、orchestrate、batch_task 三种工具
async for chunk in agent.run("帮我分析这个项目的认证机制"):
    print(chunk)
```

注入后LLM可用的工具：
- `task` - 单个子Agent调用
- `orchestrate` - 多Agent协作编排
- `batch_task` - 分布式批量执行

### 方式二：自定义场景配置

```python
from derisk.agent.core_v2 import (
    SceneProfile,
    SceneProfileBuilder,
    TaskScene,
    SubagentPolicy,
    SubagentConfig,
    inject_subagents_from_profile,
)

# 创建自定义场景
custom_profile = (SceneProfileBuilder()
    .scene(TaskScene.CUSTOM)
    .name("My Custom Mode")
    .description("自定义场景，启用特定子Agent")
    .subagents(
        ["explore", "oracle", "tester"],  # 只启用这3个子Agent
        enabled=True,
        max_concurrent=2,
        default_timeout=600,
    )
    .build())

# 注入到Agent
agent = ReActReasoningAgent.create(name="custom-assistant", model="gpt-4")
await inject_subagents_from_profile(agent, custom_profile)
```

### 方式三：产品级集成

```python
from derisk.agent.core_v2 import (
    ProductAgentRegistry,
    AgentTeamConfig,
    SceneRegistry,
    inject_subagents_from_scene,
)

# 在产品启动时配置
registry = ProductAgentRegistry()

# 为产品绑定场景
profile = SceneRegistry.get(TaskScene.CODING)

# 创建Agent时自动注入
agent = ReActReasoningAgent.create(
    name="code-app-agent",
    model="gpt-4",
)

# 根据产品场景注入
await inject_subagents_from_profile(agent, profile)
```

## 内置场景配置

| 场景 | 启用的子Agent | 用途 |
|------|--------------|------|
| **CODING** | explore, code-reviewer, tester, oracle | 代码开发 |
| **ANALYSIS** | explore, analyst, librarian | 数据分析 |
| **RESEARCH** | explore, librarian, oracle | 深度研究 |
| **DEBUG** | explore, analyst, code-reviewer | Bug调试 |
| **REFACTORING** | explore, code-reviewer, oracle, tester | 代码重构 |
| **TESTING** | explore, tester, code-reviewer | 测试编写 |
| **DOCUMENTATION** | explore | 文档编写 |
| **CREATIVE** | (无) | 创意写作 |
| **GENERAL** | general | 通用任务 |

## 内置子Agent

| 子Agent | 能力 | 描述 |
|---------|------|------|
| **explore** | code-search, file-search, structure-analysis | 代码库探索 |
| **code-reviewer** | code-review, security-audit, quality-check | 代码审查 |
| **librarian** | doc-search, api-reference, best-practices | 文档检索 |
| **oracle** | architecture, design-review, problem-analysis | 高级顾问 |
| **tester** | test-generation, test-execution | 测试编写 |
| **coder** | coding, implementation, debugging | 代码实现 |
| **analyst** | data-analysis, log-analysis | 数据分析 |
| **general** | general, reasoning | 通用助手 |

## LLM调用示例

### 模式一：task（单Agent调用）

```json
{
  "name": "task",
  "arguments": {
    "subagent": "explore",
    "prompt": "搜索项目中所有认证相关的代码实现"
  }
}
```

### 模式二：orchestrate（多Agent协作）

```json
{
  "name": "orchestrate",
  "arguments": {
    "goal": "开发用户登录功能",
    "agents": ["analyst", "coder", "tester"],
    "strategy": "hierarchical"
  }
}
```

**strategy说明**：
- `sequential`: Agent顺序执行
- `parallel`: Agent并行执行
- `hierarchical`: 按依赖关系层次执行（推荐）

### 模式三：batch_task（批量执行）

```json
{
  "name": "batch_task",
  "arguments": {
    "subagent": "analyst",
    "tasks": [
      "分析日志文件 log1.txt",
      "分析日志文件 log2.txt",
      "分析日志文件 log3.txt"
    ],
    "max_concurrent": 5
  }
}
```

**适用场景**：
- 分析100个日志文件
- 审查50个源代码文件
- 测试多个API端点

## 高级配置

### 自定义子Agent

```python
from derisk.agent.core_v2 import SubagentConfig, register_subagent

# 注册自定义子Agent
custom_subagent = SubagentConfig(
    name="security-scanner",
    description="安全扫描Agent，检查代码漏洞",
    capabilities=["security-scan", "vulnerability-detect"],
    allowed_tools=["read", "grep", "glob"],
    max_steps=15,
    timeout=600,
)

# 注册到内置列表
register_subagent(custom_subagent)

# 在场景中使用
profile = (SceneProfileBuilder()
    .scene(TaskScene.CUSTOM)
    .name("Security Review Mode")
    .subagents(["explore", "security-scanner", "code-reviewer"])
    .build())
```

### 控制子Agent权限

```python
from derisk.agent.core_v2 import SubagentConfig

# 创建受限子Agent
limited_subagent = SubagentConfig(
    name="readonly-explorer",
    description="只读探索Agent",
    capabilities=["search"],
    allowed_tools=["read", "grep", "glob"],  # 只允许读取工具
    denied_tools=["write", "edit", "bash"],   # 禁止修改工具
    max_steps=10,
)
```

## 产品集成示例

```python
# 完整的产品集成示例
from derisk.agent.core_v2 import (
    ReActReasoningAgent,
    TaskScene,
    SceneProfileBuilder,
    inject_subagents_from_scene,
    inject_subagents_from_profile,
)

async def create_agent_for_product(app_code: str, user_query: str):
    """根据产品创建配置好的Agent"""
    
    # 1. 确定场景（根据产品类型）
    scene_map = {
        "code_app": TaskScene.CODING,
        "data_app": TaskScene.ANALYSIS,
        "chat_app": TaskScene.GENERAL,
    }
    scene = scene_map.get(app_code, TaskScene.GENERAL)
    
    # 2. 创建Agent
    agent = ReActReasoningAgent.create(
        name=f"{app_code}-agent",
        model="gpt-4",
    )
    
    # 3. 注入子Agent能力
    await inject_subagents_from_scene(agent, scene)
    
    # 4. 执行用户请求（LLM自主决策是否调用子Agent）
    result = []
    async for chunk in agent.run(user_query):
        result.append(chunk)
    
    return "".join(result)


# 使用
result = await create_agent_for_product(
    app_code="code_app",
    user_query="分析这个项目的认证流程，并找出潜在的安全问题"
)
```

## 总结

### 三种模式对比

| 模式 | 工具 | 用途 | 并发 | 执行时长 |
|------|------|------|------|----------|
| **模式一** | `task` | 单个子Agent调用 | 1个 | 秒级/分钟级 |
| **模式二** | `orchestrate` | 多Agent协作 | 2-5个 | 分钟级 |
| **模式三** | `batch_task` | 分布式批量执行 | 10-50个 | 小时级/天级 |

### 核心特性

| 特性 | 说明 |
|------|------|
| ✅ **场景驱动** | 通过场景配置决定启用哪些子Agent |
| ✅ **LLM自主** | 三种模式全部支持LLM自主决策，无程序硬编码 |
| ✅ **自动注入** | 3种工具自动注入到Agent |
| ✅ **灵活扩展** | 支持自定义子Agent和场景 |
| ✅ **产品友好** | 支持产品级场景绑定 |

### 关键设计

```
场景配置 → 自动注入 → LLM自主决策 → 执行

无程序硬编码流程，100%由LLM决策何时、如何调用子Agent
```