# 极端场景分布式执行方案 - 最终设计

## 一、设计改进

根据讨论，已实现以下改进：

### 1. 持久化存储面向接口编程

```python
from derisk.agent.core_v2 import (
    StorageBackendType,
    StorageConfig,
    StateStorageFactory,
)

# 默认使用内存存储 (开发/测试)
config = StorageConfig(
    backend_type=StorageBackendType.MEMORY
)

# 文件存储 (单机生产)
config = StorageConfig(
    backend_type=StorageBackendType.FILE,
    base_dir=".agent_checkpoints",
)

# Redis 存储 (分布式)
config = StorageConfig(
    backend_type=StorageBackendType.REDIS,
    redis_url="redis://localhost:6379/0",
)

# 创建存储实例
storage = StateStorageFactory.create(config)
```

### 2. 主 Agent 休眠/唤醒机制

```python
from derisk.agent.core_v2 import (
    AgentSleepManager,
    SleepContext,
    WakeupSignal,
)

sleep_manager = AgentSleepManager(storage=storage)

# 主 Agent 进入休眠
context = await sleep_manager.sleep(
    task_id="main-task-001",
    reason="Waiting for 100 subtasks",
    wait_for_subtasks=["sub-001", "sub-002", ...],  # 子任务 ID 列表
    checkpoint_id="checkpoint-abc",
    max_sleep_seconds=86400 * 3,  # 最长休眠 3 天
)

# 子任务完成后唤醒主 Agent
await sleep_manager.wakeup(
    task_id="main-task-001",
    wakeup_reason="subtask_completed",
    triggered_by="sub-001",
    subagent_result={"success": True, "output": "..."},
)

# 等待唤醒
signal = await sleep_manager.wait_for_wakeup(
    task_id="main-task-001",
    timeout_seconds=86400,  # 最多等 1 天
)
```

### 3. 子 Agent 独立对话管理

```python
from derisk.agent.core_v2 import (
    SubagentConversationManager,
    SubagentConversation,
)

conversation_manager = SubagentConversationManager(
    storage=storage,
    sleep_manager=sleep_manager,
)

# 创建子 Agent 独立对话
conv = await conversation_manager.create_conversation(
    parent_task_id="main-task-001",
    subagent_name="analyzer",
    initial_context={"target": "target-001"},
)

# 每个对话有独立的 ID
print(conv.conversation_id)  # conv_xxx

# 更新对话状态
await conversation_manager.update_conversation_status(
    conversation_id=conv.conversation_id,
    status=SubagentConversationStatus.COMPLETED,
    result="分析完成",
)

# 查看进度
progress = await conversation_manager.get_conversation_progress("main-task-001")
print(f"完成: {progress['completed']}/{progress['total']}")
```

---

## 二、完整使用示例

### 场景 1: 长期任务 (2-3 天)

```python
from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

# 配置存储
config = StorageConfig(
    backend_type=StorageBackendType.FILE,  # 或 REDIS
    base_dir=".agent_checkpoints",
)

# 创建执行器
executor = DistributedTaskExecutor(storage_config=config)

# 执行长期任务
result = await executor.execute_main_task(
    task_id="long-analysis-001",
    agent=my_agent,
    goal="对 10TB 数据进行深度分析",
    resume=True,  # 自动从检查点恢复
)

# 检查进度
checkpoint = await storage.load("checkpoint:long-analysis-001")
```

### 场景 2: 100+ 子 Agent 执行

```python
from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

# 使用 Redis 存储 (分布式)
config = StorageConfig(
    backend_type=StorageBackendType.REDIS,
    redis_url="redis://localhost:6379/0",
)

executor = DistributedTaskExecutor(storage_config=config)

# 主任务 ID
parent_task_id = "batch-analysis-001"

# 创建 100 个子任务
targets = [f"target-{i}" for i in range(100)]
tasks = [f"分析目标: {target}" for target in targets]

# 委派给子 Agent (创建独立对话)
conversation_ids = await executor.delegate_to_subagents(
    parent_task_id=parent_task_id,
    subagent_name="analyzer",
    tasks=tasks,
    max_concurrent=10,  # 最多 10 个并行
)

print(f"创建了 {len(conversation_ids)} 个独立对话")
print("主 Agent 进入休眠...")

# 等待子 Agent 完成 (可能需要一天)
results = await executor.wait_for_subagents(
    parent_task_id=parent_task_id,
    timeout_seconds=86400,  # 最多等 1 天
)

print(f"唤醒原因: {results['wakeup_reason']}")
print(f"完成: {len(results['subagent_results'])}")

# 查看每个子对话的结果
for conv_id, result in results['subagent_results'].items():
    print(f"{conv_id}: {result['status']}")
```

