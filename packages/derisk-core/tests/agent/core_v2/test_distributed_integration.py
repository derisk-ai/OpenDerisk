"""
Integration Tests for Distributed Execution Architecture (v7)

Tests for:
- Worker Process Pool
- Monitoring Dashboard
- Database Storage
- Agent Application with distributed execution
"""

import asyncio
import pytest
import tempfile
import os
from datetime import datetime
from pathlib import Path


class TestWorkerPool:
    """Worker Process Pool Tests"""

    @pytest.mark.asyncio
    async def test_worker_pool_creation(self):
        """Test creating a worker pool"""
        from derisk.agent.core_v2.worker_pool import (
            WorkerPool,
            WorkerPoolConfig,
            create_worker_pool,
        )

        # Create with config
        config = WorkerPoolConfig(
            min_workers=2,
            max_workers=5,
            max_tasks_per_worker=10,
        )
        pool = WorkerPool(config)
        assert pool is not None
        assert pool.config.min_workers == 2
        assert pool.config.max_workers == 5

        # Create with convenience function
        pool2 = create_worker_pool(min_workers=1, max_workers=3)
        assert pool2 is not None

    @pytest.mark.asyncio
    async def test_worker_pool_task_submission(self):
        """Test submitting tasks to worker pool"""
        from derisk.agent.core_v2.worker_pool import create_worker_pool

        pool = create_worker_pool(min_workers=1, max_workers=2)

        # Start pool
        await pool.start()

        try:
            # Submit a simple task
            def simple_task(x):
                return x * 2

            task_id = await pool.submit_task(simple_task, 5)
            assert task_id is not None
            assert task_id.startswith("task-")

            # Get result
            result = await pool.get_result(task_id, timeout=30)
            assert result == 10

        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_worker_pool_stats(self):
        """Test worker pool statistics"""
        from derisk.agent.core_v2.worker_pool import create_worker_pool

        pool = create_worker_pool(min_workers=2, max_workers=4)
        await pool.start()

        try:
            stats = await pool.get_stats()
            assert "total_workers" in stats
            assert "active_workers" in stats
            assert stats["total_workers"] == 2

        finally:
            await pool.stop()


