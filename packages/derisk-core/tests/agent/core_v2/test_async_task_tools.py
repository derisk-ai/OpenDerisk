"""
Tests for Async Task Tools

测试 4 个异步任务 Tool 的执行逻辑
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from derisk.agent.core_v2.async_task_manager import (
    AsyncTaskManager,
    AsyncTaskSpec,
    AsyncTaskState,
    AsyncTaskStatus,
)
from derisk.agent.tools.builtin.async_task.async_task_tools import (
    SpawnAgentTaskTool,
    CheckTasksTool,
    WaitTasksTool,
    CancelTaskTool,
)


# ==================== Fixtures ====================


def make_mock_manager():
    """创建 Mock AsyncTaskManager"""
    manager = MagicMock(spec=AsyncTaskManager)
    manager.spawn = AsyncMock(return_value="atask_abc12345")
    manager.get_all_status.return_value = {
        "atask_abc12345": {
            "task_id": "atask_abc12345",
            "agent_name": "test_agent",
            "description": "test task",
            "status": "running",
            "elapsed": 5.0,
            "result_preview": None,
            "error": None,
        }
    }
    manager.format_status_table.return_value = "  [⟳] atask_abc12345 (test_agent): running"
    manager.format_results.return_value = "## Task: atask_abc12345\n- Status: completed\n- Result: done"
    manager.cancel = AsyncMock(return_value=True)

    # wait_any / wait_all 返回
    completed_state = MagicMock(spec=AsyncTaskState)
    completed_state.spec = MagicMock()
    completed_state.spec.task_id = "atask_abc12345"
    completed_state.spec.agent_name = "test_agent"
    completed_state.status = AsyncTaskStatus.COMPLETED
    completed_state.result = "task done"
    completed_state.error = None
    completed_state.artifacts = {}
    completed_state.is_terminal.return_value = True

    manager.wait_any = AsyncMock(return_value=[completed_state])
    manager.wait_all = AsyncMock(return_value=[completed_state])

    return manager


def make_mock_context(manager):
    """创建带 manager 的 Mock ToolContext"""
    context = MagicMock()
    context.get_resource.return_value = manager
    return context


# ==================== SpawnAgentTaskTool ====================


class TestSpawnAgentTaskTool:
    """测试 spawn_agent_task 工具"""

    @pytest.mark.asyncio
    async def test_spawn_success(self):
        """测试成功提交任务"""
        manager = make_mock_manager()
        tool = SpawnAgentTaskTool(async_task_manager=manager)

        result = await tool.execute(
            {"agent_name": "code_reviewer", "task": "Review the auth module"},
        )

        assert result.success is True
        assert "atask_abc12345" in result.output
        assert "code_reviewer" in result.output
        manager.spawn.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_with_context(self):
        """测试从 ToolContext 获取 manager"""
        manager = make_mock_manager()
        context = make_mock_context(manager)
        tool = SpawnAgentTaskTool()  # 不传 manager

        result = await tool.execute(
            {"agent_name": "agent_a", "task": "do work"},
            context=context,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_spawn_empty_agent_name(self):
        """测试空 agent_name 失败"""
        manager = make_mock_manager()
        tool = SpawnAgentTaskTool(async_task_manager=manager)

        result = await tool.execute({"agent_name": "", "task": "hello"})
        assert result.success is False
        assert "不能为空" in result.error

    @pytest.mark.asyncio
    async def test_spawn_empty_task(self):
        """测试空 task 失败"""
        manager = make_mock_manager()
        tool = SpawnAgentTaskTool(async_task_manager=manager)

        result = await tool.execute({"agent_name": "agent_a", "task": ""})
        assert result.success is False
        assert "不能为空" in result.error

    @pytest.mark.asyncio
    async def test_spawn_no_manager(self):
        """测试无 manager 时失败"""
        tool = SpawnAgentTaskTool()
        result = await tool.execute({"agent_name": "a", "task": "t"})
        assert result.success is False
        assert "不可用" in result.error

    @pytest.mark.asyncio
    async def test_spawn_with_dependencies(self):
        """测试带依赖的任务提交"""
        manager = make_mock_manager()
        tool = SpawnAgentTaskTool(async_task_manager=manager)

        result = await tool.execute({
            "agent_name": "agent_a",
            "task": "analyze after collection",
            "depend_on": ["atask_prev1", "atask_prev2"],
        })

        assert result.success is True
        assert "依赖" in result.output

    def test_metadata(self):
        """测试工具元数据"""
        tool = SpawnAgentTaskTool()
        assert tool.metadata.name == "spawn_agent_task"
        assert "async" in tool.metadata.tags

    def test_parameters(self):
        """测试参数 schema"""
        tool = SpawnAgentTaskTool()
        params = tool.parameters
        assert "agent_name" in params["properties"]
        assert "task" in params["properties"]
        assert "depend_on" in params["properties"]
        assert "agent_name" in params["required"]
        assert "task" in params["required"]


# ==================== CheckTasksTool ====================


class TestCheckTasksTool:
    """测试 check_tasks 工具"""

    @pytest.mark.asyncio
    async def test_check_all(self):
        """测试查询所有任务"""
        manager = make_mock_manager()
        tool = CheckTasksTool(async_task_manager=manager)

        result = await tool.execute({"task_ids": []})
        assert result.success is True
        manager.format_status_table.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_check_specific(self):
        """测试查询指定任务"""
        manager = make_mock_manager()
        tool = CheckTasksTool(async_task_manager=manager)

        result = await tool.execute({"task_ids": ["t1", "t2"]})
        assert result.success is True
        manager.format_status_table.assert_called_once_with(["t1", "t2"])

    @pytest.mark.asyncio
    async def test_check_no_manager(self):
        """测试无 manager 时失败"""
        tool = CheckTasksTool()
        result = await tool.execute({})
        assert result.success is False

    def test_metadata(self):
        """测试工具元数据"""
        tool = CheckTasksTool()
        assert tool.metadata.name == "check_tasks"


# ==================== WaitTasksTool ====================


class TestWaitTasksTool:
    """测试 wait_tasks 工具"""

    @pytest.mark.asyncio
    async def test_wait_all_specific(self):
        """测试等待指定任务"""
        manager = make_mock_manager()
        tool = WaitTasksTool(async_task_manager=manager)

        result = await tool.execute({"task_ids": ["t1"], "timeout": 30})
        assert result.success is True
        manager.wait_all.assert_called_once_with(["t1"], timeout=30)

    @pytest.mark.asyncio
    async def test_wait_any(self):
        """测试等待任意任务"""
        manager = make_mock_manager()
        tool = WaitTasksTool(async_task_manager=manager)

        result = await tool.execute({"task_ids": [], "timeout": 10})
        assert result.success is True
        manager.wait_any.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_wait_timeout_no_results(self):
        """测试等待超时无结果"""
        manager = make_mock_manager()
        manager.wait_any = AsyncMock(return_value=[])
        tool = WaitTasksTool(async_task_manager=manager)

        result = await tool.execute({"timeout": 1})
        assert result.success is True
        assert "超时" in result.output

    @pytest.mark.asyncio
    async def test_wait_no_manager(self):
        """测试无 manager 时失败"""
        tool = WaitTasksTool()
        result = await tool.execute({})
        assert result.success is False

    def test_metadata(self):
        """测试工具元数据"""
        tool = WaitTasksTool()
        assert tool.metadata.name == "wait_tasks"


# ==================== CancelTaskTool ====================


class TestCancelTaskTool:
    """测试 cancel_task 工具"""

    @pytest.mark.asyncio
    async def test_cancel_success(self):
        """测试成功取消"""
        manager = make_mock_manager()
        tool = CancelTaskTool(async_task_manager=manager)

        result = await tool.execute({"task_id": "atask_abc12345"})
        assert result.success is True
        assert "已取消" in result.output

    @pytest.mark.asyncio
    async def test_cancel_failed(self):
        """测试取消失败（已完成）"""
        manager = make_mock_manager()
        manager.cancel = AsyncMock(return_value=False)
        tool = CancelTaskTool(async_task_manager=manager)

        result = await tool.execute({"task_id": "atask_abc12345"})
        assert result.success is True
        assert "无法取消" in result.output

    @pytest.mark.asyncio
    async def test_cancel_empty_id(self):
        """测试空 task_id 失败"""
        manager = make_mock_manager()
        tool = CancelTaskTool(async_task_manager=manager)

        result = await tool.execute({"task_id": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_cancel_no_manager(self):
        """测试无 manager 时失败"""
        tool = CancelTaskTool()
        result = await tool.execute({"task_id": "t1"})
        assert result.success is False

    def test_metadata(self):
        """测试工具元数据"""
        tool = CancelTaskTool()
        assert tool.metadata.name == "cancel_task"
