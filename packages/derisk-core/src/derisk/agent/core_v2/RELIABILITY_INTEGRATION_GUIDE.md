# Agent Loop 可靠性改进 - 完整集成指南

## 概述

本指南说明如何在 Core V1 和 Core V2 Agent 中使用新的可靠性机制。

## 实现的模块

| 文件 | 描述 |
|------|------|
| `state_machine.py` | 状态机执行模式 |
| `smart_checkpoint.py` | 智能检查点管理 |
| `hierarchical_memory.py` | 分层记忆系统 |
| `task_orchestrator.py` | DAG 任务编排 |
| `agent_metrics.py` | 健康监控 |
| `reliability_adapter.py` | 通用可靠性适配器 |
| `reliability_integration.py` | Core V1 深度集成 |

---

## 一、ReActMasterAgent (Core V1) 集成方式

### 方式 1: 简单包装 (推荐用于快速集成)

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import make_reliable

# 创建 Agent
agent = ReActMasterAgent()

# 添加可靠性能力
reliable = make_reliable(agent)

# 执行
result = await reliable.run("分析系统日志")

# 获取结果
if result["success"]:
    print(f"响应: {result['response']}")
    print(f"检查点: {result['checkpoint_id']}")
else:
    print(f"失败: {result['error']}")
    # 可以使用 checkpoint_id 恢复
```

### 方式 2: 完整状态机模式 (推荐用于长任务)

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import with_state_machine

agent = ReActMasterAgent()
executor = with_state_machine(agent)

result = await executor.execute("分析系统日志并生成报告")

print(f"最终状态: {result.final_state.name}")
print(f"总步数: {result.total_steps}")
print(f"健康分数: {executor.get_health_score()}")
```

### 方式 3: 深度集成 - generate_reply 包装

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import make_react_master_reliable

agent = ReActMasterAgent()
wrapper = make_react_master_reliable(
    agent,
    checkpoint_strategy="adaptive",
)

from derisk.agent import AgentMessage
message = AgentMessage(content="分析日志")

result = await wrapper.generate_reply_with_reliability(message)

# 检查点信息在 extra 中
print(f"检查点: {result.extra['checkpoint_id']}")
print(f"健康状态: {result.extra['health']}")
```

### 方式 4: 深度集成 - 状态机驱动执行

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import with_state_machine_execution

agent = ReActMasterAgent()
executor = with_state_machine_execution(agent)

# 执行
result = await executor.execute("分析日志")

print(f"成功: {result['success']}")
print(f"步数: {result['step']}")
print(f"健康分数: {result['health']['health_score']}")

# 从检查点恢复
result = await executor.execute("继续", resume_checkpoint=checkpoint_id)
```

### 方式 5: Mixin 模式 (创建新的 Agent 类)

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import ReActMasterReliabilityMixin

