"""
Agent Application Configuration - Agent应用配置

正确的架构设计：
1. 配置层：定义主Agent和其绑定的子Agent
2. 运行时：主Agent自主决策何时调用哪个子Agent
3. 基础设施：提供休眠/唤醒、独立对话等能力

示例配置：
    MainAgent (业务分析师)
    ├── 子Agent: data_collector (数据采集)
    ├── 子Agent: analyzer (数据分析)
    └── 子Agent: report_generator (报告生成)

    运行时：
    - 主Agent分析业务目标
    - 决定调用 analyzer 对100个目标进行分析
    - 主Agent进入休眠
    - 100个analyzer子任务完成后唤醒主Agent
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Type, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Part 1: Agent应用配置
# =============================================================================


@dataclass
class SubagentBinding:
    """
    子Agent绑定配置

    定义主Agent可以使用的子Agent
    """

    name: str  # 子Agent名称 (用于调用)
    agent_class: Type  # 子Agent类
    description: str = ""  # 描述 (给LLM看)

    # 执行配置
    max_instances: int = 10  # 最大并行实例数
    default_timeout: int = 3600  # 默认超时(秒)
    max_retries: int = 3  # 最大重试次数

    # 权限控制
    auto_approve: bool = False  # 是否自动批准调用
    require_confirmation: bool = True  # 是否需要用户确认

    # 结果处理
    summarize_results: bool = True  # 是否汇总结果
    max_result_size: int = 10000  # 单个结果最大字符数


@dataclass
class AgentApplication:
    """
    Agent应用配置

    定义一个完整的Agent应用，包含主Agent和其子Agent
    """

    app_id: str  # 应用ID
    name: str  # 应用名称

    # 主Agent
    main_agent_class: Type  # 主Agent类
    main_agent_config: Dict[str, Any] = field(default_factory=dict)

    # 绑定的子Agent
    subagent_bindings: Dict[str, SubagentBinding] = field(default_factory=dict)

    # 可靠性配置
    enable_checkpoint: bool = True
    checkpoint_interval: int = 10
    enable_sleep: bool = True  # 启用休眠机制

    # 存储配置
    storage_backend: str = "memory"  # memory/file/redis
    storage_config: Dict[str, Any] = field(default_factory=dict)

    def bind_subagent(
        self,
        name: str,
        agent_class: Type,
        description: str = "",
        **kwargs,
    ) -> "AgentApplication":
        """绑定子Agent"""
        self.subagent_bindings[name] = SubagentBinding(
            name=name,
            agent_class=agent_class,
            description=description,
            **kwargs,
        )
        return self

    def get_subagent_description(self) -> str:
        """生成给LLM的子Agent描述"""
        if not self.subagent_bindings:
            return "没有可用的子Agent"

        lines = ["可用子Agent:"]
        for name, binding in self.subagent_bindings.items():
            lines.append(f"\n## {name}")
            lines.append(f"{binding.description}")
            lines.append(f"- 最大并行数: {binding.max_instances}")
            lines.append(f"- 超时: {binding.default_timeout}秒")

        return "\n".join(lines)


# =============================================================================
# Part 2: Agent运行时上下文
# =============================================================================


class AgentRuntimeContext:
    """
    Agent运行时上下文

    管理Agent执行过程中的状态和能力
    """

    def __init__(
        self,
        application: AgentApplication,
        storage: Any = None,
    ):
        self.application = application
        self.storage = storage

        # 运行时状态
        self.main_agent: Optional[Any] = None
        self.task_id: Optional[str] = None
        self.parent_task_id: Optional[str] = None

        # 子Agent管理
        self.subagent_instances: Dict[str, List[Any]] = {}
        self.subagent_conversations: Dict[
            str, Any
        ] = {}  # conversation_id -> conversation

        # 休眠管理
        self._is_sleeping = False
        self._sleep_reason: Optional[str] = None
        self._waiting_subtasks: List[str] = []

        # 进度跟踪
        self._total_subtasks = 0
        self._completed_subtasks = 0
        self._failed_subtasks = 0

    async def initialize(self):
        """初始化运行时"""
        # 创建存储
        if self.storage is None:
            from .distributed_execution import (
                StateStorageFactory,
                StorageConfig,
                StorageBackendType,
            )

            backend = StorageBackendType(self.application.storage_backend)
            config = StorageConfig(
                backend_type=backend, **self.application.storage_config
            )
            self.storage = StateStorageFactory.create(config)

        # 创建主Agent
        self.main_agent = self.application.main_agent_class(
            **self.application.main_agent_config
        )

        # 注入运行时能力
        await self._inject_runtime_capabilities()

    async def _inject_runtime_capabilities(self):
        """向主Agent注入运行时能力"""
        # 注入子Agent调用能力
        if hasattr(self.main_agent, "_runtime_context"):
            self.main_agent._runtime_context = self

        # 注入子Agent描述到系统提示
        subagent_desc = self.application.get_subagent_description()
        if hasattr(self.main_agent, "available_subagents"):
            self.main_agent.available_subagents = subagent_desc

        logger.info(
            f"[AgentRuntime] Initialized with {len(self.application.subagent_bindings)} subagents"
        )

    def is_sleeping(self) -> bool:
        """主Agent是否在休眠"""
        return self._is_sleeping

    def get_subagent_progress(self) -> Dict[str, Any]:
        """获取子任务进度"""
        return {
            "total": self._total_subtasks,
            "completed": self._completed_subtasks,
            "failed": self._failed_subtasks,
            "pending": self._total_subtasks
            - self._completed_subtasks
            - self._failed_subtasks,
            "progress_percent": (
                (self._completed_subtasks + self._failed_subtasks)
                / self._total_subtasks
                * 100
                if self._total_subtasks > 0
                else 0
            ),
        }


# =============================================================================
# Part 3: 子Agent调用接口
# =============================================================================


@dataclass
class SubagentCallRequest:
    """子Agent调用请求"""

    subagent_name: str  # 要调用的子Agent名称
    task: str  # 任务内容
    count: int = 1  # 调用次数 (批量时>1)

    # 执行配置
    max_concurrent: Optional[int] = None
    timeout: Optional[int] = None

    # 上下文传递
    shared_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubagentCallResult:
    """子Agent调用结果"""

    call_id: str
    subagent_name: str
    success: bool

    # 批量结果
    conversation_ids: List[str] = field(default_factory=list)
    results: List[Any] = field(default_factory=list)

    # 统计
    total: int = 0
    successful: int = 0
    failed: int = 0

    # 汇总
    summary: Optional[str] = None


class SubagentCaller:
    """
    子Agent调用器

    提供主Agent调用子Agent的能力
    """

    def __init__(
        self,
        runtime_context: AgentRuntimeContext,
    ):
        self.context = runtime_context
        self.storage = runtime_context.storage

    async def call(
        self,
        request: SubagentCallRequest,
    ) -> SubagentCallResult:
        """
        调用子Agent

        这是主Agent可以调用的方法，用于执行子任务
        """
        import uuid

        # 获取子Agent绑定
        binding = self.context.application.subagent_bindings.get(request.subagent_name)
        if not binding:
            return SubagentCallResult(
                call_id="",
                subagent_name=request.subagent_name,
                success=False,
                summary=f"子Agent '{request.subagent_name}' 未找到",
            )

        # 确定并发数
        max_concurrent = request.max_concurrent or binding.max_instances

        # 生成调用ID
        call_id = f"call_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"[SubagentCaller] Calling {request.subagent_name} "
            f"for {request.count} tasks (max_concurrent={max_concurrent})"
        )

        # 创建子任务
        conversation_ids = []
        results = []

        # 控制并发
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_single_task(task_content: str, index: int):
            async with semaphore:
                return await self._run_single_subagent(
                    binding=binding,
                    task=task_content,
                    parent_task_id=self.context.task_id,
                    shared_context=request.shared_context,
                )

        # 并行执行
        tasks = [run_single_task(request.task, i) for i in range(request.count)]

        # 更新进度
        self.context._total_subtasks += request.count

        # 执行并收集结果
        successful = 0
        failed = 0

        for coro in asyncio.as_completed(tasks):
            try:
                conv_id, result = await coro
                conversation_ids.append(conv_id)
                results.append(result)

                if result.get("success"):
                    successful += 1
                    self.context._completed_subtasks += 1
                else:
                    failed += 1
                    self.context._failed_subtasks += 1

            except Exception as e:
                logger.error(f"[SubagentCaller] Task failed: {e}")
                failed += 1
                self.context._failed_subtasks += 1

        # 汇总结果
        summary = None
        if binding.summarize_results:
            summary = self._summarize_results(results, binding.max_result_size)

        return SubagentCallResult(
            call_id=call_id,
            subagent_name=request.subagent_name,
            success=failed == 0,
            conversation_ids=conversation_ids,
            results=results,
            total=request.count,
            successful=successful,
            failed=failed,
            summary=summary,
        )

    async def _run_single_subagent(
        self,
        binding: SubagentBinding,
        task: str,
        parent_task_id: str,
        shared_context: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """运行单个子Agent任务"""
        import uuid
        from .distributed_execution import (
            SubagentConversationStatus,
        )

        # 创建独立对话
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"

        # 创建子Agent实例
        subagent = binding.agent_class()

        # 创建对话记录
        conversation_data = {
            "conversation_id": conversation_id,
            "parent_task_id": parent_task_id,
            "subagent_name": binding.name,
            "status": SubagentConversationStatus.RUNNING.value,
            "task": task,
            "created_at": datetime.now().isoformat(),
            "shared_context": shared_context,
        }

        # 保存对话
        await self.storage.save(
            f"conversation:{conversation_id}",
            conversation_data,
        )

        # 执行子Agent
        result = {}
        try:
            # 调用子Agent的run方法
            if hasattr(subagent, "run"):
                if asyncio.iscoroutinefunction(subagent.run):
                    output = await subagent.run(task, context=shared_context)
                else:
                    output = subagent.run(task, context=shared_context)

                result = {
                    "success": True,
                    "output": str(output) if output else "",
                }
            else:
                result = {
                    "success": False,
                    "error": "子Agent没有run方法",
                }

        except asyncio.TimeoutError:
            result = {
                "success": False,
                "error": f"执行超时 ({binding.default_timeout}秒)",
            }

        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
            }

        # 更新对话状态
        conversation_data["status"] = (
            SubagentConversationStatus.COMPLETED.value
            if result["success"]
            else SubagentConversationStatus.FAILED.value
        )
        conversation_data["result"] = result
        conversation_data["completed_at"] = datetime.now().isoformat()

        await self.storage.save(
            f"conversation:{conversation_id}",
            conversation_data,
        )

        return conversation_id, result

    def _summarize_results(
        self,
        results: List[Dict[str, Any]],
        max_size: int,
    ) -> str:
        """汇总结果"""
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        parts = [
            f"成功: {len(successful)}/{len(results)}",
        ]

        if failed:
            parts.append(f"失败: {len(failed)}")
            errors = [r.get("error", "未知错误") for r in failed[:5]]
            parts.append(f"错误示例: {errors}")

        # 成功结果摘要
        if successful:
            outputs = [r.get("output", "")[:500] for r in successful[:3]]
            parts.append(f"结果示例: {outputs}")

        summary = "\n".join(parts)

        # 截断
        if len(summary) > max_size:
            summary = summary[:max_size] + "..."

        return summary


# =============================================================================
# Part 4: 完整的Agent应用运行器
# =============================================================================


class AgentApplicationRunner:
    """
    Agent应用运行器

    完整的流程：
    1. 加载Agent应用配置
    2. 初始化运行时上下文
    3. 执行主Agent
    4. 主Agent自主调用子Agent
    5. 自动休眠/唤醒
    """

    def __init__(
        self,
        application: AgentApplication,
        storage: Any = None,
    ):
        self.application = application
        self.storage = storage

        self.runtime_context: Optional[AgentRuntimeContext] = None
        self.subagent_caller: Optional[SubagentCaller] = None

    async def initialize(self):
        """初始化运行器"""
        # 创建运行时上下文
        self.runtime_context = AgentRuntimeContext(
            application=self.application,
            storage=self.storage,
        )

        await self.runtime_context.initialize()

        # 创建子Agent调用器
        self.subagent_caller = SubagentCaller(self.runtime_context)

        # 向主Agent注入调用能力
        await self._inject_subagent_caller()

        logger.info(f"[AgentAppRunner] Initialized app: {self.application.name}")

    async def _inject_subagent_caller(self):
        """向主Agent注入子Agent调用能力"""
        agent = self.runtime_context.main_agent

        # 注入调用方法
        agent.call_subagent = self._create_call_method()
        agent.get_subagent_progress = lambda: (
            self.runtime_context.get_subagent_progress()
        )

        # 注入子Agent描述
        if hasattr(agent, "subagent_description"):
            agent.subagent_description = self.application.get_subagent_description()

        logger.info("[AgentAppRunner] Injected subagent caller into main agent")

    def _create_call_method(self) -> Callable:
        """创建子Agent调用方法"""

        async def call_subagent(
            subagent_name: str,
            task: str,
            count: int = 1,
            max_concurrent: Optional[int] = None,
            **kwargs,
        ) -> Dict[str, Any]:
            """
            调用子Agent

            这是注入到主Agent的方法，主Agent可以在运行时调用

            Args:
                subagent_name: 子Agent名称
                task: 任务内容
                count: 调用次数 (批量执行)
                max_concurrent: 最大并发数

            Returns:
                调用结果
            """
            request = SubagentCallRequest(
                subagent_name=subagent_name,
                task=task,
                count=count,
                max_concurrent=max_concurrent,
                **kwargs,
            )

            result = await self.subagent_caller.call(request)

            return {
                "success": result.success,
                "total": result.total,
                "successful": result.successful,
                "failed": result.failed,
                "summary": result.summary,
                "conversation_ids": result.conversation_ids,
            }

        return call_subagent

    async def run(
        self,
        goal: str,
        task_id: Optional[str] = None,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """
        运行Agent应用

        Args:
            goal: 任务目标
            task_id: 任务ID (可选，用于恢复)
            resume: 是否从检查点恢复

        Returns:
            执行结果
        """
        import uuid

        # 生成任务ID
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        self.runtime_context.task_id = task_id

        logger.info(f"[AgentAppRunner] Starting task: {task_id}")

        # 尝试恢复
        if resume:
            checkpoint = await self.storage.load(f"checkpoint:{task_id}")
            if checkpoint:
                logger.info(f"[AgentAppRunner] Resuming from checkpoint")
                # TODO: 恢复状态

        # 执行主Agent
        try:
            # 保存起始检查点
            await self.storage.save(
                f"checkpoint:{task_id}",
                {
                    "status": "running",
                    "goal": goal,
                    "started_at": datetime.now().isoformat(),
                },
            )

            # 运行主Agent
            agent = self.runtime_context.main_agent

            if hasattr(agent, "run"):
                if asyncio.iscoroutinefunction(agent.run):
                    output = await agent.run(goal)
                else:
                    output = agent.run(goal)
            else:
                output = "Agent没有run方法"

            # 保存完成检查点
            await self.storage.save(
                f"checkpoint:{task_id}",
                {
                    "status": "completed",
                    "output": str(output),
                    "completed_at": datetime.now().isoformat(),
                    "subagent_progress": self.runtime_context.get_subagent_progress(),
                },
            )

            return {
                "success": True,
                "task_id": task_id,
                "output": str(output),
                "subagent_progress": self.runtime_context.get_subagent_progress(),
            }

        except Exception as e:
            logger.exception(f"[AgentAppRunner] Task failed: {e}")

            # 保存错误检查点
            await self.storage.save(
                f"checkpoint:{task_id}",
                {
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.now().isoformat(),
                },
            )

            return {
                "success": False,
                "task_id": task_id,
                "error": str(e),
            }

    async def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return await self.storage.load(f"checkpoint:{task_id}")


# =============================================================================
# Part 5: 配置示例
# =============================================================================


def create_agent_application() -> AgentApplication:
    """
    创建Agent应用配置示例
    """
    from derisk.agent.expand.react_master_agent import ReActMasterAgent

    # 定义子Agent (示例)
    class DataCollectorAgent:
        """数据采集子Agent"""

        async def run(self, task: str, context: dict = None):
            # 实际实现...
            return f"数据采集完成: {task}"

    class AnalyzerAgent:
        """数据分析子Agent"""

        async def run(self, task: str, context: dict = None):
            # 实际实现...
            return f"分析完成: {task}"

    class ReportGeneratorAgent:
        """报告生成子Agent"""

        async def run(self, task: str, context: dict = None):
            # 实际实现...
            return f"报告生成完成: {task}"

    # 创建应用配置
    app = AgentApplication(
        app_id="analysis-app",
        name="业务分析应用",
        main_agent_class=ReActMasterAgent,
        main_agent_config={
            "max_retry_count": 100,
        },
        enable_checkpoint=True,
        storage_backend="redis",
        storage_config={
            "redis_url": "redis://localhost:6379/0",
        },
    )

    # 绑定子Agent
    app.bind_subagent(
        name="data_collector",
        agent_class=DataCollectorAgent,
        description="数据采集Agent - 从各种数据源采集数据",
        max_instances=20,
        auto_approve=True,
    )

    app.bind_subagent(
        name="analyzer",
        agent_class=AnalyzerAgent,
        description="数据分析Agent - 对数据进行深度分析",
        max_instances=10,
        auto_approve=True,
    )

    app.bind_subagent(
        name="report_generator",
        agent_class=ReportGeneratorAgent,
        description="报告生成Agent - 生成分析报告",
        max_instances=5,
        auto_approve=True,
    )

    return app


# =============================================================================
# Part 6: 使用示例
# =============================================================================


async def example_usage():
    """使用示例"""

    # 1. 创建应用配置
    app = create_agent_application()

    # 2. 创建运行器
    runner = AgentApplicationRunner(app)
    await runner.initialize()

    # 3. 运行
    result = await runner.run(
        goal="分析系统日志，找出异常模式",
    )

    print(f"任务ID: {result['task_id']}")
    print(f"成功: {result['success']}")
    print(f"子任务进度: {result['subagent_progress']}")


# =============================================================================
# Part 7: 主Agent如何使用 (提示词示例)
# =============================================================================

SUBAGENT_CALLING_PROMPT = """
你可以调用以下子Agent来完成任务：

{subagent_description}

## 调用方式

在需要时，使用以下格式调用子Agent：

```python
# 调用单个任务
result = await call_subagent("analyzer", "分析这个日志文件")

# 批量调用 (例如对100个目标执行分析)
result = await call_subagent(
    "analyzer", 
    "分析目标", 
    count=100,
    max_concurrent=10
)
```

## 批量调用说明

当需要对多个目标执行相同任务时，使用 `count` 参数：
- `count`: 要执行的任务数量
- `max_concurrent`: 最大并行数 (默认为子Agent配置的值)

## 示例场景

假设你有100个服务器日志需要分析：

```python
# 调用分析Agent对100个日志进行分析
result = await call_subagent(
    "analyzer",
    "分析服务器日志，找出错误模式",
    count=100,
    max_concurrent=20  # 最多20个并行
)

# 查看进度
progress = get_subagent_progress()
print(f"进度: {progress['progress_percent']}%")

# 结果汇总
print(result['summary'])
```

## 注意事项

1. 批量调用时，主Agent会等待所有子任务完成
2. 结果会自动汇总
3. 如果部分失败，会包含失败信息
"""