---

## 三、架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Main Agent                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       execute_main_task()                            │   │
│  │  - 执行主任务                                                        │   │
│  │  - 自动保存检查点                                                    │   │
│  │  - 支持中断恢复                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    delegate_to_subagents()                          │   │
│  │  - 创建 100+ 独立对话                                                │   │
│  │  - 进入休眠状态                                                      │   │
│  │  - 等待子任务完成                                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 创建独立对话
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Subagent Conversations                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     ┌─────────────┐      │
│  │  Conv 001   │ │  Conv 002   │ │  Conv 003   │ ... │  Conv 100   │      │
│  │  (独立上下文)│ │  (独立上下文)│ │  (独立上下文)│     │  (独立上下文)│      │
│  └─────────────┘ └─────────────┘ └─────────────┘     └─────────────┘      │
│        │               │               │                   │               │
│        │ 完成后发送唤醒信号                                               │
│        └───────────────┴───────────────┴───────────────────┘               │
                                    │                                         │
                                    ▼                                         │
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Wakeup Mechanism                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  AgentSleepManager                                                  │   │
│  │  - 接收唤醒信号                                                      │   │
│  │  - 检查是否所有子任务完成                                             │   │
│  │  - 唤醒主 Agent                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Storage Layer (可插拔)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │ Memory       │  │ File         │  │ Redis        │                       │
│  │ (默认/测试)  │  │ (单机生产)   │  │ (分布式)     │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、API 参考

### 存储配置

| 类 | 描述 |
|----|------|
| `StorageBackendType` | 存储后端类型枚举 |
| `StorageConfig` | 存储配置 |
| `StateStorage` | 存储抽象接口 |
| `MemoryStateStorage` | 内存存储实现 |
| `FileStateStorage` | 文件存储实现 |
| `RedisStateStorage` | Redis 存储实现 |
| `StateStorageFactory` | 存储工厂 |

### 休眠管理

| 类 | 描述 |
|----|------|
| `AgentSleepManager` | 休眠管理器 |
| `SleepContext` | 休眠上下文 |
| `WakeupSignal` | 唤醒信号 |
| `MainAgentState` | 主 Agent 状态 |

### 对话管理

| 类 | 描述 |
|----|------|
| `SubagentConversationManager` | 对话管理器 |
| `SubagentConversation` | 子 Agent 对话 |
| `ConversationLink` | 对话关联 |
| `SubagentConversationStatus` | 对话状态 |

### 执行器

| 类 | 描述 |
|----|------|
| `DistributedTaskExecutor` | 分布式任务执行器 |

---

## 五、文件清单

| 文件 | 行数 | 描述 |
|------|------|------|
| `distributed_execution.py` | ~700 | 分布式执行完整实现 |
| `EXTREME_SCENARIO_ANALYSIS.md` | ~300 | 极端场景分析报告 |

---

## 六、与原计划对比

| 改进点 | 原方案 | 新方案 |
|--------|--------|--------|
| 持久化存储 | 绑定 Redis | 面向接口，支持多种后端 |
| 主 Agent 等待 | 未明确 | 休眠/唤醒机制 |
| 子 Agent 对话 | 无独立对话 | 每个子任务独立对话 |
| 对话关联 | 无 | ConversationLink |
| 进度跟踪 | 无 | 实时进度查询 |

---

## 七、下一步

1. 实现数据库存储 (PostgreSQL/MySQL)
2. 实现 S3 存储
3. 添加 Worker 进程池
4. 添加任务调度器
5. 添加监控面板