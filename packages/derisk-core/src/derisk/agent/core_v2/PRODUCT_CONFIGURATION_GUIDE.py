"""
产品层配置指南 - Agent Loop 可靠性架构

本指南说明如何在产品层配置和使用可靠性架构。

支持场景：
1. 长期任务 (2-3天)
2. 大规模子Agent编排 (100+)
3. 中断恢复
"""

# =============================================================================
# 配置方式一：使用默认配置 (推荐新手)
# =============================================================================

from derisk.agent.core_v2 import DistributedTaskExecutor

# 使用默认内存存储
executor = DistributedTaskExecutor()

result = await executor.execute_main_task(
    task_id="task-001",
    agent=my_agent,
    goal="分析数据",
)


# =============================================================================
# 配置方式二：单机生产环境 (文件存储)
# =============================================================================

from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

config = StorageConfig(
    backend_type=StorageBackendType.FILE,
    base_dir="/data/agent_checkpoints",  # 持久化目录
)

executor = DistributedTaskExecutor(storage_config=config)


# =============================================================================
# 配置方式三：分布式生产环境 (Redis存储)
# =============================================================================

from derisk.agent.core_v2 import (
    DistributedTaskExecutor,
    StorageConfig,
    StorageBackendType,
)

config = StorageConfig(
    backend_type=StorageBackendType.REDIS,
    redis_url="redis://localhost:6379/0",
    key_prefix="agent:",
    ttl_seconds=86400 * 7,  # 7天过期
)

executor = DistributedTaskExecutor(storage_config=config)


# =============================================================================
# 场景一：长期任务执行
# =============================================================================


async def run_long_task():
    from derisk.agent.core_v2 import (
        DistributedTaskExecutor,
        StorageConfig,
        StorageBackendType,
    )
    from derisk.agent.expand.react_master_agent import ReActMasterAgent

    # 1. 配置存储
    config = StorageConfig(
        backend_type=StorageBackendType.FILE,
        base_dir="/data/agent_checkpoints",
    )

    # 2. 创建执行器
    executor = DistributedTaskExecutor(storage_config=config)

    # 3. 创建Agent
    agent = ReActMasterAgent()

    # 4. 执行任务
    result = await executor.execute_main_task(
        task_id="long-analysis-001",
        agent=agent,
        goal="对10TB数据进行深度分析",
        resume=True,  # 自动从检查点恢复
    )

    return result


# =============================================================================
# 场景二：100+ 子Agent并行执行
# =============================================================================


async def run_batch_subagents():
    from derisk.agent.core_v2 import (
        DistributedTaskExecutor,
        StorageConfig,
        StorageBackendType,
    )

    # 1. 配置Redis存储 (分布式)
    config = StorageConfig(
        backend_type=StorageBackendType.REDIS,
        redis_url="redis://localhost:6379/0",
    )

    # 2. 创建执行器
    executor = DistributedTaskExecutor(storage_config=config)

    # 3. 创建100个子任务
    targets = [f"target-{i}" for i in range(100)]
    tasks = [f"分析目标: {target}" for target in targets]

    # 4. 委派给子Agent
    conversation_ids = await executor.delegate_to_subagents(
        parent_task_id="batch-001",
        subagent_name="analyzer",
        tasks=tasks,
        max_concurrent=10,  # 最多10个并行
    )

    print(f"创建了 {len(conversation_ids)} 个独立对话")
    print("主Agent进入休眠...")

    # 5. 等待子Agent完成
    results = await executor.wait_for_subagents(
        parent_task_id="batch-001",
        timeout_seconds=86400,  # 最多等1天
    )

    print(f"唤醒原因: {results['wakeup_reason']}")
    print(f"完成: {len(results['subagent_results'])}")

    return results


# =============================================================================
# 与现有 ReActMasterAgent 集成
# =============================================================================


async def integrate_with_react_master():
    from derisk.agent.expand.react_master_agent import ReActMasterAgent
    from derisk.agent.core_v2 import (
        DistributedTaskExecutor,
        StorageConfig,
        StorageBackendType,
    )

    # 方式1: 使用DistributedTaskExecutor包装
    config = StorageConfig(
        backend_type=StorageBackendType.REDIS,
        redis_url="redis://localhost:6379/0",
    )

    executor = DistributedTaskExecutor(storage_config=config)
    agent = ReActMasterAgent()

    result = await executor.execute_main_task(
        task_id="task-001",
        agent=agent,
        goal="分析系统日志",
        resume=True,
    )

    # 方式2: 使用可靠性适配器
    from derisk.agent.core_v2 import make_reliable

    agent = ReActMasterAgent()
    reliable = make_reliable(agent)

    result = await reliable.run("分析系统日志")


# =============================================================================
# 与现有 ReActReasoningAgent (Core V2) 集成
# =============================================================================


async def integrate_with_react_reasoning():
    from derisk.agent.core_v2 import (
        ReActReasoningAgent,
        AgentInfo,
        LLMFactory,
        LLMConfig,
        DistributedTaskExecutor,
        StorageConfig,
        StorageBackendType,
    )

    # 创建Agent
    info = AgentInfo(name="analyst", max_steps=50)
    llm_config = LLMConfig(model="gpt-4", api_key="...", api_base="...")
    llm_adapter = LLMFactory.create(llm_config)

    agent = ReActReasoningAgent(
        info=info,
        llm_adapter=llm_adapter,
    )

    # 使用DistributedTaskExecutor
    config = StorageConfig(
        backend_type=StorageBackendType.REDIS,
        redis_url="redis://localhost:6379/0",
    )

    executor = DistributedTaskExecutor(storage_config=config)

    result = await executor.execute_main_task(
        task_id="analysis-001",
        agent=agent,
        goal="分析代码库",
    )


