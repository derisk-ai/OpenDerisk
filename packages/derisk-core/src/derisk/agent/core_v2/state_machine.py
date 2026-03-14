"""
State Machine Pattern for Agent Execution

Implements a formal state machine to replace simple while loops,
providing:
- Predictable state transitions
- Better error recovery
- Checkpoint-friendly execution
- Improved debugging and observability

This module implements the P0 improvements from the reliability analysis.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from .agent_harness import (
        CheckpointManager,
        ExecutionContext,
        ExecutionSnapshot,
        StateStore,
    )
    from .smart_checkpoint import SmartCheckpointManager

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """
    Agent状态定义

    形式化的状态机状态，替代简单的while循环。
    每个状态都有明确的转换规则和回调。
    """

    IDLE = auto()  # 空闲 - 初始状态
    INITIALIZING = auto()  # 初始化中 - 加载配置、工具
    THINKING = auto()  # 思考中 - LLM推理
    ACTING = auto()  # 行动中 - 执行工具
    VERIFYING = auto()  # 验证中 - 检查结果
    PAUSED = auto()  # 暂停 - 等待恢复
    COMPACTING = auto()  # 压缩中 - 上下文压缩
    RECOVERING = auto()  # 恢复中 - 从检查点恢复
    COMPLETED = auto()  # 完成 - 任务成功结束
    FAILED = auto()  # 失败 - 任务失败

    def is_terminal(self) -> bool:
        """检查是否为终态"""
        return self in {AgentState.COMPLETED, AgentState.FAILED}

    def is_active(self) -> bool:
        """检查是否为活跃状态"""
        return self in {
            AgentState.THINKING,
            AgentState.ACTING,
            AgentState.VERIFYING,
            AgentState.COMPACTING,
            AgentState.RECOVERING,
        }


class StateTransitionError(Exception):
    """无效状态转换错误"""

    def __init__(self, from_state: AgentState, to_state: AgentState, message: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition from {from_state.name} to {to_state.name}: {message}"
        )


class RecoverableError(Exception):
    """可恢复错误 - Agent可以尝试从检查点恢复"""

    pass


class FatalError(Exception):
    """致命错误 - Agent必须停止"""

    pass


@dataclass
class StateTransitionRecord:
    """状态转换记录"""

    from_state: AgentState
    to_state: AgentState
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    checkpoint_id: Optional[str] = None


class StateTransitionProtocol(Protocol):
    """状态转换协议"""

    async def can_transition(
        self, from_state: AgentState, to_state: AgentState
    ) -> bool:
        """检查是否可以转换"""
        ...

    async def on_enter(self, state: AgentState, context: Dict[str, Any]) -> None:
        """进入状态时的回调"""
        ...

    async def on_exit(self, state: AgentState, context: Dict[str, Any]) -> None:
        """退出状态时的回调"""
        ...


class DefaultStateTransitionHandler:
    """
    默认状态转换处理器

    实现状态转换的验证和回调逻辑
    """

    # 允许的状态转换映射
    ALLOWED_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
        AgentState.IDLE: {AgentState.INITIALIZING},
        AgentState.INITIALIZING: {AgentState.THINKING, AgentState.FAILED},
        AgentState.THINKING: {
            AgentState.ACTING,
            AgentState.PAUSED,
            AgentState.FAILED,
            AgentState.COMPLETED,  # 直接完成（无需行动）
        },
        AgentState.ACTING: {
            AgentState.VERIFYING,
            AgentState.PAUSED,
            AgentState.FAILED,
            AgentState.THINKING,  # 直接进入下一轮思考
        },
        AgentState.VERIFYING: {
            AgentState.THINKING,
            AgentState.COMPLETED,
            AgentState.COMPACTING,
            AgentState.FAILED,
        },
        AgentState.PAUSED: {
            AgentState.RECOVERING,
            AgentState.THINKING,
            AgentState.FAILED,
        },
        AgentState.RECOVERING: {AgentState.THINKING, AgentState.FAILED},
        AgentState.COMPACTING: {AgentState.THINKING, AgentState.FAILED},
        AgentState.COMPLETED: set(),  # 终态
        AgentState.FAILED: set(),  # 终态
    }

    def __init__(self):
        self._enter_handlers: Dict[AgentState, List[Callable]] = defaultdict(list)
        self._exit_handlers: Dict[AgentState, List[Callable]] = defaultdict(list)
        self._transition_hooks: List[Callable] = []

    def register_enter_handler(self, state: AgentState, handler: Callable) -> None:
        """注册进入状态处理器"""
        self._enter_handlers[state].append(handler)

    def register_exit_handler(self, state: AgentState, handler: Callable) -> None:
        """注册退出状态处理器"""
        self._exit_handlers[state].append(handler)

    def register_transition_hook(self, hook: Callable) -> None:
        """注册转换钩子"""
        self._transition_hooks.append(hook)

    def can_transition(self, from_state: AgentState, to_state: AgentState) -> bool:
        """检查状态转换是否有效"""
        allowed = self.ALLOWED_TRANSITIONS.get(from_state, set())
        return to_state in allowed

    async def on_enter(self, state: AgentState, context: Dict[str, Any]) -> None:
        """进入状态的回调处理"""
        logger.info(f"[StateMachine] Entering state: {state.name}")

        for handler in self._enter_handlers[state]:
            try:
                result = handler(state, context)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(f"[StateMachine] Enter handler error: {e}")

    async def on_exit(self, state: AgentState, context: Dict[str, Any]) -> None:
        """退出状态的回调处理"""
        logger.debug(f"[StateMachine] Exiting state: {state.name}")

        for handler in self._exit_handlers[state]:
            try:
                result = handler(state, context)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(f"[StateMachine] Exit handler error: {e}")

    async def on_transition(
        self, from_state: AgentState, to_state: AgentState, context: Dict[str, Any]
    ) -> None:
        """状态转换钩子"""
        for hook in self._transition_hooks:
            try:
                result = hook(from_state, to_state, context)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(f"[StateMachine] Transition hook error: {e}")


@dataclass
class StateMachineResult:
    """状态机执行结果"""

    final_state: AgentState
    success: bool
    total_steps: int
    total_time_ms: float
    state_history: List[StateTransitionRecord]
    error: Optional[Exception] = None
    output: Any = None
    checkpoint_id: Optional[str] = None


class StateMachineAgent:
    """
    基于状态机的 Agent

    将传统的 while 循环改造为形式化的状态机模式：
    - 明确的状态定义和转换规则
    - 每个状态都可以保存检查点
    - 支持从任意状态恢复
    - 更容易实现暂停/恢复

    示例:
        agent = StateMachineAgent(
            think_func=my_think,
            act_func=my_act,
            verify_func=my_verify
        )

        result = await agent.execute("分析系统日志")

        if not result.success:
            # 从最后检查点恢复
            await agent.resume_from_checkpoint(result.checkpoint_id)
    """

    def __init__(
        self,
        think_func: Callable,
        act_func: Callable,
        verify_func: Optional[Callable] = None,
        should_terminate: Optional[Callable] = None,
        transition_handler: Optional[DefaultStateTransitionHandler] = None,
        checkpoint_manager: Optional["SmartCheckpointManager"] = None,
        max_steps: int = 100,
    ):
        """
        初始化状态机 Agent

        Args:
            think_func: 思考函数，返回思考结果
            act_func: 行动函数，执行动作
            verify_func: 验证函数，检查结果
            should_terminate: 终止条件判断函数
            transition_handler: 状态转换处理器
            checkpoint_manager: 检查点管理器
            max_steps: 最大步数限制
        """
        self.think_func = think_func
        self.act_func = act_func
        self.verify_func = verify_func
        self.should_terminate = should_terminate
        self.transition_handler = transition_handler or DefaultStateTransitionHandler()
        self.checkpoint_manager = checkpoint_manager
        self.max_steps = max_steps

        # 状态
        self.current_state = AgentState.IDLE
        self.state_history: List[StateTransitionRecord] = []
        self._step_count = 0
        self._start_time: Optional[datetime] = None
        self._context: Dict[str, Any] = {}
        self._current_input: Any = None
        self._thinking_result: Any = None
        self._action_result: Any = None

    @property
    def is_terminal(self) -> bool:
        """是否处于终态"""
        return self.current_state.is_terminal()

    @property
    def is_active(self) -> bool:
        """是否处于活跃状态"""
        return self.current_state.is_active()

    def get_state_info(self) -> Dict[str, Any]:
        """获取当前状态信息"""
        return {
            "current_state": self.current_state.name,
            "step_count": self._step_count,
            "is_terminal": self.is_terminal,
            "is_active": self.is_active,
            "state_history_count": len(self.state_history),
        }

    async def transition_to(
        self, new_state: AgentState, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        状态转换

        Args:
            new_state: 目标状态
            context: 转换上下文

        Raises:
            StateTransitionError: 无效的状态转换
        """
        if not self.transition_handler.can_transition(self.current_state, new_state):
            raise StateTransitionError(
                self.current_state,
                new_state,
                f"Transition not allowed. Allowed: {self.transition_handler.ALLOWED_TRANSITIONS.get(self.current_state, set())}",
            )

        old_state = self.current_state
        transition_start = datetime.now()

        # 退出当前状态
        await self.transition_handler.on_exit(old_state, context or {})

        # 记录历史
        record = StateTransitionRecord(
            from_state=old_state,
            to_state=new_state,
            timestamp=transition_start,
            context=context or {},
        )
        self.state_history.append(record)

        # 更新状态
        self.current_state = new_state

        # 触发转换钩子
        await self.transition_handler.on_transition(old_state, new_state, context or {})

        # 进入新状态
        await self.transition_handler.on_enter(new_state, context or {})

        # 更新记录
        record.duration_ms = (datetime.now() - transition_start).total_seconds() * 1000

        logger.info(
            f"[StateMachine] Transition: {old_state.name} -> {new_state.name} "
            f"({record.duration_ms:.2f}ms)"
        )

    async def execute(
        self, goal: str, initial_context: Optional[Dict[str, Any]] = None
    ) -> StateMachineResult:
        """
        执行任务 - 状态机驱动

        Args:
            goal: 任务目标
            initial_context: 初始上下文

        Returns:
            StateMachineResult: 执行结果
        """
        self._start_time = datetime.now()
        self._context = initial_context or {}
        self._context["goal"] = goal
        self._step_count = 0

        try:
            # 初始化
            await self.transition_to(AgentState.INITIALIZING, {"goal": goal})

            # 初始化完成，开始思考
            await self._do_initialize(goal)
            await self.transition_to(AgentState.THINKING)

            # 主循环 - 状态机驱动
            while not self.is_terminal:
                await self._execute_current_state()

            # 构建结果
            total_time_ms = (datetime.now() - self._start_time).total_seconds() * 1000

            return StateMachineResult(
                final_state=self.current_state,
                success=self.current_state == AgentState.COMPLETED,
                total_steps=self._step_count,
                total_time_ms=total_time_ms,
                state_history=self.state_history.copy(),
                output=self._action_result,
            )

        except RecoverableError as e:
            logger.warning(f"[StateMachine] Recoverable error: {e}")
            await self.transition_to(AgentState.PAUSED, {"error": str(e)})

            # 保存检查点
            checkpoint_id = await self._save_checkpoint()

            return StateMachineResult(
                final_state=self.current_state,
                success=False,
                total_steps=self._step_count,
                total_time_ms=(datetime.now() - self._start_time).total_seconds()
                * 1000,
                state_history=self.state_history.copy(),
                error=e,
                checkpoint_id=checkpoint_id,
            )

        except FatalError as e:
            logger.error(f"[StateMachine] Fatal error: {e}")
            await self.transition_to(AgentState.FAILED, {"error": str(e)})

            return StateMachineResult(
                final_state=self.current_state,
                success=False,
                total_steps=self._step_count,
                total_time_ms=(datetime.now() - self._start_time).total_seconds()
                * 1000,
                state_history=self.state_history.copy(),
                error=e,
            )

        except Exception as e:
            logger.exception(f"[StateMachine] Unexpected error: {e}")
            await self.transition_to(AgentState.FAILED, {"error": str(e)})

            return StateMachineResult(
                final_state=self.current_state,
                success=False,
                total_steps=self._step_count,
                total_time_ms=(datetime.now() - self._start_time).total_seconds()
                * 1000,
                state_history=self.state_history.copy(),
                error=e,
            )

    async def _execute_current_state(self) -> None:
        """执行当前状态的逻辑"""

        if self.current_state == AgentState.THINKING:
            await self._do_thinking()

        elif self.current_state == AgentState.ACTING:
            await self._do_acting()

        elif self.current_state == AgentState.VERIFYING:
            await self._do_verifying()

        elif self.current_state == AgentState.COMPACTING:
            await self._do_compacting()

        elif self.current_state == AgentState.RECOVERING:
            await self._do_recovering()

        elif self.current_state == AgentState.PAUSED:
            await self._do_paused()

    async def _do_initialize(self, goal: str) -> None:
        """初始化逻辑"""
        self._current_input = goal
        logger.info(f"[StateMachine] Initialized with goal: {goal[:100]}...")

    async def _do_thinking(self) -> None:
        """思考状态逻辑"""
        try:
            self._thinking_result = await self.think_func(self._current_input)

            # 检查是否应该终止
            if self.should_terminate and self.should_terminate(self._thinking_result):
                await self.transition_to(
                    AgentState.COMPLETED, {"reason": "terminate_condition_met"}
                )
                return

            # 转换到行动状态
            await self.transition_to(
                AgentState.ACTING, {"thinking_result": str(self._thinking_result)[:200]}
            )

        except RecoverableError as e:
            raise
        except Exception as e:
            logger.error(f"[StateMachine] Thinking error: {e}")
            raise FatalError(f"Thinking failed: {e}")

    async def _do_acting(self) -> None:
        """行动状态逻辑"""
        try:
            self._action_result = await self.act_func(self._thinking_result)

            # 检查是否需要验证
            if self.verify_func:
                await self.transition_to(
                    AgentState.VERIFYING,
                    {"action_result": str(self._action_result)[:200]},
                )
            else:
                # 无需验证，检查是否完成或继续
                if self.should_terminate and self.should_terminate(self._action_result):
                    await self.transition_to(AgentState.COMPLETED)
                else:
                    self._step_count += 1
                    self._current_input = self._action_result

                    # 检查是否需要压缩
                    if self._should_compact():
                        await self.transition_to(AgentState.COMPACTING)
                    else:
                        await self.transition_to(AgentState.THINKING)

        except RecoverableError as e:
            raise
        except Exception as e:
            logger.error(f"[StateMachine] Acting error: {e}")
            raise FatalError(f"Action failed: {e}")

    async def _do_verifying(self) -> None:
        """验证状态逻辑"""
        try:
            passed, reason = await self.verify_func(self._action_result)

            if passed:
                await self.transition_to(
                    AgentState.COMPLETED, {"verified": True, "reason": reason}
                )
            else:
                # 验证失败，继续循环
                self._step_count += 1
                self._current_input = self._action_result

                # 检查步数限制
                if self._step_count >= self.max_steps:
                    raise FatalError(f"Max steps ({self.max_steps}) exceeded")

                # 检查是否需要压缩
                if self._should_compact():
                    await self.transition_to(AgentState.COMPACTING)
                else:
                    await self.transition_to(
                        AgentState.THINKING, {"verification_failed": reason}
                    )

        except RecoverableError as e:
            raise
        except Exception as e:
            logger.error(f"[StateMachine] Verification error: {e}")
            raise FatalError(f"Verification failed: {e}")

    async def _do_compacting(self) -> None:
        """压缩状态逻辑"""
        try:
            # TODO: 调用内存压缩器
            logger.info("[StateMachine] Performing context compaction")

            # 压缩完成，继续思考
            await self.transition_to(AgentState.THINKING)

        except Exception as e:
            logger.error(f"[StateMachine] Compaction error: {e}")
            # 压缩失败不中断执行
            await self.transition_to(AgentState.THINKING)

    async def _do_recovering(self) -> None:
        """恢复状态逻辑"""
        try:
            # 恢复完成，继续执行
            await self.transition_to(AgentState.THINKING)

        except Exception as e:
            logger.error(f"[StateMachine] Recovery error: {e}")
            raise FatalError(f"Recovery failed: {e}")

    async def _do_paused(self) -> None:
        """暂停状态逻辑 - 等待恢复"""
        logger.info("[StateMachine] Paused, waiting for resume...")
        # 实际实现中这里会等待恢复信号
        raise RecoverableError("Execution paused, waiting for resume")

    def _should_compact(self) -> bool:
        """判断是否需要压缩上下文"""
        # 简单实现：每 10 步压缩一次
        return self._step_count > 0 and self._step_count % 10 == 0

    async def _save_checkpoint(self) -> Optional[str]:
        """保存检查点"""
        if not self.checkpoint_manager:
            return None

        try:
            # 导入延迟避免循环引用
            from .smart_checkpoint import CheckpointType

            checkpoint = await self.checkpoint_manager.create_checkpoint(
                execution_id=self._context.get("execution_id", "unknown"),
                checkpoint_type=CheckpointType.MANUAL,
                state={
                    "agent_state": self.current_state.value,
                    "step_count": self._step_count,
                    "context": self._context,
                    "current_input": str(self._current_input)[:1000]
                    if self._current_input
                    else None,
                },
                context=self._context,
                step_index=self._step_count,
                message=f"Checkpoint at state {self.current_state.name}",
            )

            logger.info(
                f"[StateMachine] Checkpoint saved: {checkpoint.checkpoint_id[:8]}"
            )
            return checkpoint.checkpoint_id

        except Exception as e:
            logger.error(f"[StateMachine] Checkpoint save failed: {e}")
            return None

    async def pause(self) -> Optional[str]:
        """暂停执行"""
        if self.is_active:
            await self.transition_to(AgentState.PAUSED)
            return await self._save_checkpoint()
        return None

    async def resume(self) -> None:
        """恢复执行"""
        if self.current_state == AgentState.PAUSED:
            await self.transition_to(AgentState.RECOVERING)

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        """
        从检查点恢复

        Args:
            checkpoint_id: 检查点ID

        Returns:
            是否恢复成功
        """
        if not self.checkpoint_manager:
            logger.error("[StateMachine] No checkpoint manager configured")
            return False

        try:
            restored = await self.checkpoint_manager.restore_checkpoint(checkpoint_id)

            if not restored:
                return False

            # 恢复状态
            state_data = restored["state"]
            self.current_state = AgentState(state_data["agent_state"])
            self._step_count = state_data["step_count"]
            self._context = state_data.get("context", {})

            logger.info(
                f"[StateMachine] Restored from checkpoint {checkpoint_id[:8]} "
                f"at state {self.current_state.name}, step {self._step_count}"
            )

            return True

        except Exception as e:
            logger.error(f"[StateMachine] Restore failed: {e}")
            return False


# 便捷函数
def create_state_machine_agent(
    think_func: Callable,
    act_func: Callable,
    verify_func: Optional[Callable] = None,
    **kwargs,
) -> StateMachineAgent:
    """
    创建状态机 Agent 的便捷函数

    Args:
        think_func: 思考函数
        act_func: 行动函数
        verify_func: 验证函数
        **kwargs: 其他参数

    Returns:
        StateMachineAgent 实例
    """
    return StateMachineAgent(
        think_func=think_func, act_func=act_func, verify_func=verify_func, **kwargs
    )
