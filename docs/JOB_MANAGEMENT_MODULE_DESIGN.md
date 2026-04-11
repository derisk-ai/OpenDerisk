# 任务作业管理模块设计方案

## Context

系统需要一个任务作业管理模块，用于大规模管理 Agent 任务、周期性长期任务、并发调度等。经探索发现，现有 `derisk-serve/cron` 模块已具备核心能力，可直接复用并扩展。

## 现有 Cron 模块能力分析

### 已具备的功能 ✅

| 功能 | 实现位置 | 说明 |
|------|---------|------|
| Cron 表达式调度 | `cron/service/service.py` | 支持 5/6 字段 cron 表达式 |
| 持久化任务定义 | `cron/models/models.py` | `CronJobEntity` 数据库表 |
| Agent 任务执行 | `payload_kind=AGENT_TURN` | 调用指定 Agent |
| 会话模式 | `SessionMode` | ISOLATED/SHARED |
| 状态追踪 | `CronJobState` | 运行时间、状态、错误等 |
| REST API | `cron/api/endpoints.py` | CRUD + 启用/禁用/手动触发 |
| 分布式锁 | `cron/service/lock.py` | 防止并发重复执行 |

### 缺少的功能 ❌

| 功能 | 说明 |
|------|------|
| 批量任务管理 | 无批量提交、分发能力 |
| 任务依赖编排 | 无 DAG 依赖管理 |
| 并发控制 | 无最大并发实例限制 |
| 优先级调度 | 无优先级概念 |
| 自动重试 | 虽有 `consecutive_errors`，无重试逻辑 |
| 多负载类型 | 仅支持 AGENT_TURN |

## 设计方案：复用 + 扩展

### 方案选择

**推荐：复用现有 Cron 模块，扩展 Job 管理层**

理由：
1. 避免重复实现 Cron 调度核心逻辑
2. 持久化机制已完备，无需新建表结构
3. Agent 执行流程已打通
4. 扩展点清晰：批量、依赖、并发控制可在上层包装

### 扩展架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Job Management Layer (新增)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  JobBatcher  │  │ JobOrchestrator │  │ JobDependencyManager │   │
│  │  (批量分发)   │  │  (任务编排)     │  │  (依赖管理)           │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────────────┘   │
│         │                 │                 │                    │
│         └─────────────────┼─────────────────┘                    │
│                           │                                      │
│              ┌────────────▼────────────┐                         │
│              │  JobCoordinator (新增)   │                         │
│              │  - Agent级并发池控制      │                         │
│              │  - 优先级排队             │                         │
│              │  - 重试策略               │                         │
│              └────────────┬────────────┘                         │
│                           │                                      │
└───────────────────────────┼─────────────────────────────────────┘
                            │
              ┌─────────────▼─────────────┐
              │   Existing Cron Module    │
              │   (复用现有实现)            │
              │                           │
              │  - CronScheduler          │
              │  - CronJobEntity (持久化)  │
              │  - CronTrigger            │
              │  - AgentTurn 执行          │
              └───────────────────────────┘
```

## 设计决策（已确认）

| 决策点 | 选择 | 说明 |
|--------|------|------|
| **并发控制范围** | Agent 级并发池 | 每个 Agent 有独立并发池，可在 Agent 定义中配置 `max_concurrent` |
| **执行结果存储** | 需要持久化 | 新增 `job_execution_result` 表存储输出数据 |
| **依赖编排复杂度** | 渐进实现 | Phase 1 先实现简单 `depends_on` 线性依赖，后续扩展完整 DAG |

## 实现计划

### Phase 1: 扩展数据模型

**修改文件**: `packages/derisk-serve/src/derisk_serve/cron/models/models.py`

扩展 `CronJobEntity` 添加新字段：

```python
class CronJobEntity(Model):
    # ... 现有字段 ...

    # 新增：任务编排字段
    priority = Column(Integer, default=5)          # 优先级 1-20
    max_concurrent = Column(Integer, default=1)    # 该 Agent 最大并发实例
    depends_on = Column(JSON, nullable=True)       # 依赖的 job_id 列表 ["job_id1", "job_id2"]
    retry_policy = Column(JSON, nullable=True)     # 重试策略 {"max_retries": 3, "delay_seconds": 60}

    # 新增：批量任务字段
    batch_id = Column(String(64), nullable=True, index=True)   # 所属批次 ID
    batch_index = Column(Integer, nullable=True)   # 批次内序号
