"""
Agent Reliability Integration Guide - Agent 可靠性层集成指南

本文档说明如何将新的可靠性层 (StateMachineAgent, SmartCheckpointManager 等)
集成到现有 Core V1 和 Core V2 Agent 架构中。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Product Layer (产品层)                               │
│  app_chat() / conversation endpoints                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Reliability Layer (可靠性层 - 新增)                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │StateMachineAgent│  │SmartCheckpoint  │  │HierarchicalMemory│              │
│  │  (状态机执行)   │  │   Manager       │  │   Manager       │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        AgentMetrics                                 │   │
│  │                    (健康监控与诊断)                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Agent Layer (Agent 层)                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐          │
│  │      Core V1 Agents         │  │      Core V2 Agents         │          │
│  │  - ReActMasterAgent         │  │  - ReActReasoningAgent      │          │
│  │  - ConversableAgent         │  │  - BaseBuiltinAgent        │          │
│  │  - PDC-AAgent              │  │  - SimpleAgent             │          │
│  └─────────────────────────────┘  └─────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 集成模式

### 模式 1: 包装器模式 (推荐)

将现有 Agent 包装在 StateMachineAgent 中，保留原有接口不变。

```python
from derisk.agent.core_v2 import (
    StateMachineAgent,
    SmartCheckpointManager,
    HierarchicalMemoryManager,
    AgentMetrics,
    CheckpointStrategy,
)


# 包装 Core V1 Agent
class ReliableReActMasterAgent:
    def __init__(
        self, original_agent: ReActMasterAgent, config: ReliabilityConfig = None
    ):
        self.agent = original_agent
        self.config = config or ReliabilityConfig()

        # 初始化可靠性组件
        self.checkpoint_manager = SmartCheckpointManager(
            strategy=self.config.checkpoint_strategy,
            checkpoint_store=self.config.state_store,
        )
        self.memory_manager = HierarchicalMemoryManager(
            working_memory_tokens=self.config.working_memory_tokens,
        )
        self.metrics = AgentMetrics()

        # 创建状态机执行器
        self.state_machine = StateMachineAgent(
            think_func=self._wrap_think,
            act_func=self._wrap_act,
            verify_func=self._wrap_verify,
            checkpoint_manager=self.checkpoint_manager,
            max_steps=original_agent.max_retry_count,
        )

    async def run(self, message: str, **kwargs):
        # 使用状态机执行
        result = await self.state_machine.execute(message)

        # 记录指标
        self.metrics.record_step(
            step_index=result.total_steps,
            state=result.final_state.name,
            duration_ms=result.total_time_ms,
            success=result.success,
        )

        return result
```

### 模式 2: Mixin 模式

通过 Mixin 类为现有 Agent 添加可靠性能力。

```python
class ReliabilityMixin:
    def init_reliability(self, config: ReliabilityConfig = None):
        self.config = config or ReliabilityConfig()
        self._checkpoint_manager = SmartCheckpointManager(
            strategy=self.config.checkpoint_strategy,
        )
        self._memory_manager = HierarchicalMemoryManager()
        self._metrics = AgentMetrics()
        self._checkpoint_id = None

    async def save_checkpoint(self):
        self._checkpoint_id = await self._checkpoint_manager.create_checkpoint(
            execution_id=self._get_execution_id(),
            checkpoint_type=CheckpointType.AUTOMATIC,
            state=self._get_current_state(),
            step_index=self._get_current_step(),
        )
        return self._checkpoint_id

    async def restore_checkpoint(self, checkpoint_id: str):
        restored = await self._checkpoint_manager.restore_checkpoint(checkpoint_id)
        if restored:
            self._restore_state(restored["state"])
            return True
        return False


# 使用 Mixin
class ReliableReActMasterAgent(ReActMasterAgent, ReliabilityMixin):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.init_reliability(kwargs.get("reliability_config"))
```

### 模式 3: 组合模式

在对话级别集成，不修改 Agent 本身。

```python
class ReliableConversationManager:
    def __init__(self, agent, config: ReliabilityConfig = None):
        self.agent = agent
        self.config = config or ReliabilityConfig()
        self.checkpoint_manager = SmartCheckpointManager(
            strategy=CheckpointStrategy.ADAPTIVE,
        )
        self.metrics = AgentMetrics()

    async def chat(self, message: str, checkpoint_id: str = None):
        # 恢复检查点
        if checkpoint_id:
            restored = await self.checkpoint_manager.restore_checkpoint(checkpoint_id)
            if restored:
                self._restore_conversation_state(restored)

        # 执行对话
        try:
            response = await self.agent.run(message)

            # 保存检查点
            await self.save_checkpoint()

            return response

        except RecoverableError as e:
            # 可恢复错误，保存检查点
            await self.save_checkpoint()
            raise
```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .state_machine import StateMachineAgent, AgentState, StateMachineResult
    from .smart_checkpoint import SmartCheckpointManager, StateStore, CheckpointStrategy
    from .hierarchical_memory import HierarchicalMemoryManager
    from .agent_metrics import AgentMetrics

logger = logging.getLogger(__name__)


@dataclass
class ReliabilityConfig:
    """可靠性配置"""

    checkpoint_strategy: "CheckpointStrategy" = None
    state_store: "StateStore" = None
    working_memory_tokens: int = 8000
    episodic_memory_tokens: int = 32000
    semantic_memory_tokens: int = 128000
    checkpoint_interval: int = 10
    max_checkpoints: int = 20
    enable_metrics: bool = True

    def __post_init__(self):
        if self.checkpoint_strategy is None:
            from .smart_checkpoint import CheckpointStrategy

            self.checkpoint_strategy = CheckpointStrategy.ADAPTIVE


class ReliabilityAdapter:
    """
    可靠性适配器 - 为现有 Agent 添加可靠性能力

    支持两种 Agent 类型:
    1. Core V1 Agent (ReActMasterAgent, ConversableAgent)
    2. Core V2 Agent (ReActReasoningAgent, BaseBuiltinAgent)

    使用示例:
        # 包装 Core V1 Agent
        agent = ReActMasterAgent()
        reliable_agent = ReliabilityAdapter.wrap_v1_agent(agent)
        result = await reliable_agent.run("分析日志")

        # 包装 Core V2 Agent
        agent = ReActReasoningAgent(info, llm_adapter)
        reliable_agent = ReliabilityAdapter.wrap_v2_agent(agent)
        result = await reliable_agent.run("分析日志")
    """

    def __init__(
        self,
        agent: Any,
        config: Optional[ReliabilityConfig] = None,
    ):
        self.agent = agent
        self.config = config or ReliabilityConfig()

        self._checkpoint_manager: Optional["SmartCheckpointManager"] = None
        self._memory_manager: Optional["HierarchicalMemoryManager"] = None
        self._metrics: Optional["AgentMetrics"] = None
        self._execution_id: Optional[str] = None
        self._current_step: int = 0

        self._initialize_components()

    def _initialize_components(self):
        from .smart_checkpoint import SmartCheckpointManager
        from .hierarchical_memory import HierarchicalMemoryManager
        from .agent_metrics import AgentMetrics

        self._checkpoint_manager = SmartCheckpointManager(
            strategy=self.config.checkpoint_strategy,
            checkpoint_store=self.config.state_store,
            checkpoint_interval=self.config.checkpoint_interval,
            max_checkpoints=self.config.max_checkpoints,
        )

        self._memory_manager = HierarchicalMemoryManager(
            working_memory_tokens=self.config.working_memory_tokens,
            episodic_memory_tokens=self.config.episodic_memory_tokens,
            semantic_memory_tokens=self.config.semantic_memory_tokens,
        )

        if self.config.enable_metrics:
            self._metrics = AgentMetrics()

    @classmethod
    def wrap_v1_agent(
        cls,
        agent: Any,
        config: Optional[ReliabilityConfig] = None,
    ) -> "ReliabilityAdapter":
        """
        包装 Core V1 Agent (ReActMasterAgent, ConversableAgent)

        Core V1 Agent 特征:
        - 继承自 ConversableAgent
        - 使用 generate_reply() 方法
        - 有 memory.gpts_memory 属性
        """
        return cls(agent, config)

    @classmethod
    def wrap_v2_agent(
        cls,
        agent: Any,
        config: Optional[ReliabilityConfig] = None,
    ) -> "ReliabilityAdapter":
        """
        包装 Core V2 Agent (ReActReasoningAgent, BaseBuiltinAgent)

        Core V2 Agent 特征:
        - 继承自 BaseBuiltinAgent 或 SimpleAgent
        - 使用 run() 方法
        - 有 _messages 和 llm_client 属性
        """
        return cls(agent, config)

    async def run(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        执行 Agent 任务，带可靠性保障

        Returns:
            {
                "success": bool,
                "response": str,
                "checkpoint_id": str,
                "metrics": dict,
            }
        """
        import uuid

        self._execution_id = kwargs.get("execution_id") or str(uuid.uuid4().hex)
        self._current_step = 0

        checkpoint_id = None

        try:
            # 检查是否有检查点需要恢复
            resume_checkpoint = kwargs.get("resume_checkpoint")
            if resume_checkpoint:
                await self._restore_checkpoint(resume_checkpoint)

            # 执行 Agent
            response = await self._execute_agent(message, **kwargs)

            # 创建完成检查点
            from .smart_checkpoint import CheckpointType

            checkpoint = await self._checkpoint_manager.create_checkpoint(
                execution_id=self._execution_id,
                checkpoint_type=CheckpointType.TASK_END,
                state=self._get_current_state(),
                step_index=self._current_step,
                message="任务完成",
            )
            checkpoint_id = checkpoint.checkpoint_id

            # 记录指标
            if self._metrics:
                self._metrics.record_step(
                    step_index=self._current_step,
                    state="COMPLETED",
                    duration_ms=0,
                    success=True,
                )

            return {
                "success": True,
                "response": response,
                "checkpoint_id": checkpoint_id,
                "metrics": self._metrics.get_summary() if self._metrics else None,
            }

        except Exception as e:
            logger.exception(f"[ReliabilityAdapter] 执行失败: {e}")

            # 创建错误检查点
            from .smart_checkpoint import CheckpointType

            checkpoint = await self._checkpoint_manager.create_checkpoint(
                execution_id=self._execution_id,
                checkpoint_type=CheckpointType.ERROR,
                state={"error": str(e), "step": self._current_step},
                step_index=self._current_step,
                message=f"错误: {str(e)[:200]}",
            )
            checkpoint_id = checkpoint.checkpoint_id

            return {
                "success": False,
                "response": None,
                "checkpoint_id": checkpoint_id,
                "error": str(e),
                "metrics": self._metrics.get_summary() if self._metrics else None,
            }

    async def _execute_agent(self, message: str, **kwargs) -> Any:
        """执行 Agent"""
        # Core V1 Agent
        if hasattr(self.agent, "generate_reply"):
            from derisk.agent import AgentMessage

            agent_message = AgentMessage(content=message)
            reply = await self.agent.generate_reply(
                received_message=agent_message, sender=None, **kwargs
            )
            return reply.content if hasattr(reply, "content") else str(reply)

        # Core V2 Agent
        elif hasattr(self.agent, "run"):
            result = []
            async for chunk in self.agent.run(message):
                result.append(chunk)
                self._current_step += 1
            return "".join(result)

        else:
            raise ValueError(f"Unknown agent type: {type(self.agent)}")

    def _get_current_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        state = {
            "step": self._current_step,
            "execution_id": self._execution_id,
        }

        # Core V1 Agent 状态
        if hasattr(self.agent, "_ctx"):
            ctx = self.agent._ctx.get()
            state["context"] = ctx

        # Core V2 Agent 状态
        if hasattr(self.agent, "_messages"):
            state["messages"] = [
                {"role": m.role, "content": m.content[:500]}
                for m in self.agent._messages[-20:]
            ]

        return state

    async def _restore_checkpoint(self, checkpoint_id: str) -> bool:
        """恢复检查点"""
        restored = await self._checkpoint_manager.restore_checkpoint(checkpoint_id)
        if not restored:
            return False

        state = restored["state"]
        self._current_step = state.get("step", 0)

        # Core V1 Agent 恢复
        if hasattr(self.agent, "_ctx"):
            self.agent._ctx.set(state.get("context", {}))

        # Core V2 Agent 恢复
        if hasattr(self.agent, "_messages"):
            from ..llm_adapter import LLMMessage

            messages_data = state.get("messages", [])
            self.agent._messages = [
                LLMMessage(
                    role=m.get("role"),
                    content=m.get("content"),
                )
                for m in messages_data
            ]

        logger.info(
            f"[ReliabilityAdapter] 恢复检查点: {checkpoint_id[:8]}, "
            f"step={self._current_step}"
        )

        return True

    async def save_checkpoint(self, message: str = "") -> str:
        """手动保存检查点"""
        from .smart_checkpoint import CheckpointType

        checkpoint = await self._checkpoint_manager.create_checkpoint(
            execution_id=self._execution_id,
            checkpoint_type=CheckpointType.MANUAL,
            state=self._get_current_state(),
            step_index=self._current_step,
            message=message,
        )

        return checkpoint.checkpoint_id

    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        if self._metrics:
            return self._metrics.get_summary()
        return {}

    def get_health_report(self) -> Dict[str, Any]:
        """获取健康报告"""
        if self._metrics:
            report = self._metrics.get_health_report()
            return {
                "health_score": report.health_score,
                "health_status": report.health_status.value,
                "issues": report.issues,
                "recommendations": report.recommendations,
            }
        return {}


