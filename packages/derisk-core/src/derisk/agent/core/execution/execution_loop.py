"""
Execution Loop - Simplified agent execution loop.
Extracted from base_agent.py for better maintainability.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ExecutionState(Enum):
    """Execution state for the agent loop."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class LoopContext:
    """Context for a single execution loop iteration."""

    iteration: int = 0
    max_iterations: int = 300  # Increased from 10 to support long-running tasks
    state: ExecutionState = ExecutionState.PENDING
    last_output: Optional[Any] = None
    error_message: Optional[str] = None
    should_terminate: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_continue(self) -> bool:
        """Check if loop can continue."""
        return (
            self.iteration < self.max_iterations
            and self.state == ExecutionState.RUNNING
            and not self.should_terminate
        )

    def increment(self):
        """Increment iteration counter."""
        self.iteration += 1

    def mark_completed(self):
        """Mark execution as completed."""
        self.state = ExecutionState.COMPLETED

    def mark_failed(self, error: str):
        """Mark execution as failed."""
        self.state = ExecutionState.FAILED
        self.error_message = error

    def terminate(self, reason: Optional[str] = None):
        """Request termination."""
        self.should_terminate = True
        if reason:
            self.metadata["terminate_reason"] = reason


@dataclass
class ExecutionMetrics:
    """Metrics for execution tracking."""

    start_time_ms: int = 0
    end_time_ms: int = 0
    total_iterations: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0

    @property
    def duration_ms(self) -> int:
        """Get execution duration in milliseconds."""
        return self.end_time_ms - self.start_time_ms if self.end_time_ms else 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "duration_ms": self.duration_ms,
            "total_iterations": self.total_iterations,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
        }


class ExecutionContext:
    """
    Execution context manager for agent loops.

    Manages the lifecycle of agent execution, including:
    - Loop iterations
    - State transitions
    - Metrics collection
    - Error handling
    """

    def __init__(
        self,
        max_iterations: int = 300,  # Increased from 10 to support long-running tasks
        on_iteration_start: Optional[Callable] = None,
        on_iteration_end: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ):
        self.max_iterations = max_iterations
        self.on_iteration_start = on_iteration_start
        self.on_iteration_end = on_iteration_end
        self.on_error = on_error
        self._loop_context: Optional[LoopContext] = None
        self._metrics = ExecutionMetrics()

    def start(self) -> LoopContext:
        """Start a new execution context."""
        self._loop_context = LoopContext(max_iterations=self.max_iterations)
        self._loop_context.state = ExecutionState.RUNNING
        self._metrics.start_time_ms = time.time_ns() // 1_000_000
        return self._loop_context

    async def run_iteration(
        self, iteration_func: Callable[[LoopContext], Any]
    ) -> Tuple[bool, Optional[Any]]:
        """
        Run a single iteration.

        Args:
            iteration_func: Async function to run for this iteration

        Returns:
            Tuple of (should_continue, result)
        """
        if not self._loop_context or self._loop_context.state != ExecutionState.RUNNING:
            return False, None

        ctx = self._loop_context

        try:
            if self.on_iteration_start:
                await self.on_iteration_start(ctx)

            result = await iteration_func(ctx)
            ctx.last_output = result
            ctx.increment()

            if self.on_iteration_end:
                await self.on_iteration_end(ctx, result)

            return ctx.can_continue(), result

        except Exception as e:
            logger.exception(f"Iteration {ctx.iteration} failed: {e}")
            ctx.mark_failed(str(e))

            if self.on_error:
                await self.on_error(e, ctx)

            return False, None

    def end(self) -> ExecutionMetrics:
        """End the execution context and return metrics."""
        if self._loop_context:
            self._metrics.total_iterations = self._loop_context.iteration
            if self._loop_context.state == ExecutionState.RUNNING:
                self._loop_context.mark_completed()

        self._metrics.end_time_ms = time.time_ns() // 1_000_000
        return self._metrics

    @property
    def context(self) -> Optional[LoopContext]:
        """Get current loop context."""
        return self._loop_context

    @property
    def metrics(self) -> ExecutionMetrics:
        """Get execution metrics."""
        return self._metrics


class SimpleExecutionLoop:
    """
    Simplified execution loop implementation.

    Provides a clean, maintainable loop structure inspired by
    opencode's agentic loop design.
    """

    def __init__(
        self,
        max_iterations: int = 300,  # Increased from 10 to support long-running tasks
        enable_retry: bool = True,
        max_retries: int = 3,
    ):
        self.max_iterations = max_iterations
        self.enable_retry = enable_retry
        self.max_retries = max_retries
        self._context = ExecutionContext(max_iterations=max_iterations)

    async def run(
        self,
        think_func: Callable,
        act_func: Callable,
        verify_func: Callable,
        should_continue_func: Optional[Callable] = None,
    ) -> Tuple[bool, ExecutionMetrics]:
        """
        Run the execution loop.

        Args:
            think_func: Async function to generate thoughts
            act_func: Async function to execute actions
            verify_func: Async function to verify results
            should_continue_func: Optional function to check if should continue

        Returns:
            Tuple of (success, metrics)
        """
        ctx = self._context.start()
        success = False

        try:
            while ctx.can_continue():
                try:
                    thought = await think_func(ctx)
                    if ctx.should_terminate:
                        break

                    action_result = await act_func(thought, ctx)
                    if ctx.should_terminate:
                        break

                    verify_result = await verify_func(action_result, ctx)
                    success = verify_result

                    if should_continue_func:
                        if not await should_continue_func(action_result, ctx):
                            ctx.terminate("should_continue_func returned False")
                            break

                except Exception as e:
                    logger.exception(f"Loop iteration failed: {e}")
                    if not self.enable_retry or ctx.iteration >= self.max_retries:
                        ctx.mark_failed(str(e))
                        break

        finally:
            metrics = self._context.end()

        return success, metrics

    def request_termination(self, reason: Optional[str] = None):
        """Request termination of the loop."""
        if self._context.context:
            self._context.context.terminate(reason)


def create_execution_context(max_iterations: int = 300, **kwargs) -> ExecutionContext:
    """Factory function to create an execution context."""
    return ExecutionContext(max_iterations=max_iterations, **kwargs)


def create_execution_loop(max_iterations: int = 300, **kwargs) -> SimpleExecutionLoop:
    """Factory function to create an execution loop."""
    return SimpleExecutionLoop(max_iterations=max_iterations, **kwargs)