```

**新增文件**: `packages/derisk-serve/src/derisk_serve/cron/models/result_entity.py`

执行结果持久化表：

```python
class JobExecutionResultEntity(Model):
    __tablename__ = "derisk_serve_job_execution_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)  # 关联 CronJobEntity.id

    # 执行追踪
    execution_id = Column(String(64), nullable=False)        # 本次执行唯一 ID
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # 结果数据
    status = Column(String(16), nullable=False)  # success, error, timeout, cancelled
    output_data = Column(JSON, nullable=True)     # Agent 执行输出
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Agent 信息
    agent_name = Column(String(128), nullable=True)
    conversation_id = Column(String(64), nullable=True)

    gmt_created = Column(DateTime, default=datetime.now)
```

### Phase 2: 实现 JobCoordinator

**新增文件**: `packages/derisk-serve/src/derisk_serve/job/coordinator.py`

核心职责：
- 包装现有 `CronScheduler`
- **Agent 级并发池控制**（每个 Agent 独立 Semaphore）
- 优先级排队
- 重试策略

```python
class JobCoordinator:
    def __init__(self, cron_scheduler: CronScheduler, default_max_workers: int = 10):
        self._scheduler = cron_scheduler
        self._default_max_workers = default_max_workers
        self._agent_semaphores: Dict[str, asyncio.Semaphore] = {}  # agent_name -> Semaphore
        self._agent_configs: Dict[str, int] = {}  # agent_name -> max_concurrent
        self._priority_queue = []  # heapq
        self._pending_deps: Dict[str, set] = {}  # job_id -> 未满足的依赖
        self._lock = asyncio.Lock()

    def _get_agent_semaphore(self, agent_name: str, max_concurrent: int) -> asyncio.Semaphore:
        """获取或创建 Agent 级并发池"""
        if agent_name not in self._agent_semaphores or self._agent_configs[agent_name] != max_concurrent:
            self._agent_semaphores[agent_name] = asyncio.Semaphore(max_concurrent)
            self._agent_configs[agent_name] = max_concurrent
        return self._agent_semaphores[agent_name]

    async def submit_batch(self, requests: List[CronJobCreate]) -> List[CronJob]:
        """批量提交任务，生成 batch_id"""

    async def submit_with_deps(self, request: CronJobCreate, depends_on: List[str]) -> CronJob:
        """带依赖提交"""

    async def _execute_with_retry(self, job_id: str, semaphore: asyncio.Semaphore) -> bool:
        """带并发控制和重试执行"""
        async with semaphore:
            # 执行并保存结果到 JobExecutionResultEntity
```

### Phase 3: 实现 JobBatcher

**新增文件**: `packages/derisk-serve/src/derisk_serve/job/batcher.py`

核心职责：
- 模板化批量任务创建
- 输入参数变量替换
- 批次追踪

```python
class JobBatcher:
    async def create_from_template(
        self,
        template: JobTemplate,
        inputs: List[Dict[str, Any]]
    ) -> BatchResult:
        """从模板 + 输入列表批量创建"""

    async def get_batch_status(self, batch_id: str) -> BatchStatus:
        """获取批次整体状态"""
```

### Phase 4: 实现 JobDependencyManager

**新增文件**: `packages/derisk-serve/src/derisk_serve/job/dependency.py`

核心职责：
- DAG 依赖检查
- 依赖完成通知
- 阻塞任务调度

```python
class JobDependencyManager:
    async def check_dependencies(self, job_id: str) -> bool:
        """检查依赖是否全部满足"""

    async def notify_completion(self, job_id: str):
        """通知任务完成，解锁下游"""

    async def get_blocked_jobs(self) -> List[str]:
        """获取被阻塞的任务列表"""
```

### Phase 5: 扩展 API 端点

**新增文件**: `packages/derisk-serve/src/derisk_serve/job/api/endpoints.py`

新增端点：

| 端点 | 方法 | 描述 |
|------|------|------|
| `/jobs/batch` | POST | 批量创建任务 |
| `/jobs/batch/{batch_id}` | GET | 获取批次状态 |
| `/jobs/dag` | POST | 提交 DAG 工作流 |
| `/jobs/{job_id}/dependencies` | GET | 获取依赖状态 |
| `/jobs/priority/{job_id}` | PUT | 更新优先级 |

### Phase 6: 扩展 CronService 执行逻辑

**修改文件**: `packages/derisk-serve/src/derisk_serve/cron/service/service.py`

修改 `_execute_job_safe` 方法，集成：
- 并发池控制
- 重试策略执行
- 依赖完成通知

```python
async def _execute_job_safe(self, job_id: str) -> None:
    # 1. 检查并发限制
    if await self._concurrent_limit_reached(job_id):
        self._reschedule_job(job_id)
        return

    # 2. 检查依赖
    if not await self._dependencies_met(job_id):
        return  # 保持阻塞状态

    # 3. 执行（带重试）
    success = await self._execute_with_retry(job_id)

    # 4. 通知依赖管理器
    if success:
        await self._dependency_manager.notify_completion(job_id)