class StateMachineAgentExecutor:
    """
    状态机 Agent 执行器

    将 StateMachineAgent 与现有 Agent 集成的执行器。
    适用于需要完整状态机能力的场景。

    使用示例:
        # Core V1 Agent
        agent = ReActMasterAgent()
        executor = StateMachineAgentExecutor.from_v1_agent(agent)
        result = await executor.execute("分析日志")

        # Core V2 Agent
        agent = ReActReasoningAgent(info, llm_adapter)
        executor = StateMachineAgentExecutor.from_v2_agent(agent)
        result = await executor.execute("分析日志")
    """

    def __init__(
        self,
        state_machine: "StateMachineAgent",
        checkpoint_manager: "SmartCheckpointManager",
        memory_manager: "HierarchicalMemoryManager",
        metrics: "AgentMetrics",
    ):
        self.state_machine = state_machine
        self.checkpoint_manager = checkpoint_manager
        self.memory_manager = memory_manager
        self.metrics = metrics

    @classmethod
    def from_v1_agent(
        cls,
        agent: Any,
        config: Optional[ReliabilityConfig] = None,
    ) -> "StateMachineAgentExecutor":
        """从 Core V1 Agent 创建执行器"""
        config = config or ReliabilityConfig()

        # 创建状态机函数
        async def think_func(input_msg):
            if hasattr(agent, "thinking"):
                from derisk.agent import AgentMessage

                msg = AgentMessage(content=input_msg)
                # Core V1 thinking 返回 AgentLLMOut
                llm_out = await agent.thinking(
                    messages=[msg],
                    reply_message_id="",
                )
                return llm_out.content if llm_out else ""
            return str(input_msg)

        async def act_func(thinking_result):
            if hasattr(agent, "act"):
                # Core V1 act 返回 ActionOutput 列表
                from derisk.agent import AgentMessage

                msg = AgentMessage(content=thinking_result)
                outputs = await agent.act(
                    message=msg,
                    sender=None,
                )
                if outputs:
                    return outputs[0].content
            return thinking_result

        async def verify_func(action_result):
            if hasattr(agent, "verify"):
                verified, reason = await agent.verify(action_result)
                return (verified, reason)
            return (True, "默认验证通过")

        return cls._create_executor(
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
            config=config,
            max_steps=getattr(agent, "max_retry_count", 100),
        )

    @classmethod
    def from_v2_agent(
        cls,
        agent: Any,
        config: Optional[ReliabilityConfig] = None,
    ) -> "StateMachineAgentExecutor":
        """从 Core V2 Agent 创建执行器"""
        config = config or ReliabilityConfig()

        # 创建状态机函数
        async def think_func(input_msg):
            if hasattr(agent, "think"):
                result = []
                async for chunk in agent.think(input_msg):
                    result.append(chunk)
                return "".join(result)
            return input_msg

        async def act_func(thinking_result):
            if hasattr(agent, "decide") and hasattr(agent, "act"):
                from .enhanced_agent import Decision

                decision = await agent.decide({"thinking": thinking_result})
                if hasattr(decision, "tool_name"):
                    action_result = await agent.act(decision)
                    return action_result.output
            return thinking_result

        async def verify_func(action_result):
            # Core V2 没有 verify，使用默认验证
            return (True, "默认验证通过")

        return cls._create_executor(
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
            config=config,
            max_steps=getattr(agent.info, "max_steps", 30)
            if hasattr(agent, "info")
            else 30,
        )

    @classmethod
    def _create_executor(
        cls,
        think_func: Callable,
        act_func: Callable,
        verify_func: Callable,
        config: ReliabilityConfig,
        max_steps: int,
    ) -> "StateMachineAgentExecutor":
        """创建执行器"""
        from .state_machine import StateMachineAgent
        from .smart_checkpoint import SmartCheckpointManager
        from .hierarchical_memory import HierarchicalMemoryManager
        from .agent_metrics import AgentMetrics

        checkpoint_manager = SmartCheckpointManager(
            strategy=config.checkpoint_strategy,
            checkpoint_store=config.state_store,
            checkpoint_interval=config.checkpoint_interval,
            max_checkpoints=config.max_checkpoints,
        )

        memory_manager = HierarchicalMemoryManager(
            working_memory_tokens=config.working_memory_tokens,
            episodic_memory_tokens=config.episodic_memory_tokens,
            semantic_memory_tokens=config.semantic_memory_tokens,
        )

        metrics = AgentMetrics() if config.enable_metrics else None

        state_machine = StateMachineAgent(
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
            checkpoint_manager=checkpoint_manager,
            max_steps=max_steps,
        )

        return cls(state_machine, checkpoint_manager, memory_manager, metrics)

    async def execute(
        self,
        goal: str,
        checkpoint_id: Optional[str] = None,
        **kwargs,
    ) -> "StateMachineResult":
        """执行任务"""
        # 恢复检查点
        if checkpoint_id:
            await self.state_machine.restore_from_checkpoint(checkpoint_id)

        # 执行
        result = await self.state_machine.execute(goal)

        # 记录指标
        if self.metrics:
            self.metrics.record_step(
                step_index=result.total_steps,
                state=result.final_state.name,
                duration_ms=result.total_time_ms,
                success=result.success,
            )

        return result

    async def pause(self) -> Optional[str]:
        """暂停执行"""
        return await self.state_machine.pause()

    async def resume(self) -> None:
        """恢复执行"""
        await self.state_machine.resume()

    def get_health_score(self) -> float:
        """获取健康分数"""
        if self.metrics:
            return self.metrics.calculate_health_score()
        return 100.0