class ReliableReActMasterAgent(ReActMasterAgent, ReActMasterReliabilityMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.init_reliability(
            checkpoint_strategy="adaptive",
            checkpoint_interval=10,
        )

# 使用
agent = ReliableReActMasterAgent()

# 执行中可以手动保存检查点
checkpoint_id = await agent._save_checkpoint_reliable("中断点")

# 恢复
await agent._restore_checkpoint_reliable(checkpoint_id)
```

---

## 二、ReActReasoningAgent (Core V2) 集成方式

### 方式 1: 简单包装

```python
from derisk.agent.core_v2 import (
    ReActReasoningAgent,
    AgentInfo,
    LLMFactory,
    LLMConfig,
    make_reliable,
)

info = AgentInfo(name="analyst", max_steps=50)
llm_config = LLMConfig(model="gpt-4", api_key="...")
llm_adapter = LLMFactory.create(llm_config)

agent = ReActReasoningAgent(info=info, llm_adapter=llm_adapter)
reliable = make_reliable(agent)

result = await reliable.run("分析代码库")
```

### 方式 2: 内置可靠性特性

ReActReasoningAgent 已经内置了部分可靠性特性:

```python
agent = ReActReasoningAgent(
    info=info,
    llm_adapter=llm_adapter,
    # 内置可靠性配置
    enable_doom_loop_detection=True,
    enable_output_truncation=True,
    enable_context_compaction=True,
    enable_compaction_pipeline=True,
)
```

---

## 三、产品层集成 (推荐)

```python
from derisk.agent.core_v2 import ReliableConversationService

# 创建服务
service = ReliableConversationService(
    redis_url="redis://localhost:6379/0"
)

# 创建会话
session_id = await service.create_session("session-001")

# 对话
result = await service.chat(session_id, "分析日志")
print(f"响应: {result['response']}")
print(f"检查点: {result['checkpoint_id']}")

# 暂停
checkpoint_id = await service.pause_session(session_id)

# 恢复
await service.resume_session(session_id)
result = await service.chat(session_id, "继续", resume=True)

# 健康监控
health = service.get_health()
print(f"健康分数: {health['health_score']}")
```

---

## 四、检查点恢复

```python
# 场景: 长任务执行中断

from derisk.agent.core_v2 import make_reliable

agent = ReActMasterAgent()
reliable = make_reliable(agent)

# 第一次执行 (可能中断)
try:
    result = await reliable.run("复杂任务")
except Exception:
    checkpoint_id = result["checkpoint_id"]
    print(f"任务中断，检查点: {checkpoint_id}")

# 稍后恢复
result = await reliable.run("继续执行", resume_checkpoint=checkpoint_id)
```

---

## 五、配置选项

```python
from derisk.agent.core_v2 import (
    ReliabilityConfig,
    CheckpointStrategy,
    RedisStateStore,
    FileStateStore,
)

config = ReliabilityConfig(
    # 检查点策略
    checkpoint_strategy=CheckpointStrategy.ADAPTIVE,
    
    # 状态存储
    state_store=RedisStateStore("redis://localhost:6379/0"),
    
    # 记忆配置
    working_memory_tokens=8000,
    episodic_memory_tokens=32000,
    semantic_memory_tokens=128000,
    
    # 检查点配置
    checkpoint_interval=10,
    max_checkpoints=20,
    
    # 指标
    enable_metrics=True,
)

agent = ReActMasterAgent()
reliable = make_reliable(agent, config)
```

---

## 六、API 参考

### 便捷函数

| 函数 | 描述 |
|------|------|
| `make_reliable(agent)` | 为任意 Agent 添加可靠性能力 |
| `with_state_machine(agent)` | 使用完整状态机模式 |
| `make_react_master_reliable(agent)` | Core V1 Agent 专用包装器 |
| `with_state_machine_execution(agent)` | Core V1 状态机执行器 |

### 主要类

| 类 | 描述 |
|------|------|
| `ReliabilityAdapter` | 通用可靠性适配器 |
| `StateMachineAgentExecutor` | 状态机执行器 |
| `ReliableConversationService` | 产品层服务 |
| `ReActMasterReliabilityMixin` | Mixin 类 |

### 核心组件

| 类 | 描述 |
|------|------|
| `StateMachineAgent` | 状态机 Agent |
| `SmartCheckpointManager` | 智能检查点管理 |
| `HierarchicalMemoryManager` | 分层记忆管理 |
| `TaskOrchestrator` | 任务编排器 |
| `AgentMetrics` | 健康监控 |

---

## 七、文件结构

```
packages/derisk-core/src/derisk/agent/core_v2/
├── state_machine.py              # 状态机实现 (~550 行)
├── smart_checkpoint.py           # 智能检查点 (~580 行)
├── hierarchical_memory.py        # 分层记忆 (~530 行)
├── task_orchestrator.py          # 任务编排 (~500 行)
├── agent_metrics.py              # 健康监控 (~450 行)
├── reliability_adapter.py        # 通用适配器 (~350 行)
├── reliability_integration.py    # Core V1 集成 (~400 行)
├── RELIABILITY_USAGE_EXAMPLES.py # 使用示例 (~280 行)
└── test_agent_loop_reliability.py # 测试 (~480 行)
```

---

## 八、最佳实践

1. **快速集成** → 使用 `make_reliable(agent)`
2. **长任务** → 使用 `with_state_machine(agent)`
3. **产品层** → 使用 `ReliableConversationService`
4. **分布式** → 配置 `RedisStateStore`
5. **健康监控** → 定期检查 `health_score`

---

## 九、总结

| Agent 类型 | 推荐集成方式 | 代码示例 |
|------------|--------------|----------|
| ReActMasterAgent | `make_reliable(agent)` | `result = await make_reliable(agent).run("任务")` |
| ReActMasterAgent (长任务) | `with_state_machine(agent)` | `await with_state_machine(agent).execute("任务")` |
| ReActReasoningAgent | `make_reliable(agent)` | `result = await make_reliable(agent).run("任务")` |
| 产品层 | `ReliableConversationService` | `await service.chat(session_id, "任务")` |