```

## 关键文件清单

| 操作 | 文件路径 |
|------|---------|
| 扩展 | `packages/derisk-serve/src/derisk_serve/cron/models/models.py` |
| 新增 | `packages/derisk-serve/src/derisk_serve/cron/models/result_entity.py` |
| 扩展 | `packages/derisk-serve/src/derisk_serve/cron/service/service.py` |
| 新增 | `packages/derisk-serve/src/derisk_serve/job/__init__.py` |
| 新增 | `packages/derisk-serve/src/derisk_serve/job/coordinator.py` |
| 新增 | `packages/derisk-serve/src/derisk_serve/job/batcher.py` |
| 新增 | `packages/derisk-serve/src/derisk_serve/job/dependency.py` |
| 新增 | `packages/derisk-serve/src/derisk_serve/job/api/endpoints.py` |
| 扩展 | `packages/derisk-core/src/derisk/cron/types.py` |

## 可复用的现有组件

| 组件 | 路径 | 复用方式 |
|------|------|---------|
| `CronScheduler` | `cron/service/service.py` | 直接使用，包装执行逻辑 |
| `CronJobEntity` | `cron/models/models.py` | 扩展字段 |
| `CronTrigger` | APScheduler | 直接使用 |
| `CronJobCreate` | `cron/types.py` | 扩展字段 |
| `ServeDao` | `cron/service/dao.py` | 直接使用 |

## 验证计划

### 1. 单元测试
- 测试 `JobCoordinator.submit_batch` 批量创建
- 测试 `JobDependencyManager` DAG 检查
- 测试并发限制生效

### 2. 集成测试
- 提交 100 个批量任务，验证并发控制
- 提交 DAG 工作流 (A→B→C)，验证依赖顺序执行
- 创建周期任务，验证持久化和恢复

### 3. 手动验证

```bash
# 启动服务
uv run python derisk_server.py

# 创建批量任务
curl -X POST http://localhost:8000/api/jobs/batch \
  -H "Content-Type: application/json" \
  -d '{"template": {"agent_name": "data_analyzer"}, "inputs": [{"data": "file1"}, {"data": "file2"}]}'

# 创建周期任务 (复用现有 API)
curl -X POST http://localhost:8000/api/cron/jobs \
  -d '{"name": "daily_backup", "schedule_kind": "cron", "schedule_expr": "0 2 * * *", ...}'
```

## 使用示例

### 示例 1: 批量提交任务

```python
from derisk_serve.job.coordinator import JobCoordinator

coordinator = JobCoordinator()

# 批量提交 100 个文件处理任务
result = await coordinator.submit_batch([
    CronJobCreate(
        name=f"处理文件 {i}",
        agent_name="file_processor",
        payload={"message": f"处理 {filename}"},
    )
    for i, filename in enumerate(file_list)
])

print(f"批次 ID: {result.batch_id}")
print(f"任务数量: {len(result.jobs)}")
```

### 示例 2: 带依赖的任务链

```python
# 创建 ETL 管道: 提取 → 转换 → 加载
extract_job = await coordinator.submit_with_deps(
    CronJobCreate(name="数据提取", agent_name="extractor"),
    depends_on=[]
)

transform_job = await coordinator.submit_with_deps(
    CronJobCreate(name="数据转换", agent_name="transformer"),
    depends_on=[extract_job.id]
)

load_job = await coordinator.submit_with_deps(
    CronJobCreate(name="数据加载", agent_name="loader"),
    depends_on=[transform_job.id]
)
```

### 示例 3: 周期性长期任务（复用现有 Cron）

```python
# 创建每日数据备份任务
job = await cron_scheduler.add_job(CronJobCreate(
    name="daily_backup",
    schedule_kind="cron",
    schedule_expr="0 2 * * *",  # 每天凌晨 2 点
    payload={"agent_name": "backup_agent", "message": "执行全量备份"},
    max_concurrent=1,  # 同时间只允许一个实例
    retry_policy={"max_retries": 3, "delay_seconds": 60},
))
```

### 示例 4: Agent 级并发控制

```python
# Agent A: 最大 5 并发
agent_a_jobs = [
    CronJobCreate(name=f"AgentA-{i}", agent_name="agent_a", max_concurrent=5)
    for i in range(20)
]

# Agent B: 最大 10 并发
agent_b_jobs = [
    CronJobCreate(name=f"AgentB-{i}", agent_name="agent_b", max_concurrent=10)
    for i in range(20)
]

# 同时提交，各自使用独立并发池
await coordinator.submit_batch(agent_a_jobs + agent_b_jobs)
```