class TestMonitoringDashboard:
    """Monitoring Dashboard Tests"""

    @pytest.mark.asyncio
    async def test_dashboard_creation(self):
        """Test creating a monitoring dashboard"""
        from derisk.agent.core_v2.monitoring_dashboard import (
            MonitoringDashboard,
            get_dashboard,
        )

        # Create dashboard
        dashboard = MonitoringDashboard()
        assert dashboard is not None

        # Get global instance
        global_dashboard = get_dashboard()
        assert global_dashboard is not None

    @pytest.mark.asyncio
    async def test_task_tracking(self):
        """Test task tracking in dashboard"""
        from derisk.agent.core_v2.monitoring_dashboard import MonitoringDashboard

        dashboard = MonitoringDashboard()

        # Create task
        task = await dashboard.create_task("test-task-001", "Test Goal")
        assert task.task_id == "test-task-001"
        assert task.goal == "Test Goal"
        assert task.status == "created"

        # Update progress
        updated = await dashboard.update_task_progress(
            "test-task-001",
            current_step=5,
            total_steps=10,
            status="running",
        )
        assert updated.current_step == 5
        assert updated.total_steps == 10
        assert updated.progress_percent == 50.0

        # Complete task
        completed = await dashboard.complete_task("test-task-001", success=True)
        assert completed.status == "completed"

    @pytest.mark.asyncio
    async def test_subagent_tracking(self):
        """Test subagent tracking in dashboard"""
        from derisk.agent.core_v2.monitoring_dashboard import MonitoringDashboard

        dashboard = MonitoringDashboard()

        # Create task first
        await dashboard.create_task("task-001", "Main Task")

        # Create subagent
        subagent = await dashboard.create_subagent(
            "conv-001",
            "analyzer",
            "task-001",
        )
        assert subagent.conversation_id == "conv-001"
        assert subagent.subagent_name == "analyzer"
        assert subagent.parent_task_id == "task-001"

        # Update subagent
        updated = await dashboard.update_subagent(
            "conv-001",
            status="running",
        )
        assert updated.status == "running"

    @pytest.mark.asyncio
    async def test_alert_management(self):
        """Test alert management in dashboard"""
        from derisk.agent.core_v2.monitoring_dashboard import MonitoringDashboard

        dashboard = MonitoringDashboard()

        # Create alert
        alert = await dashboard.create_alert(
            "memory_high",
            "warning",
            "Memory usage exceeds 80%",
        )
        assert alert.alert_type == "memory_high"
        assert alert.severity == "warning"
        assert not alert.resolved

        # Resolve alert
        success = await dashboard.resolve_alert(alert.alert_id)
        assert success

        # Check resolved
        alerts = await dashboard.get_alerts(unresolved_only=True)
        assert alert.alert_id not in [a.alert_id for a in alerts]

    @pytest.mark.asyncio
    async def test_dashboard_stats(self):
        """Test dashboard statistics"""
        from derisk.agent.core_v2.monitoring_dashboard import MonitoringDashboard

        dashboard = MonitoringDashboard()

        # Create some tasks
        await dashboard.create_task("task-1", "Task 1")
        await dashboard.create_task("task-2", "Task 2")
        await dashboard.complete_task("task-1", success=True)

        # Get stats
        stats = await dashboard.get_stats()
        assert stats["tasks"]["total_created"] >= 2
        assert stats["tasks"]["total_completed"] >= 1

    @pytest.mark.asyncio
    async def test_event_recording(self):
        """Test event recording"""
        from derisk.agent.core_v2.monitoring_dashboard import (
            MonitoringDashboard,
            DashboardEventType,
        )

        dashboard = MonitoringDashboard()

        # Record event
        event = await dashboard.record_event(
            DashboardEventType.TASK_CREATED,
            task_id="test-task",
            data={"goal": "Test"},
        )
        assert event.event_type == DashboardEventType.TASK_CREATED
        assert event.task_id == "test-task"

        # Get events
        events = await dashboard.get_events(limit=10)
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_dashboard_data(self):
        """Test getting complete dashboard data"""
        from derisk.agent.core_v2.monitoring_dashboard import MonitoringDashboard

        dashboard = MonitoringDashboard()

        # Create some data
        await dashboard.create_task("task-1", "Task 1")
        await dashboard.update_worker("worker-1", status="idle", pid=12345)

        # Get dashboard data
        data = await dashboard.get_dashboard_data()
        assert "tasks" in data
        assert "workers" in data
        assert "alerts" in data
        assert "stats" in data
        assert "timestamp" in data


