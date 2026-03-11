# 极端大规模场景架构分析报告

## 一、需求场景

### 场景 1: 长期持续任务 (2-3 天)
- 任务需要持续运行 2-3 天
- 支持中断后恢复执行
- 需要持久化检查点

### 场景 2: 大规模子 Agent 编排 (100+ 目标)
- 主 Agent 需要对 100+ 目标进行处理
- 每个目标可能需要启动一个子 Agent
- 子 Agent 可能运行一天
- 主 Agent 需要等待所有子 Agent 完成

---

## 二、当前架构能力评估

### Core V1 (ReActMasterAgent) 能力

| 能力 | 支持程度 | 说明 |
|------|----------|------|
| 基础执行循环 | ✅ 完整 | while 循环驱动 |
| 内存状态管理 | ⚠️ 有限 | 仅内存中，进程崩溃丢失 |
| 检查点机制 | ❌ 缺失 | 无持久化检查点 |
| 中断恢复 | ❌ 缺失 | 无法从中断点恢复 |
| 子 Agent 管理 | ⚠️ 有限 | 无内置子 Agent 支持 |
| 并行执行 | ❌ 缺失 | 单线程执行 |
| 分布式支持 | ❌ 缺失 | 无分布式能力 |
| 进度跟踪 | ⚠️ 有限 | 仅 step 计数 |

### Core V2 能力

| 能力 | 支持程度 | 说明 |
|------|----------|------|
| 状态机执行 | ✅ 新增 | StateMachineAgent |
| 智能检查点 | ✅ 新增 | SmartCheckpointManager |
| 分层记忆 | ✅ 新增 | HierarchicalMemoryManager |
| 任务编排 | ✅ 新增 | TaskOrchestrator |
| 子 Agent 管理 | ✅ 基础 | SubagentManager (非持久化) |
| 并行执行 | ⚠️ 有限 | asyncio 并发，无分布式 |
| 分布式支持 | ⚠️ 有限 | Redis 存储，无调度 |
| 进度跟踪 | ⚠️ 有限 | AgentMetrics |

### SubagentManager 分析

```python
# 当前实现 (subagent_manager.py)
class SubagentManager:
    # ✅ 支持:
    # - 子 Agent 注册和发现
    # - 任务委派 (同步/异步)
    # - 会话隔离
    # - 超时控制
    
    # ❌ 缺失:
    # - 持久化会话存储
    # - 分布式执行
    # - 进度跟踪 (100+ 任务)
    # - 断点恢复
    # - 任务队列管理
    # - 负载均衡
```

---

## 三、架构选择建议

### 推荐方案: Core V2 + 分布式扩展

**理由:**
1. Core V2 已有状态机和检查点基础
2. 模块化设计更易扩展
3. 分层记忆适合长期任务
4. 需要新增分布式能力

### 架构演进路线

```
当前 Core V2
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│                   Distributed Agent Layer                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              DistributedTaskScheduler               │   │
│  │  - 任务队列 (Redis/RabbitMQ)                         │   │
│  │  - 任务调度                                          │   │
│  │  - 负载均衡                                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              PersistentSubagentManager              │   │
│  │  - 持久化会话存储                                    │   │
│  │  - 进度跟踪 (100+ 任务)                              │   │
│  │  - 断点恢复                                          │   │
│  │  - 分布式执行                                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LongRunningTaskManager                 │   │
│  │  - 天级任务管理                                      │   │
│  │  - 自动检查点                                        │   │
│  │  - 心跳检测                                          │   │
│  │  - 故障恢复                                          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、需要补全的能力

### 4.1 长期任务支持 (场景 1)

#### 缺失能力

| 能力 | 优先级 | 描述 |
|------|--------|------|
| 持久化检查点 | P0 | 任务状态持久化到 Redis/DB |
| 增量检查点 | P0 | 大状态增量保存，避免全量写入 |
| 自动恢复 | P0 | 进程重启后自动恢复执行 |
| 心跳机制 | P1 | 检测任务是否存活 |
| 任务暂停/恢复 | P1 | 手动暂停和恢复任务 |
| 任务优先级 | P2 | 多任务优先级调度 |

#### 实现方案

```python
class LongRunningTaskManager:
    """
    长期任务管理器
    
    支持:
    - 天级任务执行
    - 自动检查点 (每 N 分钟/步)
    - 心跳检测
    - 故障恢复
    """
    
    def __init__(
        self,
        checkpoint_interval_minutes: int = 5,
        heartbeat_interval_seconds: int = 30,
        state_store: StateStore = None,
    ):
        self.checkpoint_interval = checkpoint_interval_minutes
        self.heartbeat_interval = heartbeat_interval_seconds
        self.state_store = state_store or RedisStateStore()
    
    async def execute_long_task(
        self,
        task_id: str,
        agent: Any,
        goal: str,
        resume: bool = True,
    ) -> LongTaskResult:
        """
        执行长期任务
        
        Args:
            task_id: 任务唯一标识
            agent: Agent 实例
            goal: 任务目标
            resume: 是否尝试从检查点恢复
        """
        # 1. 尝试恢复
        if resume:
            checkpoint = await self.load_checkpoint(task_id)
            if checkpoint:
                agent = await self.restore_agent(agent, checkpoint)
        
        # 2. 启动心跳
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(task_id)
        )
        
        # 3. 启动检查点循环
        checkpoint_task = asyncio.create_task(
            self._checkpoint_loop(task_id, agent)
        )
        
        try:
            # 4. 执行任务
            result = await agent.execute(goal)
            
            # 5. 保存最终检查点
            await self.save_checkpoint(task_id, agent, final=True)
            
            return result
            
        except Exception as e:
            # 保存错误检查点
            await self.save_checkpoint(task_id, agent, error=e)
            raise
            
        finally:
            heartbeat_task.cancel()
            checkpoint_task.cancel()
