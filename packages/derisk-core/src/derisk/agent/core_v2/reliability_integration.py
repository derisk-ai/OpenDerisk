"""
ReActMasterAgent 可靠性集成方案

本模块提供 ReActMasterAgent (Core V1) 与可靠性层的深度集成。

有两种集成方式：
1. 包装器模式 - 不修改 Agent，通过适配器添加能力
2. 内部集成模式 - 修改 Agent 内部，使用状态机驱动

推荐：
- 快速集成：使用包装器模式 (make_reliable)
- 深度集成：使用内部集成模式
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from derisk.agent.core.base_agent import ConversableAgent
    from derisk.agent import AgentMessage

logger = logging.getLogger(__name__)


@dataclass
class AgentExecutionState:
    """Agent 执行状态"""

    step: int = 0
    total_steps: int = 0
    observation: str = ""
    done: bool = False
    is_success: bool = True
    fail_reason: Optional[str] = None
    last_action_output: Optional[Any] = None
    checkpoint_id: Optional[str] = None
    started_at: Optional[datetime] = None


class ReActMasterReliabilityMixin:
    """
    ReActMasterAgent 可靠性 Mixin

    使用方式:
        class ReliableReActMasterAgent(ReActMasterAgent, ReActMasterReliabilityMixin):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.init_reliability()

    或者动态添加:
        agent = ReActMasterAgent()
        ReActMasterReliabilityMixin.inject(agent)
    """

    _reliability_initialized: bool = False
    _execution_state: Optional[AgentExecutionState] = None
    _checkpoint_manager: Optional[Any] = None
    _memory_manager: Optional[Any] = None
    _metrics: Optional[Any] = None
    _state_handlers: Dict[str, List[Any]] = field(default_factory=dict)

    def init_reliability(
        self,
        checkpoint_strategy: str = "adaptive",
        state_store: Optional[Any] = None,
        working_memory_tokens: int = 8000,
        checkpoint_interval: int = 10,
        enable_metrics: bool = True,
    ):
        """
        初始化可靠性组件

        Args:
            checkpoint_strategy: 检查点策略
            state_store: 状态存储
            working_memory_tokens: 工作记忆容量
            checkpoint_interval: 检查点间隔
            enable_metrics: 是否启用指标
        """
        if self._reliability_initialized:
            return

        from derisk.agent.core_v2 import (
            SmartCheckpointManager,
            CheckpointStrategy,
            HierarchicalMemoryManager,
            AgentMetrics,
        )

        strategy = CheckpointStrategy(checkpoint_strategy)

        self._checkpoint_manager = SmartCheckpointManager(
            strategy=strategy,
            checkpoint_store=state_store,
            checkpoint_interval=checkpoint_interval,
        )

        self._memory_manager = HierarchicalMemoryManager(
            working_memory_tokens=working_memory_tokens,
        )

        if enable_metrics:
            self._metrics = AgentMetrics()

        self._execution_state = AgentExecutionState()
        self._reliability_initialized = True

        logger.info(
            f"[ReActMasterReliability] Initialized with strategy={checkpoint_strategy}"
        )

    @classmethod
    def inject(cls, agent: "ConversableAgent", **kwargs):
        """
        动态注入可靠性能力到现有 Agent

        Args:
            agent: 要注入的 Agent
            **kwargs: 传递给 init_reliability 的参数
        """
        # 添加属性和方法
        agent._reliability_initialized = False
        agent._execution_state = None
        agent._checkpoint_manager = None
        agent._memory_manager = None
        agent._metrics = None

        # 绑定方法
        agent.init_reliability = lambda **kw: cls.init_reliability(agent, **kw)
        agent._save_checkpoint_reliable = lambda msg="": cls._save_checkpoint_reliable(
            agent, msg
        )
        agent._restore_checkpoint_reliable = lambda cp_id: (
            cls._restore_checkpoint_reliable(agent, cp_id)
        )
        agent._record_step_reliable = lambda **kw: cls._record_step_reliable(
            agent, **kw
        )
        agent._get_health_reliable = lambda: cls._get_health_reliable(agent)

        # 初始化
        agent.init_reliability(**kwargs)

        return agent

    async def _save_checkpoint_reliable(self, message: str = "") -> Optional[str]:
        """保存检查点"""
        if not self._checkpoint_manager or not self._execution_state:
            return None

        from derisk.agent.core_v2 import CheckpointType

        try:
            # 获取 Agent 上下文
            conv_id = getattr(self, "not_null_agent_context", None)
            conv_id = conv_id.conv_id if conv_id else "default"

            # 收集状态
            state = {
                "step": self._execution_state.step,
                "observation": self._execution_state.observation[:1000]
                if self._execution_state.observation
                else "",
                "done": self._execution_state.done,
                "retry_counter": getattr(self, "current_retry_counter", 0),
            }

            # 收集上下文
            context = {}
            if hasattr(self, "_ctx"):
                try:
                    context = self._ctx.get()
                except:
                    pass

            checkpoint = await self._checkpoint_manager.create_checkpoint(
                execution_id=conv_id,
                checkpoint_type=CheckpointType.AUTOMATIC,
                state=state,
                context=context,
                step_index=self._execution_state.step,
                message=message,
            )

            self._execution_state.checkpoint_id = checkpoint.checkpoint_id

            logger.info(
                f"[ReActMasterReliability] Checkpoint saved: {checkpoint.checkpoint_id[:8]}, "
                f"step={self._execution_state.step}"
            )

            return checkpoint.checkpoint_id

        except Exception as e:
            logger.error(f"[ReActMasterReliability] Failed to save checkpoint: {e}")
            return None

    async def _restore_checkpoint_reliable(self, checkpoint_id: str) -> bool:
        """恢复检查点"""
        if not self._checkpoint_manager:
            return False

        try:
            restored = await self._checkpoint_manager.restore_checkpoint(checkpoint_id)

            if not restored:
                return False

            state = restored["state"]

            # 恢复执行状态
            if self._execution_state:
                self._execution_state.step = state.get("step", 0)
                self._execution_state.observation = state.get("observation", "")
                self._execution_state.done = state.get("done", False)
                self._execution_state.checkpoint_id = checkpoint_id

            # 恢复 retry counter
            if hasattr(self, "current_retry_counter"):
                self.current_retry_counter = state.get("retry_counter", 0)

            logger.info(
                f"[ReActMasterReliability] Restored from checkpoint: {checkpoint_id[:8]}, "
                f"step={state.get('step', 0)}"
            )

            return True

        except Exception as e:
            logger.error(f"[ReActMasterReliability] Failed to restore checkpoint: {e}")
            return False

    def _record_step_reliable(
        self,
        state: str,
        duration_ms: float = 0,
        success: bool = True,
        tokens_used: int = 0,
    ):
        """记录步骤指标"""
        if not self._metrics:
            return

        self._metrics.record_step(
            step_index=self._execution_state.step if self._execution_state else 0,
            state=state,
            duration_ms=duration_ms,
            success=success,
            tokens_used=tokens_used,
        )

    def _get_health_reliable(self) -> Dict[str, Any]:
        """获取健康状态"""
        if not self._metrics:
            return {"health_score": 100.0}

        return self._metrics.get_summary()


class ReliableGenerateReplyWrapper:
    """
    可靠的 generate_reply 包装器

    包装 ConversableAgent 的 generate_reply 方法，
    添加状态机驱动的执行和检查点能力。

    使用方式:
        agent = ReActMasterAgent()
        wrapper = ReliableGenerateReplyWrapper(agent)
        result = await wrapper.generate_reply_with_reliability(message)
    """

    def __init__(
        self, agent: "ConversableAgent", config: Optional[Dict[str, Any]] = None
    ):
        self.agent = agent
        self.config = config or {}

        # 注入可靠性能力
        ReActMasterReliabilityMixin.inject(agent, **self.config.get("reliability", {}))

        self._original_generate_reply = agent.generate_reply

    async def generate_reply_with_reliability(
        self,
        received_message: "AgentMessage",
        sender: Optional[Any] = None,
        resume_checkpoint: Optional[str] = None,
        **kwargs,
    ) -> "AgentMessage":
        """
        带可靠性保障的 generate_reply

        流程:
        1. 初始化执行状态
        2. 恢复检查点（如果提供）
        3. 执行原始 generate_reply
        4. 保存检查点
        5. 返回结果
        """
        import time

        start_time = time.time()

        # 初始化执行状态
        self.agent._execution_state = AgentExecutionState(
            started_at=datetime.now(),
        )

        # 恢复检查点
        if resume_checkpoint:
            restored = await self.agent._restore_checkpoint_reliable(resume_checkpoint)
            if restored:
                logger.info(
                    f"[ReliableGenerateReply] Resumed from checkpoint: {resume_checkpoint[:8]}"
                )

        # 保存初始检查点
        await self.agent._save_checkpoint_reliable("Execution started")

        try:
            # 执行原始 generate_reply
            result = await self._original_generate_reply(
                received_message=received_message,
                sender=sender,
                **kwargs,
            )

            # 记录成功
            duration_ms = (time.time() - start_time) * 1000
            self.agent._record_step_reliable(
                state="COMPLETED",
                duration_ms=duration_ms,
                success=True,
            )

            # 保存完成检查点
            checkpoint_id = await self.agent._save_checkpoint_reliable(
                "Execution completed"
            )

            # 附加检查点信息到结果
            if hasattr(result, "extra") and result.extra is None:
                result.extra = {}
            if hasattr(result, "extra"):
                result.extra["checkpoint_id"] = checkpoint_id
                result.extra["health"] = self.agent._get_health_reliable()

            return result

        except Exception as e:
            # 记录失败
            duration_ms = (time.time() - start_time) * 1000
            self.agent._record_step_reliable(
                state="FAILED",
                duration_ms=duration_ms,
                success=False,
            )

            # 保存错误检查点
            checkpoint_id = await self.agent._save_checkpoint_reliable(
                f"Error: {str(e)[:200]}"
            )

            logger.exception(
                f"[ReliableGenerateReply] Execution failed, checkpoint saved: {checkpoint_id}"
            )

            raise


class StateMachineDrivenAgent:
    """
    状态机驱动的 Agent 执行器

    将 Core V1 Agent 的 while 循环改造为状态机驱动的执行模式。

    状态映射:
    - IDLE → INITIALIZING → THINKING → ACTING → VERIFYING → COMPLETED/FAILED

    使用方式:
        agent = ReActMasterAgent()
        executor = StateMachineDrivenAgent(agent)
        result = await executor.execute("分析日志")
    """

    def __init__(
        self, agent: "ConversableAgent", config: Optional[Dict[str, Any]] = None
    ):
        self.agent = agent
        self.config = config or {}

        # 状态机状态
        self.current_state = "IDLE"
        self.step = 0
        self.max_steps = getattr(agent, "max_retry_count", 100)

        # 执行结果
        self.observation = ""
        self.done = False
        self.reply_message = None
        self.act_outs = []

        # 可靠性组件
        from derisk.agent.core_v2 import (
            SmartCheckpointManager,
            CheckpointStrategy,
            AgentMetrics,
        )

        self.checkpoint_manager = SmartCheckpointManager(
            strategy=CheckpointStrategy(
                self.config.get("checkpoint_strategy", "adaptive")
            ),
            checkpoint_interval=self.config.get("checkpoint_interval", 10),
        )

        self.metrics = (
            AgentMetrics() if self.config.get("enable_metrics", True) else None
        )

        # 状态转换映射
        self.transitions = {
            "IDLE": ["INITIALIZING"],
            "INITIALIZING": ["THINKING", "FAILED"],
            "THINKING": ["ACTING", "COMPLETED", "FAILED"],
            "ACTING": ["VERIFYING", "THINKING", "FAILED"],
            "VERIFYING": ["THINKING", "COMPLETED", "FAILED"],
            "COMPLETED": [],
            "FAILED": [],
        }

    async def transition_to(self, new_state: str):
        """状态转换"""
        if new_state not in self.transitions.get(self.current_state, []):
            raise ValueError(f"Invalid transition: {self.current_state} -> {new_state}")

        old_state = self.current_state
        self.current_state = new_state

        logger.info(f"[StateMachineDriven] Transition: {old_state} -> {new_state}")

        # 记录转换
        if self.metrics:
            self.metrics.record_transition(
                from_state=old_state,
                to_state=new_state,
                duration_ms=0,
            )

    async def execute(
        self,
        message: str,
        resume_checkpoint: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        状态机驱动的执行

        Args:
            message: 用户消息
            resume_checkpoint: 恢复的检查点 ID

        Returns:
            执行结果
        """
        import time

        start_time = time.time()

        # 恢复检查点
        if resume_checkpoint:
            restored = await self.checkpoint_manager.restore_checkpoint(
                resume_checkpoint
            )
            if restored:
                self.step = restored["state"].get("step", 0)
                self.observation = restored["state"].get("observation", "")

        try:
            # IDLE -> INITIALIZING
            await self.transition_to("INITIALIZING")
            await self._do_initialize(message, **kwargs)

            # INITIALIZING -> THINKING
            await self.transition_to("THINKING")

            # 主循环
            while not self.done and self.step < self.max_steps:
                # THINKING
                thinking_result = await self._do_thinking(**kwargs)

                if self.done:
                    await self.transition_to("COMPLETED")
                    break

                # THINKING -> ACTING
                await self.transition_to("ACTING")
                action_result = await self._do_acting(**kwargs)

                # ACTING -> VERIFYING
                await self.transition_to("VERIFYING")
                verified = await self._do_verifying(action_result)

                if verified:
                    await self.transition_to("COMPLETED")
                    break

                # VERIFYING -> THINKING
                await self.transition_to("THINKING")
                self.step += 1

                # 检查是否需要保存检查点
                if self.step % 10 == 0:
                    await self._save_checkpoint("Periodic checkpoint")

            # 记录完成
            duration_ms = (time.time() - start_time) * 1000
            if self.metrics:
                self.metrics.record_step(
                    step_index=self.step,
                    state=self.current_state,
                    duration_ms=duration_ms,
                    success=self.current_state == "COMPLETED",
                )

            # 保存最终检查点
            checkpoint_id = await self._save_checkpoint("Execution completed")

            return {
                "success": self.current_state == "COMPLETED",
                "reply_message": self.reply_message,
                "step": self.step,
                "checkpoint_id": checkpoint_id,
                "health": self.metrics.get_summary() if self.metrics else None,
            }

        except Exception as e:
            await self.transition_to("FAILED")

            checkpoint_id = await self._save_checkpoint(f"Error: {str(e)[:200]}")

            return {
                "success": False,
                "error": str(e),
                "step": self.step,
                "checkpoint_id": checkpoint_id,
            }

    async def _do_initialize(self, message: str, **kwargs):
        """初始化"""
        from derisk.agent import AgentMessage

        self.observation = message
        self.received_message = AgentMessage(content=message)

    async def _do_thinking(self, **kwargs):
        """思考阶段"""
        if hasattr(self.agent, "thinking"):
            result = await self.agent.thinking(
                messages=[self.received_message]
                if hasattr(self, "received_message")
                else [],
                reply_message_id="",
            )
            return result
        return None

    async def _do_acting(self, **kwargs):
        """行动阶段"""
        if hasattr(self.agent, "act"):
            result = await self.agent.act(
                message=self.reply_message,
                sender=None,
            )
            self.act_outs = result if isinstance(result, list) else [result]
            return self.act_outs
        return []

    async def _do_verifying(self, action_result) -> bool:
        """验证阶段"""
        if not action_result:
            return False

        for output in action_result:
            if hasattr(output, "terminate") and output.terminate:
                self.done = True
                return True

        return False

    async def _save_checkpoint(self, message: str) -> Optional[str]:
        """保存检查点"""
        conv_id = getattr(self.agent, "not_null_agent_context", None)
        conv_id = conv_id.conv_id if conv_id else "default"

        from derisk.agent.core_v2 import CheckpointType

        checkpoint = await self.checkpoint_manager.create_checkpoint(
            execution_id=conv_id,
            checkpoint_type=CheckpointType.AUTOMATIC,
            state={
                "step": self.step,
                "observation": self.observation[:1000],
                "done": self.done,
            },
            step_index=self.step,
            message=message,
        )

        return checkpoint.checkpoint_id