class TestDatabaseStorage:
    """Database Storage Tests"""

    @pytest.mark.asyncio
    async def test_memory_storage(self):
        """Test memory storage backend"""
        from derisk.agent.core_v2.distributed_execution import (
            MemoryStateStorage,
        )

        storage = MemoryStateStorage()

        # Save
        success = await storage.save("test-key", {"value": "test"})
        assert success

        # Load
        data = await storage.load("test-key")
        assert data == {"value": "test"}

        # Exists
        exists = await storage.exists("test-key")
        assert exists

        # Delete
        success = await storage.delete("test-key")
        assert success

        # Not exists
        exists = await storage.exists("test-key")
        assert not exists

    @pytest.mark.asyncio
    async def test_file_storage(self):
        """Test file storage backend"""
        from derisk.agent.core_v2.distributed_execution import (
            FileStateStorage,
            StorageConfig,
            StorageBackendType,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config = StorageConfig(
                backend_type=StorageBackendType.FILE,
                base_dir=tmpdir,
            )
            storage = FileStateStorage(config)

            # Save
            success = await storage.save("test-key", {"value": "test"})
            assert success

            # Load
            data = await storage.load("test-key")
            assert data == {"value": "test"}

            # List keys
            keys = await storage.list_keys("test")
            assert "test-key" in keys

    @pytest.mark.asyncio
    async def test_sqlite_storage(self):
        """Test SQLite storage backend"""
        from derisk.agent.core_v2.database_storage import SQLiteStateStorage
        from derisk.agent.core_v2.distributed_execution import StorageConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = StorageConfig(database_url=db_path)
            storage = SQLiteStateStorage(config)

            # Save
            success = await storage.save("test-key", {"value": "test"})
            assert success

            # Load
            data = await storage.load("test-key")
            assert data == {"value": "test"}

    @pytest.mark.asyncio
    async def test_storage_factory(self):
        """Test storage factory"""
        from derisk.agent.core_v2.distributed_execution import (
            StateStorageFactory,
            StorageConfig,
            StorageBackendType,
        )

        # Memory storage
        config = StorageConfig(backend_type=StorageBackendType.MEMORY)
        storage = StateStorageFactory.create(config)
        assert storage is not None

        # File storage
        with tempfile.TemporaryDirectory() as tmpdir:
            config = StorageConfig(
                backend_type=StorageBackendType.FILE,
                base_dir=tmpdir,
            )
            storage = StateStorageFactory.create(config)
            assert storage is not None

        # SQLite storage (via DATABASE backend)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = StorageConfig(
                backend_type=StorageBackendType.DATABASE,
                database_url=db_path,
            )
            storage = StateStorageFactory.create(config)
            assert storage is not None

    @pytest.mark.asyncio
    async def test_convenience_methods(self):
        """Test convenience factory methods"""
        from derisk.agent.core_v2.distributed_execution import StateStorageFactory

        # Default
        storage = StateStorageFactory.create_default()
        assert storage is not None

        # File
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StateStorageFactory.create_file(tmpdir)
            assert storage is not None

        # Database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = StateStorageFactory.create_database(db_path)
            assert storage is not None


class TestAgentApplicationIntegration:
    """Agent Application Integration Tests"""

    @pytest.mark.asyncio
    async def test_application_creation(self):
        """Test creating an agent application"""
        from derisk.agent.core_v2.agent_application import (
            AgentApplication,
            SubagentBinding,
        )

        # Create mock agent class
        class MockAgent:
            def __init__(self):
                self.call_subagent = None
                self.get_subagent_progress = None

            async def run(self, goal):
                return f"Completed: {goal}"

        class MockSubagent:
            async def run(self, task, context=None):
                return f"Subagent result: {task}"

        # Create application
        app = AgentApplication(
            app_id="test-app",
            name="Test Application",
            main_agent_class=MockAgent,
        )

        # Bind subagent
        app.bind_subagent(
            name="worker",
            agent_class=MockSubagent,
            description="Test worker agent",
            max_instances=5,
        )

        assert app.app_id == "test-app"
        assert "worker" in app.subagent_bindings

    @pytest.mark.asyncio
    async def test_application_runner(self):
        """Test running an agent application"""
        from derisk.agent.core_v2.agent_application import (
            AgentApplication,
            AgentApplicationRunner,
        )

        class SimpleAgent:
            def __init__(self):
                self.call_subagent = None
                self.get_subagent_progress = None

            async def run(self, goal):
                return f"Processed: {goal}"

        # Create and run
        app = AgentApplication(
            app_id="simple-app",
            name="Simple App",
            main_agent_class=SimpleAgent,
            storage_backend="memory",
        )

        runner = AgentApplicationRunner(app)
        await runner.initialize()

        result = await runner.run(goal="Test Goal")

        assert result["success"]
        assert "Test Goal" in result["output"]