```

### 4.2 大规模子 Agent 编排 (场景 2)

#### 缺失能力

| 能力 | 优先级 | 描述 |
|------|--------|------|
| 批量任务调度 | P0 | 100+ 子 Agent 并行调度 |
| 进度聚合 | P0 | 汇总所有子 Agent 进度 |
| 持久化任务状态 | P0 | 子 Agent 状态持久化 |
| 分布式执行 | P0 | 跨进程/机器执行 |
| 失败重试 | P1 | 单个子 Agent 失败重试 |
| 结果聚合 | P1 | 汇总所有子 Agent 结果 |
| 资源限制 | P2 | 并发数/资源限制 |
| 优先级队列 | P2 | 子任务优先级 |

#### 实现方案

```python
class DistributedSubagentOrchestrator:
    """
    分布式子 Agent 编排器
    
    支持:
    - 100+ 子 Agent 并行执行
    - 进度跟踪和聚合
    - 分布式调度
    - 故障恢复
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        task_queue: TaskQueue = None,
        state_store: StateStore = None,
    ):
        self.max_concurrent = max_concurrent
        self.task_queue = task_queue or RedisTaskQueue()
        self.state_store = state_store or RedisStateStore()
        self.progress_tracker = ProgressTracker()
    
    async def execute_batch(
        self,
        parent_agent: Any,
        tasks: List[SubagentTask],
        wait_all: bool = True,
        fail_fast: bool = False,
    ) -> BatchExecutionResult:
        """
        批量执行子 Agent 任务
        
        Args:
            parent_agent: 主 Agent
            tasks: 子任务列表 (100+)
            wait_all: 是否等待全部完成
            fail_fast: 是否快速失败
        """
        batch_id = str(uuid.uuid4().hex)
        
        # 1. 初始化进度跟踪
        await self.progress_tracker.init_batch(
            batch_id=batch_id,
            total_tasks=len(tasks),
        )
        
        # 2. 提交所有任务到队列
        task_futures = []
        for i, task in enumerate(tasks):
            # 创建持久化任务记录
            persistent_task = await self._create_persistent_task(
                batch_id=batch_id,
                task_index=i,
                task=task,
            )
            
            # 提交到任务队列
            future = await self.task_queue.submit(
                task_id=persistent_task.task_id,
                task_data=persistent_task.to_dict(),
            )
            task_futures.append(future)
        
        # 3. 并行执行 (控制并发)
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def execute_with_limit(task_future):
            async with semaphore:
                return await self._execute_subagent_task(task_future)
        
        results = await asyncio.gather(
            *[execute_with_limit(f) for f in task_futures],
            return_exceptions=not fail_fast,
        )
        
        # 4. 聚合结果
        successful = sum(1 for r in results if r.success)
        failed = len(tasks) - successful
        
        return BatchExecutionResult(
            batch_id=batch_id,
            total=len(tasks),
            successful=successful,
            failed=failed,
            results=results,
        )
    
    async def get_batch_progress(
        self,
        batch_id: str,
    ) -> BatchProgress:
        """
        获取批量任务进度
        
        返回:
        - 总任务数
        - 已完成数
        - 进行中数
        - 失败数
        - 预计剩余时间
        """
        return await self.progress_tracker.get_batch_progress(batch_id)
    
    async def resume_batch(
        self,
        batch_id: str,
    ) -> BatchExecutionResult:
        """
        恢复中断的批量任务
        """
        # 加载所有未完成的任务
        pending_tasks = await self.state_store.list_pending_tasks(batch_id)
        
        # 重新执行
        return await self.execute_batch(
            parent_agent=None,  # 从状态恢复
            tasks=pending_tasks,
            wait_all=True,
        )
```

### 4.3 任务队列和调度

```python
class RedisTaskQueue:
    """
    Redis 任务队列
    
    支持:
    - 任务入队/出队
    - 优先级队列
    - 延迟任务
    - 任务状态追踪
    """
    
    def __init__(self, redis_url: str, queue_name: str = "agent_tasks"):
        self.redis = redis.from_url(redis_url)
        self.queue_name = queue_name
    
    async def submit(
        self,
        task_id: str,
        task_data: Dict[str, Any],
        priority: int = 0,
        delay_seconds: int = 0,
    ) -> str:
        """提交任务"""
        task = {
            "task_id": task_id,
            "data": task_data,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "status": "pending",
        }
        
        # 存储任务
        await self.redis.hset(
            f"task:{task_id}",
            mapping={k: json.dumps(v) if isinstance(v, dict) else str(v) 
                     for k, v in task.items()},
        )
        
        # 加入队列 (带优先级)
        await self.redis.zadd(
            self.queue_name,
            {task_id: -priority},  # 负数实现优先级
        )
        
        return task_id
    
    async def pop(self, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """获取任务"""
        result = await self.redis.bzpopmin(self.queue_name, timeout)
        if result:
            _, task_id, _ = result
            task_data = await self.redis.hgetall(f"task:{task_id.decode()}")
            return {k.decode(): v.decode() for k, v in task_data.items()}
        return None
    
    async def update_status(
        self,
        task_id: str,
        status: str,
        result: Any = None,
    ):
        """更新任务状态"""
        await self.redis.hset(f"task:{task_id}", "status", status)
        if result:
            await self.redis.hset(
                f"task:{task_id}",
                "result",
                json.dumps(result, default=str),
            )
```

### 4.4 进度跟踪

```python
class ProgressTracker:
    """
    进度跟踪器
    
    支持:
    - 100+ 任务进度聚合
    - 实时进度更新
    - 预计剩余时间
    """
    
    def __init__(self, redis_url: str = None):
        self.redis = redis.from_url(redis_url) if redis_url else None
    
    async def init_batch(
        self,
        batch_id: str,
        total_tasks: int,
    ):
        """初始化批量任务进度"""
        await self.redis.hset(
            f"batch:{batch_id}:progress",
            mapping={
                "total": total_tasks,
                "completed": 0,
                "failed": 0,
                "running": 0,
                "started_at": datetime.now().isoformat(),
            },
        )
    
    async def update_task_progress(
        self,
        batch_id: str,
        task_id: str,
        status: str,
        progress: float = None,
    ):
        """更新单个任务进度"""
        # 更新任务状态
        await self.redis.hset(
            f"task:{task_id}",
            "status",
            status,
        )
        
        # 更新批量进度
        if status == "completed":
            await self.redis.hincrby(f"batch:{batch_id}:progress", "completed", 1)
        elif status == "failed":
            await self.redis.hincrby(f"batch:{batch_id}:progress", "failed", 1)
        elif status == "running":
            await self.redis.hincrby(f"batch:{batch_id}:progress", "running", 1)
    
    async def get_batch_progress(
        self,
        batch_id: str,
    ) -> BatchProgress:
        """获取批量进度"""
        data = await self.redis.hgetall(f"batch:{batch_id}:progress")
        
        total = int(data[b"total"])
        completed = int(data[b"completed"])
        failed = int(data[b"failed"])
        running = int(data[b"running"])
        started_at = datetime.fromisoformat(data[b"started_at"].decode())
        
        # 计算预计剩余时间
        elapsed = (datetime.now() - started_at).total_seconds()
        if completed > 0:
            avg_time_per_task = elapsed / completed
            remaining_tasks = total - completed - failed
            estimated_remaining = avg_time_per_task * remaining_tasks
        else:
            estimated_remaining = None
        
        return BatchProgress(
            batch_id=batch_id,
            total=total,
            completed=completed,
            failed=failed,
            running=running,
            pending=total - completed - failed - running,
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=estimated_remaining,
        )
```

---

## 五、完整架构设计

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Gateway                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Orchestrator Service                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    LongRunningTaskManager                            │   │
│  │  - 天级任务管理                                                      │   │
│  │  - 自动检查点 (每 5 分钟)                                            │   │
│  │  - 心跳检测                                                          │   │
│  │  - 故障恢复                                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                 DistributedSubagentOrchestrator                     │   │
│  │  - 100+ 子 Agent 调度                                                │   │
│  │  - 进度聚合                                                          │   │
│  │  - 结果汇总                                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Task Queue (Redis)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │ High Priority │  │ Normal Queue │  │ Low Priority │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Worker Pool (可扩展)                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Worker 1   │  │  Worker 2   │  │  Worker 3   │  │  Worker N   │        │
│  │  (Agent)    │  │  (Agent)    │  │  (Agent)    │  │  (Agent)    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         State Store (Redis)                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ Task States      │  │ Checkpoints      │  │ Progress         │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 六、实现优先级

### P0 - 立即需要 (支持极端场景)

| 模块 | 工作量 | 描述 |
|------|--------|------|
| LongRunningTaskManager | 3 天 | 长期任务管理器 |
| PersistentSubagentManager | 3 天 | 持久化子 Agent 管理器 |
| RedisTaskQueue | 1 天 | Redis 任务队列 |
| ProgressTracker | 1 天 | 进度跟踪器 |
| CheckpointSerializer | 1 天 | 检查点序列化 |

### P1 - 短期需要

| 模块 | 工作量 | 描述 |
|------|--------|------|
| DistributedTaskScheduler | 3 天 | 分布式任务调度 |
| WorkerPool | 2 天 | Worker 进程池 |
| ResultAggregator | 1 天 | 结果聚合器 |

### P2 - 中期需要

| 模块 | 工作量 | 描述 |
|------|--------|------|
| TaskPrioritizer | 1 天 | 任务优先级 |
| ResourceLimiter | 1 天 | 资源限制 |
| MonitoringDashboard | 3 天 | 监控面板 |

---

## 七、使用示例

### 场景 1: 长期任务执行

```python
from derisk.agent.core_v2 import (
    LongRunningTaskManager,
    StateMachineAgent,
    RedisStateStore,
)

# 创建长期任务管理器
task_manager = LongRunningTaskManager(
    checkpoint_interval_minutes=5,
    heartbeat_interval_seconds=30,
    state_store=RedisStateStore("redis://localhost:6379/0"),
)

# 创建 Agent
agent = StateMachineAgent(
    think_func=think,
    act_func=act,
    verify_func=verify,
)

# 执行长期任务 (支持中断恢复)
result = await task_manager.execute_long_task(
    task_id="analysis-task-001",
    agent=agent,
    goal="对 10TB 数据进行深度分析",
    resume=True,  # 自动恢复
)

# 稍后检查进度
progress = await task_manager.get_task_progress("analysis-task-001")
print(f"进度: {progress.completed_steps}/{progress.total_steps}")
print(f"预计剩余: {progress.estimated_remaining}")
```

### 场景 2: 100+ 子 Agent 执行

```python
from derisk.agent.core_v2 import (
    DistributedSubagentOrchestrator,
    SubagentTask,
)

# 创建编排器
orchestrator = DistributedSubagentOrchestrator(
    max_concurrent=10,  # 最多 10 个并行
    task_queue=RedisTaskQueue("redis://localhost:6379/0"),
    state_store=RedisStateStore("redis://localhost:6379/0"),
)

# 创建 100+ 子任务
targets = [f"target-{i}" for i in range(100)]
tasks = [
    SubagentTask(
        task_id=f"analyze-{target}",
        subagent_name="analyzer",
        task=f"分析目标: {target}",
    )
    for target in targets
]

# 执行批量任务
result = await orchestrator.execute_batch(
    parent_agent=main_agent,
    tasks=tasks,
    wait_all=True,
)

# 检查进度
progress = await orchestrator.get_batch_progress(result.batch_id)
print(f"完成: {progress.completed}/{progress.total}")
print(f"失败: {progress.failed}")
print(f"预计剩余: {progress.estimated_remaining_seconds}秒")

# 如果中断，恢复执行
if interrupted:
    result = await orchestrator.resume_batch(result.batch_id)
```

---

## 八、总结

### Core V1 vs Core V2 对比

| 维度 | Core V1 | Core V2 |
|------|---------|---------|
| 基础架构 | while 循环 | 状态机 |
| 检查点 | ❌ 无 | ✅ 有 |
| 子 Agent | ❌ 无 | ⚠️ 基础 |
| 扩展性 | ⚠️ 有限 | ✅ 好 |
| 推荐场景 | 简单任务 | 复杂/长期任务 |

### 最终建议

**选择 Core V2 + 分布式扩展**

1. Core V2 已有状态机和检查点基础
2. 模块化设计易于扩展
3. 需要新增:
   - LongRunningTaskManager
   - DistributedSubagentOrchestrator
   - RedisTaskQueue
   - ProgressTracker

### 预计工作量

| 阶段 | 工作量 | 内容 |
|------|--------|------|
| P0 | 10 天 | 核心分布式能力 |
| P1 | 6 天 | 调度和执行 |
| P2 | 5 天 | 监控和优化 |