# 便捷函数


def make_reliable(
    agent: Any,
    config: Optional[ReliabilityConfig] = None,
) -> ReliabilityAdapter:
    """
    为 Agent 添加可靠性能力的便捷函数

    自动检测 Agent 类型并选择合适的集成方式

    Args:
        agent: Core V1 或 Core V2 Agent
        config: 可靠性配置

    Returns:
        ReliabilityAdapter 实例

    Example:
        from derisk.agent.core_v2 import make_reliable

        # Core V1
        agent = ReActMasterAgent()
        reliable = make_reliable(agent)
        result = await reliable.run("分析日志")

        # Core V2
        agent = ReActReasoningAgent(info, llm_adapter)
        reliable = make_reliable(agent)
        result = await reliable.run("分析日志")
    """
    # 检测 Agent 类型
    if hasattr(agent, "generate_reply"):
        return ReliabilityAdapter.wrap_v1_agent(agent, config)
    elif hasattr(agent, "run"):
        return ReliabilityAdapter.wrap_v2_agent(agent, config)
    else:
        raise ValueError(f"Unknown agent type: {type(agent)}")


def with_state_machine(
    agent: Any,
    config: Optional[ReliabilityConfig] = None,
) -> StateMachineAgentExecutor:
    """
    使用状态机模式执行 Agent 的便捷函数

    提供完整的可靠性能力: 状态机执行、检查点、分层记忆、健康监控

    Args:
        agent: Core V1 或 Core V2 Agent
        config: 可靠性配置

    Returns:
        StateMachineAgentExecutor 实例

    Example:
        from derisk.agent.core_v2 import with_state_machine

        agent = ReActMasterAgent()
        executor = with_state_machine(agent)

        # 正常执行
        result = await executor.execute("分析日志")

        # 从检查点恢复
        result = await executor.execute("分析日志", checkpoint_id="abc123")

        # 检查健康状态
        print(f"Health: {executor.get_health_score()}")
    """
    if hasattr(agent, "generate_reply"):
        return StateMachineAgentExecutor.from_v1_agent(agent, config)
    elif hasattr(agent, "run"):
        return StateMachineAgentExecutor.from_v2_agent(agent, config)
    else:
        raise ValueError(f"Unknown agent type: {type(agent)}")