# =============================================================================
# 产品层服务封装示例
# =============================================================================


class AgentExecutionService:
    """
    产品层Agent执行服务

    可集成到FastAPI/Flask等Web框架中
    """

    def __init__(
        self,
        storage_backend: str = "redis",
        redis_url: str = "redis://localhost:6379/0",
        checkpoint_dir: str = "/data/agent_checkpoints",
    ):
        from derisk.agent.core_v2 import (
            DistributedTaskExecutor,
            StorageConfig,
            StorageBackendType,
        )

        if storage_backend == "redis":
            config = StorageConfig(
                backend_type=StorageBackendType.REDIS,
                redis_url=redis_url,
            )
        elif storage_backend == "file":
            config = StorageConfig(
                backend_type=StorageBackendType.FILE,
                base_dir=checkpoint_dir,
            )
        else:
            config = StorageConfig(
                backend_type=StorageBackendType.MEMORY,
            )

        self.executor = DistributedTaskExecutor(storage_config=config)
        self.storage = self.executor.storage

    async def execute_task(
        self,
        task_id: str,
        agent: Any,
        goal: str,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """执行任务"""
        result = await self.executor.execute_main_task(
            task_id=task_id,
            agent=agent,
            goal=goal,
            resume=resume,
        )
        return result

    async def delegate_batch(
        self,
        parent_task_id: str,
        subagent_name: str,
        tasks: List[str],
        max_concurrent: int = 10,
    ) -> List[str]:
        """批量委派子任务"""
        return await self.executor.delegate_to_subagents(
            parent_task_id=parent_task_id,
            subagent_name=subagent_name,
            tasks=tasks,
            max_concurrent=max_concurrent,
        )

    async def wait_batch(
        self,
        parent_task_id: str,
        timeout_seconds: int = 86400,
    ) -> Dict[str, Any]:
        """等待批量任务完成"""
        return await self.executor.wait_for_subagents(
            parent_task_id=parent_task_id,
            timeout_seconds=timeout_seconds,
        )

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return await self.storage.load(f"checkpoint:{task_id}")

    async def get_conversation_progress(
        self,
        parent_task_id: str,
    ) -> Dict[str, Any]:
        """获取子任务进度"""
        return await self.executor.conversation_manager.get_conversation_progress(
            parent_task_id
        )


# =============================================================================
# FastAPI 集成示例
# =============================================================================

"""
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI()
service = AgentExecutionService(storage_backend="redis")

class TaskRequest(BaseModel):
    task_id: str
    goal: str
    agent_type: str = "react_master"

class BatchRequest(BaseModel):
    parent_task_id: str
    subagent_name: str
    tasks: List[str]
    max_concurrent: int = 10

@app.post("/api/tasks")
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    # 创建任务
    agent = create_agent(request.agent_type)
    
    # 后台执行
    background_tasks.add_task(
        service.execute_task,
        request.task_id,
        agent,
        request.goal,
    )
    
    return {"task_id": request.task_id, "status": "started"}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    status = await service.get_task_status(task_id)
    return status or {"status": "not_found"}

@app.post("/api/batch")
async def create_batch(request: BatchRequest):
    conversation_ids = await service.delegate_batch(
        request.parent_task_id,
        request.subagent_name,
        request.tasks,
        request.max_concurrent,
    )
    return {
        "parent_task_id": request.parent_task_id,
        "conversation_ids": conversation_ids,
        "total": len(conversation_ids),
    }

@app.get("/api/batch/{parent_task_id}/progress")
async def get_batch_progress(parent_task_id: str):
    progress = await service.get_conversation_progress(parent_task_id)
    return progress
"""


# =============================================================================
# 环境变量配置
# =============================================================================

"""
# .env 文件配置

# 存储后端类型
AGENT_STORAGE_BACKEND=redis

# Redis配置
AGENT_REDIS_URL=redis://localhost:6379/0
AGENT_REDIS_KEY_PREFIX=agent:
AGENT_REDIS_TTL=604800  # 7天

# 文件存储配置
AGENT_CHECKPOINT_DIR=/data/agent_checkpoints

# 检查点配置
AGENT_CHECKPOINT_INTERVAL=10
AGENT_MAX_CHECKPOINTS=20

# 分布式配置
AGENT_MAX_CONCURRENT=10
AGENT_MAX_SLEEP_SECONDS=259200  # 3天
"""

import os


def create_service_from_env() -> AgentExecutionService:
    """从环境变量创建服务"""
    backend = os.getenv("AGENT_STORAGE_BACKEND", "memory")
    redis_url = os.getenv("AGENT_REDIS_URL", "redis://localhost:6379/0")
    checkpoint_dir = os.getenv("AGENT_CHECKPOINT_DIR", ".agent_checkpoints")

    return AgentExecutionService(
        storage_backend=backend,
        redis_url=redis_url,
        checkpoint_dir=checkpoint_dir,
    )
