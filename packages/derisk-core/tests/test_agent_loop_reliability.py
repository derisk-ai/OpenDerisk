"""
Tests for Agent Loop Architecture Improvements

Tests for:
- StateMachineAgent
- SmartCheckpointManager
- HierarchicalMemoryManager
- TaskOrchestrator
- AgentMetrics
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from derisk.agent.core_v2.state_machine import (
    AgentState,
    StateTransitionError,
    RecoverableError,
    FatalError,
    StateTransitionRecord,
    DefaultStateTransitionHandler,
    StateMachineAgent,
    StateMachineResult,
    create_state_machine_agent,
)

from derisk.agent.core_v2.smart_checkpoint import (
    CheckpointStrategy,
    CheckpointType,
    Checkpoint,
    CheckpointNotFoundError,
    CheckpointCorruptedError,
    MemoryStateStore,
    SmartCheckpointManager,
)

from derisk.agent.core_v2.hierarchical_memory import (
    MemoryLayer,
    MemoryType,
    MemoryEntry,
    MemoryStats,
    SimpleMemoryCompressor,
    HierarchicalMemoryManager,
)

from derisk.agent.core_v2.task_orchestrator import (
    TaskPriority,
    TaskStatus,
    RetryPolicy,
    RetryConfig,
    Task,
    TaskOrchestrator,
    WorkflowBuilder,
    WorkflowResult,
    CircularDependencyError,
)

from derisk.agent.core_v2.agent_metrics import (
    HealthStatus,
    AgentMetrics,
    AgentHealthReport,
)


class TestAgentState:
    def test_state_is_terminal(self):
        assert AgentState.COMPLETED.is_terminal() is True
        assert AgentState.FAILED.is_terminal() is True
        assert AgentState.THINKING.is_terminal() is False
        assert AgentState.IDLE.is_terminal() is False

    def test_state_is_active(self):
        assert AgentState.THINKING.is_active() is True
        assert AgentState.ACTING.is_active() is True
        assert AgentState.VERIFYING.is_active() is True
        assert AgentState.IDLE.is_active() is False
        assert AgentState.COMPLETED.is_active() is False


class TestDefaultStateTransitionHandler:
    def setup_method(self):
        self.handler = DefaultStateTransitionHandler()

    def test_valid_transition(self):
        assert (
            self.handler.can_transition(AgentState.IDLE, AgentState.INITIALIZING)
            is True
        )
        assert (
            self.handler.can_transition(AgentState.INITIALIZING, AgentState.THINKING)
            is True
        )
        assert (
            self.handler.can_transition(AgentState.THINKING, AgentState.ACTING) is True
        )

    def test_invalid_transition(self):
        assert (
            self.handler.can_transition(AgentState.IDLE, AgentState.THINKING) is False
        )
        assert (
            self.handler.can_transition(AgentState.COMPLETED, AgentState.THINKING)
            is False
        )
        assert self.handler.can_transition(AgentState.FAILED, AgentState.IDLE) is False

    @pytest.mark.asyncio
    async def test_enter_handler(self):
        called = []

        async def on_enter(state, context):
            called.append(("enter", state))

        self.handler.register_enter_handler(AgentState.THINKING, on_enter)
        await self.handler.on_enter(AgentState.THINKING, {})

        assert len(called) == 1
        assert called[0] == ("enter", AgentState.THINKING)


class TestStateMachineAgent:
    def setup_method(self):
        self.think_func = AsyncMock(return_value="thinking_result")
        self.act_func = AsyncMock(return_value="action_result")
        self.verify_func = AsyncMock(return_value=(True, "verified"))

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        agent = StateMachineAgent(
            think_func=self.think_func,
            act_func=self.act_func,
            verify_func=self.verify_func,
        )

        result = await agent.execute("test_goal")

        assert isinstance(result, StateMachineResult)
        assert result.success is True
        assert result.final_state == AgentState.COMPLETED
        assert len(result.state_history) > 0

    @pytest.mark.asyncio
    async def test_max_steps_exceeded(self):
        self.verify_func = AsyncMock(return_value=(False, "not verified"))

        agent = StateMachineAgent(
            think_func=self.think_func,
            act_func=self.act_func,
            verify_func=self.verify_func,
            max_steps=3,
        )

        result = await agent.execute("test_goal")

        assert result.success is False
        assert result.final_state == AgentState.FAILED

    @pytest.mark.asyncio
    async def test_state_history_tracking(self):
        agent = StateMachineAgent(
            think_func=self.think_func,
            act_func=self.act_func,
            verify_func=self.verify_func,
        )

        await agent.execute("test_goal")

        assert len(agent.state_history) > 0
        assert all(isinstance(r, StateTransitionRecord) for r in agent.state_history)

    def test_get_state_info(self):
        agent = StateMachineAgent(
            think_func=self.think_func,
            act_func=self.act_func,
        )

        info = agent.get_state_info()

        assert "current_state" in info
        assert "step_count" in info
        assert info["current_state"] == AgentState.IDLE.name


class TestSmartCheckpointManager:
    def setup_method(self):
        self.store = MemoryStateStore()
        self.manager = SmartCheckpointManager(
            strategy=CheckpointStrategy.STEP_BASED,
            checkpoint_store=self.store,
            checkpoint_interval=5,
        )

    @pytest.mark.asyncio
    async def test_create_checkpoint(self):
        checkpoint = await self.manager.create_checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MANUAL,
            state={"key": "value"},
            step_index=1,
        )

        assert checkpoint is not None
        assert checkpoint.execution_id == "exec-1"
        assert checkpoint.checkpoint_type == CheckpointType.MANUAL
        assert checkpoint.step_index == 1

    @pytest.mark.asyncio
    async def test_restore_checkpoint(self):
        checkpoint = await self.manager.create_checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MANUAL,
            state={"test": "data"},
            step_index=5,
        )

        restored = await self.manager.restore_checkpoint(checkpoint.checkpoint_id)

        assert restored is not None
        assert restored["state"] == {"test": "data"}
        assert restored["step_index"] == 5

    @pytest.mark.asyncio
    async def test_checkpoint_not_found(self):
        with pytest.raises(CheckpointNotFoundError):
            await self.manager.restore_checkpoint("nonexistent")

    @pytest.mark.asyncio
    async def test_should_checkpoint_step_based(self):
        assert await self.manager.should_checkpoint(5, AgentState.THINKING, {}) is True
        assert await self.manager.should_checkpoint(3, AgentState.THINKING, {}) is False

    def test_failure_rate_adjustment(self):
        assert self.manager.failure_rate == 0.0

        self.manager.record_failure()
        assert self.manager.failure_rate == 1.0

        self.manager.record_success()
        self.manager.record_success()
        assert self.manager.failure_rate == pytest.approx(1 / 3, rel=0.01)


class TestHierarchicalMemoryManager:
    def setup_method(self):
        self.manager = HierarchicalMemoryManager(
            working_memory_tokens=1000,
            episodic_memory_tokens=5000,
            semantic_memory_tokens=10000,
        )

    @pytest.mark.asyncio
    async def test_add_memory(self):
        memory_id = await self.manager.add_memory(
            content="test content",
            memory_type=MemoryType.CONVERSATION,
            importance=0.8,
            layer=MemoryLayer.WORKING,
        )

        assert memory_id is not None
        entry = await self.manager.get_memory(memory_id)
        assert entry is not None
        assert entry.content == "test content"

    @pytest.mark.asyncio
    async def test_memory_layers(self):
        await self.manager.add_memory(
            content="working",
            memory_type=MemoryType.CONVERSATION,
            layer=MemoryLayer.WORKING,
        )

        await self.manager.add_memory(
            content="episodic",
            memory_type=MemoryType.ACTION,
            layer=MemoryLayer.EPISODIC,
        )

        usage = self.manager.get_layer_usage()

        assert usage["working"]["entry_count"] == 1
        assert usage["episodic"]["entry_count"] == 1

    @pytest.mark.asyncio
    async def test_retrieve_relevant(self):
        await self.manager.add_memory(
            content="The user wants to analyze logs",
            memory_type=MemoryType.CONVERSATION,
            importance=0.9,
        )

        await self.manager.add_memory(
            content="Error occurred in database connection",
            memory_type=MemoryType.ERROR,
            importance=0.8,
        )

        results = await self.manager.retrieve_relevant(
            query="logs error",
            max_tokens=500,
        )

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_delete_memory(self):
        memory_id = await self.manager.add_memory(
            content="to delete",
            memory_type=MemoryType.CONVERSATION,
        )

        assert await self.manager.get_memory(memory_id) is not None

        deleted = await self.manager.delete_memory(memory_id)
        assert deleted is True
        assert await self.manager.get_memory(memory_id) is None


class TestTaskOrchestrator:
    def setup_method(self):
        self.orchestrator = TaskOrchestrator()

    @pytest.mark.asyncio
    async def test_single_task(self):
        async def simple_task():
            return "result"

        task = Task(
            task_id="task-1",
            name="Simple Task",
            execute_func=simple_task,
        )

        self.orchestrator.add_task(task)
        result = await self.orchestrator.execute()

        assert result.success is True
        assert result.completed_tasks == 1

    @pytest.mark.asyncio
    async def test_dependencies(self):
        execution_order = []

        async def task_a():
            execution_order.append("A")
            return "A"

        async def task_b():
            execution_order.append("B")
            return "B"

        self.orchestrator.add_task(
            Task(
                task_id="A",
                name="Task A",
                execute_func=task_a,
            )
        )

        self.orchestrator.add_task(
            Task(
                task_id="B",
                name="Task B",
                execute_func=task_b,
                dependencies=["A"],
            )
        )

        result = await self.orchestrator.execute()

        assert result.success is True
        assert execution_order == ["A", "B"]

    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self):
        self.orchestrator.add_task(
            Task(
                task_id="A",
                name="Task A",
                execute_func=lambda: "A",
                dependencies=["B"],
            )
        )

        self.orchestrator.add_task(
            Task(
                task_id="B",
                name="Task B",
                execute_func=lambda: "B",
                dependencies=["A"],
            )
        )

        with pytest.raises(CircularDependencyError):
            await self.orchestrator.execute()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        call_count = 0

        async def failing_task():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        task = Task(
            task_id="retry-task",
            name="Retry Task",
            execute_func=failing_task,
            retry_config=RetryConfig(
                policy=RetryPolicy.FIXED,
                max_retries=3,
                base_delay=0.1,
            ),
        )

        self.orchestrator.add_task(task)
        result = await self.orchestrator.execute()

        assert result.success is True
        assert call_count == 3


class TestWorkflowBuilder:
    @pytest.mark.asyncio
    async def test_build_workflow(self):
        results = []

        def step1():
            results.append(1)
            return "step1"

        def step2():
            results.append(2)
            return "step2"

        workflow = (
            WorkflowBuilder()
            .task("step1", "Step 1", step1)
            .task("step2", "Step 2", step2, dependencies=["step1"])
            .build()
        )

        result = await workflow.execute()

        assert result.success is True
        assert results == [1, 2]


class TestAgentMetrics:
    def setup_method(self):
        self.metrics = AgentMetrics()

    def test_record_step(self):
        self.metrics.record_step(
            step_index=0,
            state="THINKING",
            duration_ms=100.5,
            success=True,
            tokens_used=100,
        )

        summary = self.metrics.get_summary()
        assert summary["total_steps"] == 1
        assert summary["successful_steps"] == 1

    def test_record_transition(self):
        self.metrics.record_transition(
            from_state="THINKING",
            to_state="ACTING",
            duration_ms=10.5,
            is_valid=True,
        )

        assert len(self.metrics._transition_metrics) == 1

    def test_health_score_calculation(self):
        for i in range(10):
            self.metrics.record_step(
                step_index=i,
                state="THINKING",
                duration_ms=100.0,
                success=True,
                tokens_used=100,
            )

        score = self.metrics.calculate_health_score()

        assert 0 <= score <= 100

    def test_health_status(self):
        assert self.metrics.get_health_status(95) == HealthStatus.EXCELLENT
        assert self.metrics.get_health_status(75) == HealthStatus.GOOD
        assert self.metrics.get_health_status(55) == HealthStatus.FAIR
        assert self.metrics.get_health_status(35) == HealthStatus.POOR
        assert self.metrics.get_health_status(15) == HealthStatus.CRITICAL

    def test_health_report(self):
        self.metrics.record_step(0, "THINKING", 100.0, True, 100)
        self.metrics.record_step(1, "ACTING", 200.0, True, 100)
        self.metrics.record_step(2, "VERIFYING", 50.0, False, 50, error="test error")

        report = self.metrics.get_health_report()

        assert isinstance(report, AgentHealthReport)
        assert report.total_steps == 3
        assert report.successful_steps == 2
        assert report.failed_steps == 1

    def test_reset(self):
        self.metrics.record_step(0, "THINKING", 100.0, True)
        self.metrics.record_transition("THINKING", "ACTING", 10.0)

        self.metrics.reset()

        summary = self.metrics.get_summary()
        assert summary["total_steps"] == 0
        assert len(self.metrics._step_metrics) == 0
        assert len(self.metrics._transition_metrics) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
