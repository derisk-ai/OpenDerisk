"""
Tests for AsyncTaskManager

测试异步任务管理器的核心功能：
- 任务提交与状态管理
- 并发控制
- 等待机制
- 取消操作
- DAG 依赖编排
- 超时处理
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from derisk.agent.core_v2.async_task_manager import (
    AsyncTaskManager,
    AsyncTaskSpec,
    AsyncTaskState,
    AsyncTaskStatus,
)


# ==================== Fixtures ====================


def make_mock_subagent_manager(delay: float = 0.05, success: bool = True, output: str = "done"):
    """创建 Mock SubagentManager"""
    manager = MagicMock()

    async def mock_delegate(**kwargs):
        await asyncio.sleep(delay)
        result = MagicMock()
        result.success = success
        result.output = output
        result.error = None if success else "mock error"
        result.artifacts = {}
        return result

    manager.delegate = AsyncMock(side_effect=mock_delegate)
    return manager


# ==================== 数据模型测试 ====================


class TestAsyncTaskSpec:
    """测试任务规格模型"""

    def test_default_task_id(self):
        """测试自动生成 task_id"""
        spec = AsyncTaskSpec(agent_name="test", task_description="hello")
        assert spec.task_id.startswith("atask_")
        assert len(spec.task_id) == 14  # "atask_" + 8 hex chars

    def test_custom_task_id(self):
        """测试自定义 task_id"""
        spec = AsyncTaskSpec(
            task_id="my_task_1",
            agent_name="test",
            task_description="hello",
        )
        assert spec.task_id == "my_task_1"

    def test_default_values(self):
        """测试默认值"""
        spec = AsyncTaskSpec(agent_name="test", task_description="hello")
        assert spec.timeout == 300
        assert spec.context == {}
        assert spec.depend_on == []


class TestAsyncTaskState:
    """测试任务状态模型"""

    def test_initial_state(self):
        """测试初始状态"""
        spec = AsyncTaskSpec(agent_name="test", task_description="hello")
        state = AsyncTaskState(spec=spec)
        assert state.status == AsyncTaskStatus.PENDING
        assert state.result is None
        assert state.error is None
        assert state.consumed is False

    def test_is_terminal(self):
        """测试终态判断"""
        spec = AsyncTaskSpec(agent_name="test", task_description="hello")
        state = AsyncTaskState(spec=spec, status=AsyncTaskStatus.PENDING)
        assert state.is_terminal() is False

        state.status = AsyncTaskStatus.RUNNING
        assert state.is_terminal() is False

        for terminal in [AsyncTaskStatus.COMPLETED, AsyncTaskStatus.FAILED,
                         AsyncTaskStatus.TIMEOUT, AsyncTaskStatus.CANCELLED]:
            state.status = terminal
            assert state.is_terminal() is True

    def test_to_summary(self):
        """测试摘要生成"""
        spec = AsyncTaskSpec(agent_name="test_agent", task_description="do something")
        state = AsyncTaskState(spec=spec, status=AsyncTaskStatus.COMPLETED, result="all good")
        summary = state.to_summary()
        assert summary["task_id"] == spec.task_id
        assert summary["agent_name"] == "test_agent"
        assert summary["status"] == "completed"
        assert "all good" in summary["result_preview"]


# ==================== AsyncTaskManager 核心测试 ====================


class TestAsyncTaskManager:
    """测试 AsyncTaskManager"""

    @pytest.mark.asyncio
    async def test_spawn_task(self):
        """测试提交任务"""
        mock_mgr = make_mock_subagent_manager()
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(agent_name="agent_a", task_description="task 1")
        task_id = await atm.spawn(spec)

        assert task_id == spec.task_id
        state = atm.get_status(task_id)
        assert state is not None
        assert state.spec.agent_name == "agent_a"

    @pytest.mark.asyncio
    async def test_spawn_duplicate_raises(self):
        """测试重复 task_id 抛异常"""
        mock_mgr = make_mock_subagent_manager()
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(task_id="dup_1", agent_name="a", task_description="t")
        await atm.spawn(spec)

        with pytest.raises(ValueError, match="already exists"):
            await atm.spawn(AsyncTaskSpec(task_id="dup_1", agent_name="b", task_description="t2"))

    @pytest.mark.asyncio
    async def test_task_completes_successfully(self):
        """测试任务成功完成"""
        mock_mgr = make_mock_subagent_manager(delay=0.05, success=True, output="result_ok")
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(agent_name="agent_a", task_description="do work")
        task_id = await atm.spawn(spec)

        # 等待完成
        results = await atm.wait_all([task_id], timeout=5)
        assert len(results) == 1
        assert results[0].status == AsyncTaskStatus.COMPLETED
        assert results[0].result == "result_ok"

    @pytest.mark.asyncio
    async def test_task_failure(self):
        """测试任务失败"""
        mock_mgr = make_mock_subagent_manager(delay=0.05, success=False, output="")
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(agent_name="agent_a", task_description="fail task")
        task_id = await atm.spawn(spec)

        results = await atm.wait_all([task_id], timeout=5)
        assert results[0].status == AsyncTaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_get_all_status(self):
        """测试查询所有状态"""
        mock_mgr = make_mock_subagent_manager(delay=0.5)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="task 1"))
        await atm.spawn(AsyncTaskSpec(task_id="t2", agent_name="b", task_description="task 2"))

        status = atm.get_all_status()
        assert "t1" in status
        assert "t2" in status
        assert status["t1"]["agent_name"] == "a"
        assert status["t2"]["agent_name"] == "b"

    @pytest.mark.asyncio
    async def test_wait_any(self):
        """测试等待任意任务完成"""
        mock_mgr = make_mock_subagent_manager(delay=0.05)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="task 1"))
        await atm.spawn(AsyncTaskSpec(task_id="t2", agent_name="b", task_description="task 2"))

        results = await atm.wait_any(timeout=5)
        assert len(results) >= 1
        assert all(s.is_terminal() for s in results)

    @pytest.mark.asyncio
    async def test_wait_all(self):
        """测试等待全部任务完成"""
        mock_mgr = make_mock_subagent_manager(delay=0.05)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="task 1"))
        await atm.spawn(AsyncTaskSpec(task_id="t2", agent_name="b", task_description="task 2"))

        results = await atm.wait_all(["t1", "t2"], timeout=5)
        assert len(results) == 2
        assert all(s.status == AsyncTaskStatus.COMPLETED for s in results)

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """测试取消任务"""
        mock_mgr = make_mock_subagent_manager(delay=5.0)  # 长时间运行
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(agent_name="slow_agent", task_description="slow")
        task_id = await atm.spawn(spec)

        await asyncio.sleep(0.05)  # 让任务启动
        success = await atm.cancel(task_id)
        assert success is True

        state = atm.get_status(task_id)
        assert state.status == AsyncTaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_completed_task_fails(self):
        """测试取消已完成的任务失败"""
        mock_mgr = make_mock_subagent_manager(delay=0.01)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(agent_name="a", task_description="quick")
        task_id = await atm.spawn(spec)
        await atm.wait_all([task_id], timeout=5)

        success = await atm.cancel(task_id)
        assert success is False

    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        """测试并发限制"""
        running_count = 0
        max_running = 0

        original_manager = make_mock_subagent_manager(delay=0.1)

        async def counting_delegate(**kwargs):
            nonlocal running_count, max_running
            running_count += 1
            max_running = max(max_running, running_count)
            await asyncio.sleep(0.1)
            running_count -= 1
            result = MagicMock()
            result.success = True
            result.output = "ok"
            result.error = None
            result.artifacts = {}
            return result

        original_manager.delegate = AsyncMock(side_effect=counting_delegate)

        atm = AsyncTaskManager(
            subagent_manager=original_manager,
            max_concurrent=2,
            parent_session_id="test",
        )

        # 提交 5 个任务
        task_ids = []
        for i in range(5):
            tid = await atm.spawn(
                AsyncTaskSpec(task_id=f"t{i}", agent_name="a", task_description=f"task {i}")
            )
            task_ids.append(tid)

        await atm.wait_all(task_ids, timeout=10)

        # 最大同时运行不超过 2
        assert max_running <= 2

    @pytest.mark.asyncio
    async def test_dependency_chain(self):
        """测试 DAG 依赖编排"""
        execution_order = []

        mock_mgr = MagicMock()

        async def ordered_delegate(**kwargs):
            task_name = kwargs.get("task", "unknown")
            execution_order.append(task_name)
            await asyncio.sleep(0.05)
            result = MagicMock()
            result.success = True
            result.output = f"done: {task_name}"
            result.error = None
            result.artifacts = {}
            return result

        mock_mgr.delegate = AsyncMock(side_effect=ordered_delegate)

        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        # t1 无依赖，t2 依赖 t1
        await atm.spawn(
            AsyncTaskSpec(task_id="t1", agent_name="a", task_description="step1")
        )
        await atm.spawn(
            AsyncTaskSpec(
                task_id="t2", agent_name="a", task_description="step2",
                depend_on=["t1"],
            )
        )

        await atm.wait_all(["t1", "t2"], timeout=10)

        # t1 必须在 t2 之前执行
        assert execution_order.index("step1") < execution_order.index("step2")

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """测试任务超时"""
        mock_mgr = make_mock_subagent_manager(delay=10.0)  # 超长延迟
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        spec = AsyncTaskSpec(
            agent_name="slow", task_description="will timeout", timeout=1
        )
        task_id = await atm.spawn(spec)

        results = await atm.wait_all([task_id], timeout=5)
        assert results[0].status == AsyncTaskStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_get_completed_results_consume(self):
        """测试结果消费机制"""
        mock_mgr = make_mock_subagent_manager(delay=0.01)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="t"))

        # wait_any 获取并消费
        results = await atm.wait_any(timeout=5)
        assert len(results) == 1

        # 第二次获取（已消费）
        results = atm.get_completed_results(consume=True)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_has_pending_tasks(self):
        """测试是否有待处理任务"""
        mock_mgr = make_mock_subagent_manager(delay=0.5)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        assert atm.has_pending_tasks() is False

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="t"))
        assert atm.has_pending_tasks() is True

    @pytest.mark.asyncio
    async def test_format_status_table(self):
        """测试状态表格格式化"""
        mock_mgr = make_mock_subagent_manager(delay=0.01)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="test_agent", task_description="hello"))
        await atm.wait_all(["t1"], timeout=5)

        table = atm.format_status_table()
        assert "t1" in table
        assert "test_agent" in table
        assert "completed" in table

    @pytest.mark.asyncio
    async def test_format_notifications(self):
        """测试通知格式化"""
        mock_mgr = make_mock_subagent_manager(delay=0.01, output="analysis result")
        atm = AsyncTaskManager(subagent_manager=mock_mgr, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="analyzer", task_description="analyze"))

        # 使用 get_completed_results 而不是 wait_all（wait_all 会消费结果）
        await asyncio.sleep(0.2)  # 等待任务完成
        completed = atm.get_completed_results(consume=False)
        assert len(completed) >= 1

        notification = atm.format_notifications(completed)
        assert "[异步任务完成通知]" in notification
        assert "analysis result" in notification

    @pytest.mark.asyncio
    async def test_statistics(self):
        """测试统计信息"""
        mock_mgr = make_mock_subagent_manager(delay=0.01)
        atm = AsyncTaskManager(subagent_manager=mock_mgr, max_concurrent=3, parent_session_id="test")

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="t"))
        await atm.wait_all(["t1"], timeout=5)

        stats = atm.get_statistics()
        assert stats["total_spawned"] == 1
        assert stats["total_completed"] == 1
        assert stats["max_concurrent"] == 3

    @pytest.mark.asyncio
    async def test_on_complete_callback(self):
        """测试完成回调"""
        callback_results = []

        async def on_complete(state):
            callback_results.append(state.spec.task_id)

        mock_mgr = make_mock_subagent_manager(delay=0.01)
        atm = AsyncTaskManager(
            subagent_manager=mock_mgr,
            parent_session_id="test",
            on_task_complete=on_complete,
        )

        await atm.spawn(AsyncTaskSpec(task_id="t1", agent_name="a", task_description="t"))
        await atm.wait_all(["t1"], timeout=5)

        assert "t1" in callback_results