# 便捷函数


def make_react_master_reliable(
    agent: "ConversableAgent",
    checkpoint_strategy: str = "adaptive",
    state_store: Optional[Any] = None,
    **kwargs,
) -> ReliableGenerateReplyWrapper:
    """
    为 ReActMasterAgent 添加可靠性能力的便捷函数

    Args:
        agent: ReActMasterAgent 实例
        checkpoint_strategy: 检查点策略
        state_store: 状态存储

    Returns:
        ReliableGenerateReplyWrapper 实例

    Example:
        from derisk.agent.expand.react_master_agent import ReActMasterAgent
        from derisk.agent.core_v2.reliability_integration import make_react_master_reliable

        agent = ReActMasterAgent()
        reliable = make_react_master_reliable(agent)

        result = await reliable.generate_reply_with_reliability(message)
        print(f"检查点: {result.extra['checkpoint_id']}")
    """
    config = {
        "reliability": {
            "checkpoint_strategy": checkpoint_strategy,
            "state_store": state_store,
            **kwargs,
        }
    }

    return ReliableGenerateReplyWrapper(agent, config)


def with_state_machine_execution(
    agent: "ConversableAgent",
    **kwargs,
) -> StateMachineDrivenAgent:
    """
    使用状态机模式执行 ReActMasterAgent

    将 while 循环改造为状态机驱动，提供完整的可靠性能力。

    Args:
        agent: ReActMasterAgent 实例

    Returns:
        StateMachineDrivenAgent 实例

    Example:
        from derisk.agent.expand.react_master_agent import ReActMasterAgent
        from derisk.agent.core_v2.reliability_integration import with_state_machine_execution

        agent = ReActMasterAgent()
        executor = with_state_machine_execution(agent)

        result = await executor.execute("分析日志")
        print(f"步数: {result['step']}")
        print(f"健康分数: {result['health']['health_score']}")
    """
    return StateMachineDrivenAgent(agent, kwargs)
