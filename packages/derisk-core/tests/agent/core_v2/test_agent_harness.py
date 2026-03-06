"""
AgentHarness测试用例

测试超长任务的上下文管理和执行框架
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from derisk.agent.core_v2.agent_harness import (
    ExecutionState,
    CheckpointType,
    ContextLayer,
    ExecutionContext,
    Checkpoint,
    ExecutionSnapshot,
    FileStateStore,
    MemoryStateStore,
    CheckpointManager,
    CircuitBreaker,
    TaskQueue,
    StateCompressor,
    AgentHarness,
)


class TestExecutionContext:
    """分层上下文测试"""
    
    def test_create_context(self):
        context = ExecutionContext(
            system_layer={"agent_name": "test"},
            task_layer={"current_task": "research"},
            tool_layer={"available_tools": ["bash", "read"]},
            memory_layer={"history": []},
            temporary_layer={"cache": {}}
        )
        
        assert context.system_layer["agent_name"] == "test"
        assert context.task_layer["current_task"] == "research"
    
    def test_get_layer(self):
        context = ExecutionContext()
        context.set_layer(ContextLayer.SYSTEM, {"name": "agent"})
        
        system = context.get_layer(ContextLayer.SYSTEM)
        assert system["name"] == "agent"
    
    def test_merge_all(self):
        context = ExecutionContext(
            system_layer={"a": 1},
            task_layer={"b": 2},
            tool_layer={"c": 3}
        )
        
        merged = context.merge_all()
        assert merged["a"] == 1
        assert merged["b"] == 2
        assert merged["c"] == 3
    
    def test_serialization(self):
        context = ExecutionContext(
            system_layer={"name": "test"},
            task_layer={"task": "run"}
        )
        
        data = context.to_dict()
        restored = ExecutionContext.from_dict(data)
        
        assert restored.system_layer["name"] == "test"
        assert restored.task_layer["task"] == "run"


class TestCheckpoint:
    """检查点测试"""
    
    def test_create_checkpoint(self):
        checkpoint = Checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MANUAL,
            state={"step": 5},
            message="测试检查点"
        )
        
        assert checkpoint.execution_id == "exec-1"
        assert checkpoint.checkpoint_type == CheckpointType.MANUAL
        assert checkpoint.state["step"] == 5
    
    def test_checksum(self):
        checkpoint = Checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.AUTOMATIC,
            state={"key": "value"},
            step_index=10
        )
        
        checksum1 = checkpoint.compute_checksum()
        checksum2 = checkpoint.compute_checksum()
        
        assert checksum1 == checksum2
        
        checkpoint.state["key"] = "new_value"
        checksum3 = checkpoint.compute_checksum()
        
        assert checksum1 != checksum3


class TestCheckpointManager:
    """检查点管理器测试"""
    
    @pytest.fixture
    def manager(self):
        store = MemoryStateStore()
        return CheckpointManager(store, auto_checkpoint_interval=5)
    
    @pytest.mark.asyncio
    async def test_create_checkpoint(self, manager):
        checkpoint = await manager.create_checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MANUAL,
            state={"step": 1}
        )
        
        assert checkpoint.execution_id == "exec-1"
        assert checkpoint.checkpoint_id is not None
    
    @pytest.mark.asyncio
    async def test_should_auto_checkpoint(self, manager):
        assert await manager.should_auto_checkpoint("exec-1", 3) is False
        assert await manager.should_auto_checkpoint("exec-1", 5) is True
        assert await manager.should_auto_checkpoint("exec-1", 8) is False
        assert await manager.should_auto_checkpoint("exec-1", 10) is True
    
    @pytest.mark.asyncio
    async def test_get_checkpoint(self, manager):
        created = await manager.create_checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MANUAL,
            state={"step": 1}
        )
        
        retrieved = await manager.get_checkpoint(created.checkpoint_id)
        
        assert retrieved is not None
        assert retrieved.checkpoint_id == created.checkpoint_id
    
    @pytest.mark.asyncio
    async def test_restore_checkpoint(self, manager):
        checkpoint = await manager.create_checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MILESTONE,
            state={"step": 10, "data": "important"},
            step_index=10
        )
        
        restored = await manager.restore_checkpoint(checkpoint.checkpoint_id)
        
        assert restored is not None
        assert restored["state"]["step"] == 10
        assert restored["step_index"] == 10
    
    @pytest.mark.asyncio
    async def test_list_checkpoints(self, manager):
        await manager.create_checkpoint("exec-1", CheckpointType.MANUAL, {"step": 1})
        await manager.create_checkpoint("exec-1", CheckpointType.AUTOMATIC, {"step": 2})
        await manager.create_checkpoint("exec-2", CheckpointType.MANUAL, {"step": 1})
        
        checkpoints = await manager.list_checkpoints("exec-1")
        
        assert len(checkpoints) == 2


class TestCircuitBreaker:
    """熔断器测试"""
    
    def test_closed_state(self):
        breaker = CircuitBreaker(failure_threshold=3)
        
        assert breaker.state == "closed"
        assert breaker.can_execute() is True
    
    def test_open_after_failures(self):
        breaker = CircuitBreaker(failure_threshold=3)
        
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "closed"
        
        breaker.record_failure()
        assert breaker.state == "open"
        assert breaker.can_execute() is False
    
    def test_half_open_recovery(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
        
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "open"
        
        breaker._last_failure_time = datetime(2020, 1, 1)
        
        assert breaker.can_execute() is True
        assert breaker.state == "half_open"
        
        breaker.record_success()
        assert breaker.state == "closed"
    
    def test_success_resets_failures(self):
        breaker = CircuitBreaker(failure_threshold=3)
        
        breaker.record_failure()
        breaker.record_failure()
        assert breaker._failure_count == 2
        
        breaker.record_success()
        assert breaker._failure_count == 0


class TestTaskQueue:
    """任务队列测试"""
    
    @pytest.fixture
    def queue(self):
        return TaskQueue(max_size=100)
    
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue):
        await queue.enqueue("task-1", {"action": "test"}, priority=1)
        
        task = await queue.dequeue()
        
        assert task is not None
        assert task["task_id"] == "task-1"
        assert task["data"]["action"] == "test"
    
    @pytest.mark.asyncio
    async def test_priority_order(self, queue):
        await queue.enqueue("low", {"value": 1}, priority=10)
        await queue.enqueue("high", {"value": 2}, priority=1)
        await queue.enqueue("medium", {"value": 3}, priority=5)
        
        task1 = await queue.dequeue()
        task2 = await queue.dequeue()
        task3 = await queue.dequeue()
        
        assert task1["task_id"] == "high"
        assert task2["task_id"] == "medium"
        assert task3["task_id"] == "low"
    
    @pytest.mark.asyncio
    async def test_complete_task(self, queue):
        await queue.enqueue("task-1", {"action": "test"})
        task = await queue.dequeue()
        
        await queue.complete(task["task_id"], result="done")
        
        assert task["task_id"] in queue._completed
        assert queue._completed[task["task_id"]]["result"] == "done"
    
    @pytest.mark.asyncio
    async def test_fail_and_retry(self, queue):
        await queue.enqueue("task-1", {"action": "test"}, max_retries=2)
        task = await queue.dequeue()
        
        await queue.fail(task["task_id"], "error", retry=True)
        
        assert task["task_id"] in queue._pending
        assert queue._pending[task["task_id"]]["retry_count"] == 1
    
    @pytest.mark.asyncio
    async def test_fail_no_more_retries(self, queue):
        await queue.enqueue("task-1", {"action": "test"}, max_retries=1)
        task = await queue.dequeue()
        
        await queue.fail(task["task_id"], "error", retry=True)
        
        new_task = await queue.dequeue()
        await queue.fail(new_task["task_id"], "error", retry=True)
        
        assert new_task["task_id"] in queue._failed


class TestStateCompressor:
    """状态压缩器测试"""
    
    def test_compress_list(self):
        compressor = StateCompressor()
        
        items = [{"step": i} for i in range(100)]
        compressed = compressor._compress_list(items, 20)
        
        assert len(compressed) == 20
        assert compressed[0]["step"] == 80
    
    @pytest.mark.asyncio
    async def test_compress_messages(self):
        compressor = StateCompressor(max_messages=10)
        
        messages = [
            {"role": "user", "content": f"message {i}"}
            for i in range(50)
        ]
        
        compressed = await compressor._compress_messages(messages)
        
        assert len(compressed) <= 10
    
    @pytest.mark.asyncio
    async def test_compress_snapshot(self):
        compressor = StateCompressor(
            max_messages=10,
            max_tool_history=5,
            max_decision_history=5
        )
        
        snapshot = ExecutionSnapshot(
            execution_id="exec-1",
            agent_name="test",
            status=ExecutionState.RUNNING,
            messages=[{"role": "user", "content": str(i)} for i in range(100)],
            tool_history=[{"tool": f"tool-{i}"} for i in range(50)],
            decision_history=[{"decision": i} for i in range(50)]
        )
        
        compressed = await compressor.compress(snapshot)
        
        assert len(compressed.messages) <= 10
        assert len(compressed.tool_history) <= 5
        assert len(compressed.decision_history) <= 5


class TestAgentHarness:
    """Agent Harness完整测试"""
    
    @pytest.fixture
    def mock_agent(self):
        agent = Mock()
        agent.info = Mock()
        agent.info.name = "test-agent"
        return agent
    
    @pytest.fixture
    def harness(self, mock_agent):
        return AgentHarness(
            agent=mock_agent,
            state_store=MemoryStateStore(),
            checkpoint_interval=5
        )
    
    @pytest.mark.asyncio
    async def test_start_execution(self, harness):
        execution_id = await harness.start_execution("测试任务", metadata={"priority": "high"})
        
        assert execution_id is not None
        
        snapshot = harness.get_execution(execution_id)
        assert snapshot is not None
        assert snapshot.status == ExecutionState.RUNNING or snapshot.status == ExecutionState.COMPLETED
    
    def test_harness_stats(self, harness):
        stats = harness.get_stats()
        
        assert "active_executions" in stats
        assert "circuit_breaker" in stats
        assert "task_queue" in stats
    
    @pytest.mark.asyncio
    async def test_pause_resume(self, harness):
        execution_id = await harness.start_execution("测试任务")
        
        await harness.pause_execution(execution_id)
        
        snapshot = harness.get_execution(execution_id)
        if snapshot:
            assert snapshot.status == ExecutionState.PAUSED
        
        await harness.resume_execution(execution_id)
        
        assert execution_id not in harness._paused_executions
    
    @pytest.mark.asyncio
    async def test_cancel_execution(self, harness):
        execution_id = await harness.start_execution("测试任务")
        
        await harness.cancel_execution(execution_id)
        
        snapshot = harness.get_execution(execution_id)
        assert snapshot.status == ExecutionState.CANCELLED
    
    @pytest.mark.asyncio
    async def test_list_executions(self, harness):
        await harness.start_execution("任务1")
        await harness.start_execution("任务2")
        
        executions = await harness.list_executions()
        
        assert len(executions) >= 2


class TestFileStateStore:
    """文件状态存储测试"""
    
    @pytest.fixture
    def store(self, tmp_path):
        return FileStateStore(base_dir=str(tmp_path / ".agent_state"))
    
    @pytest.mark.asyncio
    async def test_save_load(self, store):
        data = {"key": "value", "number": 123}
        
        await store.save("test-key", data)
        loaded = await store.load("test-key")
        
        assert loaded["key"] == "value"
        assert loaded["number"] == 123
    
    @pytest.mark.asyncio
    async def test_delete(self, store):
        await store.save("test-key", {"data": "test"})
        
        await store.delete("test-key")
        loaded = await store.load("test-key")
        
        assert loaded is None
    
    @pytest.mark.asyncio
    async def test_list_keys(self, store):
        await store.save("prefix-1", {"data": 1})
        await store.save("prefix-2", {"data": 2})
        await store.save("other-1", {"data": 3})
        
        keys = await store.list_keys("prefix-")
        
        assert len(keys) == 2


class TestLongRunningTaskSimulation:
    """超长任务模拟测试"""
    
    @pytest.mark.asyncio
    async def test_checkpoint_milestones(self):
        store = MemoryStateStore()
        manager = CheckpointManager(store, auto_checkpoint_interval=10)
        
        execution_id = "long-task"
        
        for step in range(1, 101):
            if await manager.should_auto_checkpoint(execution_id, step):
                await manager.create_checkpoint(
                    execution_id=execution_id,
                    checkpoint_type=CheckpointType.AUTOMATIC,
                    state={"step": step, "progress": step / 100},
                    step_index=step
                )
        
        checkpoints = await manager.list_checkpoints(execution_id)
        
        assert len(checkpoints) >= 9
    
    @pytest.mark.asyncio
    async def test_context_layered_management(self):
        context = ExecutionContext(
            system_layer={"agent_version": "2.0", "model": "gpt-4"},
            task_layer={"current_task": "research", "queries": ["q1", "q2"]},
            tool_layer={"tools": ["search", "read"], "active_tool": None},
            memory_layer={"messages": []},
            temporary_layer={}
        )
        
        for i in range(100):
            context.temporary_layer[f"temp_{i}"] = f"value_{i}"
            
            if i % 10 == 0:
                context.memory_layer[f"milestone_{i//10}"] = f"checkpoint at {i}"
        
        assert len(context.temporary_layer) == 100
        assert len(context.memory_layer) == 10
        
        context.temporary_layer.clear()
        
        assert len(context.temporary_layer) == 0
        assert len(context.memory_layer) == 10
    
    @pytest.mark.asyncio
    async def test_state_recovery_simulation(self):
        store = MemoryStateStore()
        manager = CheckpointManager(store)
        
        execution_id = "recovery-test"
        
        cp1 = await manager.create_checkpoint(
            execution_id=execution_id,
            checkpoint_type=CheckpointType.MILESTONE,
            state={"step": 50, "important_data": "saved"},
            step_index=50,
            message="里程碑检查点"
        )
        
        restored = await manager.restore_checkpoint(cp1.checkpoint_id)
        
        assert restored["state"]["step"] == 50
        assert restored["state"]["important_data"] == "saved"
        assert restored["step_index"] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])