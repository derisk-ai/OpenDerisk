# Agent Loop 可靠性架构 - 完整方案文档

> 版本: v5.0
> 更新时间: 2026-03-10
> 适用场景: 长期任务、大规模子Agent编排、分布式执行

---

## 目录

1. [概述](#一概述)
2. [核心组件](#二核心组件)
3. [持久化存储](#三持久化存储)
4. [状态机执行](#四状态机执行)
5. [智能检查点](#五智能检查点)
6. [分层记忆系统](#六分层记忆系统)
7. [任务编排](#七任务编排)
8. [健康监控](#八健康监控)
9. [分布式执行](#九分布式执行)
10. [Agent集成](#十agent集成)
11. [使用示例](#十一使用示例)
12. [文件清单](#十二文件清单)

---

## 一、概述

### 1.1 解决的问题

| 问题 | 描述 |
|------|------|
| 长期任务 | 任务需要运行 2-3 天，支持中断恢复 |
| 大规模编排 | 100+ 子Agent并行执行，主Agent等待完成 |
| 状态丢失 | 进程崩溃后状态丢失，无法恢复 |
| 上下文爆炸 | 长任务上下文无限增长 |
| 循环僵死 | Agent陷入无限循环 |
| 子Agent管理 | 缺乏独立的子Agent对话和进度跟踪 |

### 1.2 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Application Layer                                    │
│  ProductAgent / ReActMasterAgent / ReActReasoningAgent                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Integration Layer                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     ReliabilityAdapter                              │    │
│  │  make_reliable(agent) / with_state_machine(agent)                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                  DistributedTaskExecutor                            │    │
│  │  execute_main_task() / delegate_to_subagents()                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Reliability Layer                                     │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐            │
│  │StateMachineAgent │ │SmartCheckpoint   │ │HierarchicalMemory│            │
│  │  (状态机执行)    │ │   Manager        │ │   Manager        │            │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘            │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐            │
│  │TaskOrchestrator  │ │  AgentMetrics    │ │AgentSleepManager │            │
│  │  (DAG编排)       │ │  (健康监控)      │ │  (休眠唤醒)      │            │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Storage Layer (可插拔)                                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │  Memory    │  │   File     │  │   Redis    │  │  Database  │            │
│  │  (默认)    │  │  (单机)    │  │  (分布式)  │  │   (TODO)   │            │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、核心组件

### 2.1 组件清单

| 组件 | 文件 | 功能 |
|------|------|------|
| StateMachineAgent | state_machine.py | 形式化状态机执行 |
| SmartCheckpointManager | smart_checkpoint.py | 自适应检查点策略 |
| HierarchicalMemoryManager | hierarchical_memory.py | 三层记忆架构 |
| TaskOrchestrator | task_orchestrator.py | DAG任务编排 |
| AgentMetrics | agent_metrics.py | 健康监控诊断 |
| AgentSleepManager | distributed_execution.py | 主Agent休眠唤醒 |
| SubagentConversationManager | distributed_execution.py | 子Agent对话管理 |
| StateStorage | distributed_execution.py | 持久化存储抽象 |

### 2.2 导入方式

```python
from derisk.agent.core_v2 import (
    # 核心组件
    StateMachineAgent,
    SmartCheckpointManager,
    HierarchicalMemoryManager,
    TaskOrchestrator,
    AgentMetrics,
    
    # 分布式组件
    AgentSleepManager,
    SubagentConversationManager,
    DistributedTaskExecutor,
    
    # 存储
    StorageBackendType,
    StorageConfig,
    StateStorage,
    MemoryStateStorage,
    FileStateStorage,
    RedisStateStorage,
    StateStorageFactory,
    
    # 集成
    ReliabilityAdapter,
    make_reliable,
    with_state_machine,
)
```

---

## 三、持久化存储

### 3.1 设计原则

**面向接口编程，不绑定特定后端**

```python
class StateStorage(ABC):
    @abstractmethod
    async def save(self, key: str, data: Dict[str, Any]) -> bool: ...
    
    @abstractmethod
    async def load(self, key: str) -> Optional[Dict[str, Any]]: ...
    
    @abstractmethod
    async def delete(self, key: str) -> bool: ...
    
    @abstractmethod
    async def exists(self, key: str) -> bool: ...
    
    @abstractmethod
    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool: ...
    
    @abstractmethod
    async def release_lock(self, key: str) -> bool: ...
```

### 3.2 后端类型

| 后端 | 类型 | 适用场景 | 特性 |
|------|------|----------|------|
| Memory | `MEMORY` | 开发/测试 | 无持久化，进程内 |
| File | `FILE` | 单机生产 | 文件持久化，支持压缩 |
| Redis | `REDIS` | 分布式 | 分布式锁，跨进程共享 |
| Database | `DATABASE` | TODO | 关系型数据库 |
| S3 | `S3` | TODO | 对象存储 |

### 3.3 使用示例

```python
from derisk.agent.core_v2 import (
    StorageBackendType,
    StorageConfig,
    StateStorageFactory,
)

# 方式1: 默认内存存储
storage = StateStorageFactory.create_default()

# 方式2: 文件存储
config = StorageConfig(
    backend_type=StorageBackendType.FILE,
    base_dir=".agent_checkpoints",
)
storage = StateStorageFactory.create(config)

# 方式3: Redis存储
config = StorageConfig(
    backend_type=StorageBackendType.REDIS,
    redis_url="redis://localhost:6379/0",
    key_prefix="agent:",
    ttl_seconds=86400 * 7,  # 7天过期
)
storage = StateStorageFactory.create(config)

# 使用
await storage.save("task:001", {"step": 10, "status": "running"})
data = await storage.load("task:001")
await storage.delete("task:001")

# 分布式锁
if await storage.acquire_lock("task:001", ttl_seconds=30):
    try:
        # 执行任务
        pass
    finally:
        await storage.release_lock("task:001")
```

---

## 四、状态机执行

### 4.1 状态定义

```
IDLE ─────────► INITIALIZING
                       │
                       ▼
                   THINKING ◄────────────┐
                       │                 │
                       ▼                 │
                    ACTING               │
                       │                 │
                       ▼                 │
                   VERIFYING ────────────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
         COMPLETED          COMPACTING
                                 │
                                 ▼
                             THINKING

特殊状态:
- PAUSED: 暂停执行
- RECOVERING: 从检查点恢复
- FAILED: 失败终止
```

### 4.2 状态转换规则

```python
ALLOWED_TRANSITIONS = {
    AgentState.IDLE: {AgentState.INITIALIZING},
    AgentState.INITIALIZING: {AgentState.THINKING, AgentState.FAILED},
    AgentState.THINKING: {
        AgentState.ACTING, 
        AgentState.PAUSED, 
        AgentState.FAILED,
        AgentState.COMPLETED
    },
    AgentState.ACTING: {
        AgentState.VERIFYING, 
        AgentState.PAUSED, 
        AgentState.FAILED,
        AgentState.THINKING
    },
    AgentState.VERIFYING: {
        AgentState.THINKING, 
        AgentState.COMPLETED, 
        AgentState.COMPACTING,
        AgentState.FAILED
    },
    AgentState.PAUSED: {
        AgentState.RECOVERING, 
        AgentState.THINKING,
        AgentState.FAILED
    },
    AgentState.RECOVERING: {
        AgentState.THINKING, 
        AgentState.FAILED
    },
    AgentState.COMPACTING: {
        AgentState.THINKING,
        AgentState.FAILED
    },
}
```

### 4.3 使用示例

```python
from derisk.agent.core_v2 import StateMachineAgent

async def think(input_msg):
    return await llm.generate(input_msg)

async def act(thinking):
    return await execute_tool(thinking)

async def verify(result):
    return (True, "verified")

agent = StateMachineAgent(
    think_func=think,
    act_func=act,
    verify_func=verify,
    max_steps=100,
)

result = await agent.execute("分析系统日志")

print(f"最终状态: {result.final_state.name}")
print(f"总步数: {result.total_steps}")
print(f"成功: {result.success}")
```

---

## 五、智能检查点

### 5.1 检查点策略

| 策略 | 描述 | 适用场景 |
|------|------|----------|
| TIME_BASED | 按时间间隔 | 固定周期保存 |
| STEP_BASED | 按步数间隔 | 确定性保存 |
| MILESTONE_BASED | 按里程碑 | 关键节点保存 |
| ADAPTIVE | 自适应 | 动态调整 (推荐) |

### 5.2 自适应策略

```python
# 根据失败率动态调整检查点间隔
if failure_rate > 0.2:
    # 高失败率，更频繁检查点
    recommended_interval = max(3, current_interval // 2)
elif failure_rate < 0.05:
    # 低失败率，恢复默认间隔
    recommended_interval = min(current_interval + 2, default_interval)
```

### 5.3 使用示例

```python
from derisk.agent.core_v2 import (
    SmartCheckpointManager,
    CheckpointStrategy,
    RedisStateStorage,
)

checkpoint_manager = SmartCheckpointManager(
    strategy=CheckpointStrategy.ADAPTIVE,
    checkpoint_store=RedisStateStorage(redis_url="redis://localhost:6379/0"),
    checkpoint_interval=10,
    max_checkpoints=20,
)

# 判断是否需要检查点
if await checkpoint_manager.should_checkpoint(step, state, context):
    checkpoint = await checkpoint_manager.create_checkpoint(
        execution_id="exec-001",
        checkpoint_type=CheckpointType.AUTOMATIC,
        state={"step": step, "data": current_state},
        step_index=step,
    )

# 恢复检查点
restored = await checkpoint_manager.restore_checkpoint(checkpoint.checkpoint_id)
if restored:
    step = restored["step_index"]
    state = restored["state"]
```

---

## 六、分层记忆系统

### 6.1 三层架构

```
┌─────────────────────────────────────────────┐
│  WORKING MEMORY (8K tokens)                 │
│  - 当前任务相关                              │
│  - 快速访问                                  │
│  - 容量有限                                  │
└─────────────────────────────────────────────┘
                    │ 降级
                    ▼
┌─────────────────────────────────────────────┐
│  EPISODIC MEMORY (32K tokens)               │
│  - 近期事件序列                              │
│  - 中期存储                                  │
│  - 事件关联                                  │
└─────────────────────────────────────────────┘
                    │ 压缩
                    ▼
┌─────────────────────────────────────────────┐
│  SEMANTIC MEMORY (128K tokens)              │
│  - 长期知识                                  │
│  - 语义摘要                                  │
│  - 概念关联                                  │
└─────────────────────────────────────────────┘
```

### 6.2 使用示例

```python
from derisk.agent.core_v2 import (
    HierarchicalMemoryManager,
    MemoryLayer,
    MemoryType,
)

memory_manager = HierarchicalMemoryManager(
    working_memory_tokens=8000,
    episodic_memory_tokens=32000,
    semantic_memory_tokens=128000,
)

# 添加记忆
memory_id = await memory_manager.add_memory(
    content="用户要求分析日志",
    memory_type=MemoryType.CONVERSATION,
    importance=0.8,
    layer=MemoryLayer.WORKING,
)

# 检索相关记忆
relevant = await memory_manager.retrieve_relevant(
    query="日志分析",
    max_tokens=4000,
)

# 查看使用情况
usage = memory_manager.get_layer_usage()
# {"working": {"usage_percent": 60}, ...}
```

---

## 七、任务编排

### 7.1 DAG编排

```python
from derisk.agent.core_v2 import (
    TaskOrchestrator,
    Task,
    TaskPriority,
    RetryConfig,
    RetryPolicy,
)

orchestrator = TaskOrchestrator(max_concurrent=10)

# 添加有依赖的任务
orchestrator.add_task(Task(
    task_id="fetch",
    name="Fetch Data",
    execute_func=fetch_data,
    priority=TaskPriority.HIGH,
))

orchestrator.add_task(Task(
    task_id="process",
    name="Process Data",
    execute_func=process_data,
    dependencies=["fetch"],  # 依赖 fetch 任务
    retry_config=RetryConfig(
        policy=RetryPolicy.EXPONENTIAL,
        max_retries=3,
    ),
    compensation_handler=rollback,  # 失败补偿
))

# 执行
result = await orchestrator.execute()
```

### 7.2 重试策略

| 策略 | 描述 |
|------|------|
| NONE | 不重试 |
| FIXED | 固定间隔重试 |
| LINEAR | 线性退避重试 |
| EXPONENTIAL | 指数退避重试 (推荐) |

---

## 八、健康监控

### 8.1 健康分数计算

```
健康分数 = 100 
         - 步骤耗时惩罚 (25%)
         - 无效转换惩罚 (20%)
         - 检查点大小惩罚 (15%)
         - 内存使用惩罚 (20%)
         - 错误率惩罚 (20%)
```

### 8.2 使用示例

```python
from derisk.agent.core_v2 import AgentMetrics

metrics = AgentMetrics()

# 记录步骤
metrics.record_step(
    step_index=10,
    state="THINKING",
    duration_ms=150.5,
    success=True,
    tokens_used=100,
)

# 记录状态转换
metrics.record_transition(
    from_state="THINKING",
    to_state="ACTING",
    duration_ms=10.5,
)

# 获取健康报告
report = metrics.get_health_report()
print(f"健康分数: {report.health_score}")
print(f"健康状态: {report.health_status.value}")
print(f"问题: {report.issues}")
print(f"建议: {report.recommendations}")
```

---

## 九、分布式执行

### 9.1 主Agent休眠机制

```python
from derisk.agent.core_v2 import AgentSleepManager

sleep_manager = AgentSleepManager(storage=storage)

# 主Agent进入休眠
context = await sleep_manager.sleep(
    task_id="main-task-001",
    reason="Waiting for 100 subtasks",
    wait_for_subtasks=["sub-001", "sub-002", ...],
    checkpoint_id="checkpoint-abc",
    max_sleep_seconds=86400 * 3,  # 最长3天
)

# 子任务完成后唤醒
await sleep_manager.wakeup(
    task_id="main-task-001",
    wakeup_reason="subtask_completed",
    triggered_by="sub-001",
    subagent_result={"success": True, "output": "..."},
)

# 等待唤醒
signal = await sleep_manager.wait_for_wakeup(
    task_id="main-task-001",
    timeout_seconds=86400,
)
```

### 9.2 子Agent独立对话

```python
from derisk.agent.core_v2 import (
    SubagentConversationManager,
    SubagentConversationStatus,
)

conversation_manager = SubagentConversationManager(
    storage=storage,
    sleep_manager=sleep_manager,
)

# 创建独立对话
conv = await conversation_manager.create_conversation(
    parent_task_id="main-task-001",
    subagent_name="analyzer",
    initial_context={"target": "target-001"},
)

# 每个对话独立
print(conv.conversation_id)  # conv_xxx

# 更新状态
await conversation_manager.update_conversation_status(
    conversation_id=conv.conversation_id,
    status=SubagentConversationStatus.COMPLETED,
    result="分析完成",
)

# 查看进度
progress = await conversation_manager.get_conversation_progress("main-task-001")
print(f"完成: {progress['completed']}/{progress['total']}")

# 收集结果
results = await conversation_manager.collect_child_results("main-task-001")
```

---

## 十、Agent集成

### 10.1 Core V1 Agent (ReActMasterAgent)

```python
from derisk.agent.expand.react_master_agent import ReActMasterAgent
from derisk.agent.core_v2 import make_reliable, with_state_machine

# 方式1: 简单包装
agent = ReActMasterAgent()
reliable = make_reliable(agent)
result = await reliable.run("分析日志")

# 方式2: 完整状态机
agent = ReActMasterAgent()
executor = with_state_machine(agent)
result = await executor.execute("分析日志")
print(f"健康分数: {executor.get_health_score()}")
```

### 10.2 Core V2 Agent (ReActReasoningAgent)

```python
from derisk.agent.core_v2 import ReActReasoningAgent, make_reliable

agent = ReActReasoningAgent.create(name="analyst")
reliable = make_reliable(agent)
result = await reliable.run("分析代码库")
```

### 10.3 产品层集成

```python
from derisk.agent.core_v2 import DistributedTaskExecutor, StorageConfig

# 配置Redis存储
config = StorageConfig(
    backend_type=StorageBackendType.REDIS,
    redis_url="redis://localhost:6379/0",
)

executor = DistributedTaskExecutor(storage_config=config)

# 执行主任务
result = await executor.execute_main_task(
    task_id="batch-001",
    agent=main_agent,
    goal="分析100个目标",
    resume=True,
)

# 委派100个子任务
conversation_ids = await executor.delegate_to_subagents(
    parent_task_id="batch-001",
    subagent_name="analyzer",
    tasks=[f"分析目标{i}" for i in range(100)],
    max_concurrent=10,
)

# 等待完成
results = await executor.wait_for_subagents("batch-001")
```

---

## 十一、使用示例

### 场景1: 长期任务 (2-3天)

```python
from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

# 文件存储 (单机)
config = StorageConfig(
    backend_type=StorageBackendType.FILE,
    base_dir=".agent_checkpoints",
)

executor = DistributedTaskExecutor(storage_config=config)

# 执行长期任务
result = await executor.execute_main_task(
    task_id="long-analysis-001",
    agent=my_agent,
    goal="对10TB数据进行深度分析",
    resume=True,  # 自动从检查点恢复
)

# 如果中断，下次运行会自动恢复
```

### 场景2: 100+ 子Agent并行

```python
from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

# Redis存储 (分布式)
config = StorageConfig(
    backend_type=StorageBackendType.REDIS,
    redis_url="redis://localhost:6379/0",
)

executor = DistributedTaskExecutor(storage_config=config)

# 创建100个子任务
targets = [f"target-{i}" for i in range(100)]
tasks = [f"分析目标: {target}" for target in targets]

# 委派
conversation_ids = await executor.delegate_to_subagents(
    parent_task_id="batch-001",
    subagent_name="analyzer",
    tasks=tasks,
    max_concurrent=10,
)

print(f"创建了 {len(conversation_ids)} 个独立对话")
print("主Agent进入休眠...")

# 等待子Agent完成 (可能需要一天)
results = await executor.wait_for_subagents(
    parent_task_id="batch-001",
    timeout_seconds=86400,
)

print(f"唤醒原因: {results['wakeup_reason']}")
print(f"完成: {len(results['subagent_results'])}")

# 中断后恢复
# results = await executor.wait_for_subagents("batch-001")  # 自动恢复
```

---

## 十二、文件清单

### 12.1 核心模块

| 文件 | 行数 | 描述 |
|------|------|------|
| `state_machine.py` | ~550 | 状态机执行 |
| `smart_checkpoint.py` | ~580 | 智能检查点 |
| `hierarchical_memory.py` | ~530 | 分层记忆 |
| `task_orchestrator.py` | ~500 | 任务编排 |
| `agent_metrics.py` | ~450 | 健康监控 |
| `distributed_execution.py` | ~700 | 分布式执行 |
| `reliability_adapter.py` | ~350 | 集成适配器 |
| `reliability_integration.py` | ~400 | Core V1集成 |

### 12.2 文档

| 文件 | 描述 |
|------|------|
| `ARCHITECTURE.md` | 架构文档 (已更新) |
| `RELIABILITY_INTEGRATION_GUIDE.md` | 集成指南 |
| `DISTRIBUTED_EXECUTION_GUIDE.md` | 分布式执行指南 |
| `EXTREME_SCENARIO_ANALYSIS.md` | 极端场景分析 |

### 12.3 测试

| 文件 | 描述 |
|------|------|
| `test_agent_loop_reliability.py` | 核心组件测试 |

---

## 十三、总结

### 13.1 能力对比

| 能力 | Core V1 | Core V2 + 扩展 |
|------|---------|----------------|
| 执行模式 | while循环 | 状态机 |
| 检查点 | ❌ | ✅ 多策略 |
| 记忆管理 | 扁平 | 三层分层 |
| 任务编排 | ❌ | ✅ DAG |
| 健康监控 | ❌ | ✅ 完整报告 |
| 存储后端 | ❌ | ✅ 可插拔 |
| 主Agent休眠 | ❌ | ✅ 支持 |
| 子Agent对话 | ❌ | ✅ 独立管理 |
| 分布式 | ❌ | ✅ Redis支持 |

### 13.2 快速开始

```python
from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

# 创建执行器
executor = DistributedTaskExecutor()

# 执行任务
result = await executor.execute_main_task(
    task_id="task-001",
    agent=my_agent,
    goal="分析数据",
)

# 委派子任务
ids = await executor.delegate_to_subagents(
    parent_task_id="task-001",
    subagent_name="analyzer",
    tasks=["任务1", "任务2", "任务3"],
)

# 等待完成
results = await executor.wait_for_subagents("task-001")
```

### 13.3 后续计划

| 优先级 | 任务 | 工作量 |
|--------|------|--------|
| P0 | Worker进程池 | 2天 |
| P1 | 数据库存储 | 1天 |
| P1 | 任务调度器 | 2天 |
| P2 | 监控面板 | 3天 |
| P2 | S3存储 | 1天 |