class TestDistributedTaskExecutor:
    """Distributed Task Executor Tests"""

    @pytest.mark.asyncio
    async def test_executor_creation(self):
        """Test creating a distributed task executor"""
        from derisk.agent.core_v2.distributed_execution import (
            DistributedTaskExecutor,
            StorageConfig,
            StorageBackendType,
        )

        config = StorageConfig(backend_type=StorageBackendType.MEMORY)
        executor = DistributedTaskExecutor(storage_config=config)

        assert executor is not None
        assert executor.storage is not None
        assert executor.sleep_manager is not None
        assert executor.conversation_manager is not None

    @pytest.mark.asyncio
    async def test_sleep_wakeup_mechanism(self):
        """Test agent sleep/wakeup mechanism"""
        from derisk.agent.core_v2.distributed_execution import (
            AgentSleepManager,
            MemoryStateStorage,
        )

        storage = MemoryStateStorage()
        sleep_manager = AgentSleepManager(storage=storage)

        # Sleep
        context = await sleep_manager.sleep(
            task_id="task-001",
            reason="Waiting for subtasks",
            wait_for_subtasks=["subtask-1", "subtask-2"],
        )

        assert context.task_id == "task-001"
        assert len(context.wake_conditions) == 2

        # Check sleep status
        status = await sleep_manager.get_sleep_status("task-001")
        assert status is not None

        # Wakeup (first subtask)
        await sleep_manager.wakeup(
            task_id="task-001",
            wakeup_reason="subtask_completed",
            triggered_by="subtask-1",
        )

        # Should still be sleeping (one more subtask)
        status = await sleep_manager.get_sleep_status("task-001")
        assert status is not None

    @pytest.mark.asyncio
    async def test_subagent_conversation(self):
        """Test subagent conversation management"""
        from derisk.agent.core_v2.distributed_execution import (
            SubagentConversationManager,
            AgentSleepManager,
            MemoryStateStorage,
        )

        storage = MemoryStateStorage()
        sleep_manager = AgentSleepManager(storage=storage)
        conv_manager = SubagentConversationManager(
            storage=storage,
            sleep_manager=sleep_manager,
        )

        # Create conversation
        conv = await conv_manager.create_conversation(
            parent_task_id="task-001",
            subagent_name="analyzer",
            initial_context={"data": "test"},
        )

        assert conv.conversation_id is not None
        assert conv.parent_task_id == "task-001"
        assert conv.subagent_name == "analyzer"

        # Add message
        success = await conv_manager.add_message(
            conv.conversation_id,
            "user",
            "Test message",
        )
        assert success

        # Get progress
        progress = await conv_manager.get_conversation_progress("task-001")
        assert progress["total"] >= 1


class TestFullIntegration:
    """Full Integration Tests"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete workflow with all components"""
        from derisk.agent.core_v2.agent_application import (
            AgentApplication,
            AgentApplicationRunner,
        )
        from derisk.agent.core_v2.monitoring_dashboard import MonitoringDashboard
        from derisk.agent.core_v2.distributed_execution import (
            StorageConfig,
            StorageBackendType,
        )

        # Setup dashboard
        dashboard = MonitoringDashboard()

        # Create agent
        class MonitoredAgent:
            def __init__(self):
                self.call_subagent = None
                self.get_subagent_progress = None
                self.dashboard = None

            async def run(self, goal):
                if self.dashboard:
                    await self.dashboard.update_task_progress(
                        "monitored-task",
                        current_step=1,
                        total_steps=3,
                        status="running",
                    )
                return f"Processed: {goal}"

        # Create application
        app = AgentApplication(
            app_id="monitored-app",
            name="Monitored App",
            main_agent_class=MonitoredAgent,
            storage_backend="memory",
        )

        # Create task in dashboard
        await dashboard.create_task("monitored-task", "Monitored Task")

        # Run application
        runner = AgentApplicationRunner(app)
        await runner.initialize()

        # Inject dashboard
        if runner.runtime_context.main_agent:
            runner.runtime_context.main_agent.dashboard = dashboard

        result = await runner.run(goal="Test Goal")

        # Check result
        assert result["success"]

        # Check dashboard was updated
        task = await dashboard.get_task("monitored-task")
        assert task is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
