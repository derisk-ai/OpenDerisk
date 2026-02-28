"""
Tests for Shared Infrastructure - 共享基础设施测试

测试目标：
1. SharedSessionContext - 统一会话上下文容器
2. ContextArchiver - 上下文自动归档器
3. TaskBoardManager - 任务看板管理器
4. V1/V2 Adapters - 架构适配器
"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestContextArchiver:
    """ContextArchiver 测试"""

    @pytest.fixture
    def mock_file_system(self):
        """创建模拟的 AgentFileSystem"""
        mock_fs = MagicMock()
        mock_fs.conv_id = "conv_001"
        mock_fs.session_id = "session_001"
        mock_fs.save_file = AsyncMock()
        mock_fs.read_file = AsyncMock(return_value=None)
        
        saved_file = MagicMock()
        saved_file.file_id = "file_123"
        saved_file.file_name = "test_file.txt"
        saved_file.oss_url = "oss://bucket/file"
        saved_file.preview_url = "https://preview.url"
        saved_file.download_url = "https://download.url"
        mock_fs.save_file.return_value = saved_file
        
        return mock_fs

    @pytest.mark.asyncio
    async def test_process_tool_output_small(self, mock_file_system):
        """测试小输出不归档"""
        from derisk.agent.shared.context_archiver import ContextArchiver
        
        archiver = ContextArchiver(file_system=mock_file_system)
        
        result = await archiver.process_tool_output(
            tool_name="test_tool",
            output="small output",
        )
        
        assert result["archived"] is False
        assert result["content"] == "small output"
        mock_file_system.save_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_tool_output_large(self, mock_file_system):
        """测试大输出自动归档"""
        from derisk.agent.shared.context_archiver import ContextArchiver, ContentType
        
        archiver = ContextArchiver(file_system=mock_file_system)
        
        large_output = "x" * 10000  # 10000 characters
        
        result = await archiver.process_tool_output(
            tool_name="bash",
            output=large_output,
        )
        
        assert result["archived"] is True
        assert "archive_ref" in result
        assert result["archive_ref"]["file_id"] == "file_123"
        mock_file_system.save_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_skill_content(self, mock_file_system):
        """测试 Skill 内容归档"""
        from derisk.agent.shared.context_archiver import ContextArchiver
        
        archiver = ContextArchiver(file_system=mock_file_system)
        
        result = await archiver.archive_skill_content(
            skill_name="code_analysis",
            content="skill full content " * 1000,
            summary="完成了代码分析",
            key_results=["发现3个问题", "建议优化点2处"],
        )
        
        assert result["archived"] is True
        assert "archive_ref" in result

    @pytest.mark.asyncio
    async def test_restore_content(self, mock_file_system):
        """测试内容恢复"""
        from derisk.agent.shared.context_archiver import ContextArchiver
        
        archiver = ContextArchiver(file_system=mock_file_system)
        
        # 先归档
        await archiver.process_tool_output(
            tool_name="test",
            output="x" * 10000,
        )
        
        # 模拟恢复
        mock_file_system.read_file.return_value = "restored content"
        
        # 恢复
        content = await archiver.restore_content(list(archiver._archives.keys())[0])
        
        assert content == "restored content"

    def test_get_statistics(self, mock_file_system):
        """测试统计信息"""
        from derisk.agent.shared.context_archiver import ContextArchiver
        
        archiver = ContextArchiver(file_system=mock_file_system)
        
        stats = archiver.get_statistics()
        
        assert "total_archives" in stats
        assert "total_archived_tokens" in stats


class TestTaskBoardManager:
    """TaskBoardManager 测试"""

    @pytest.fixture
    def task_board(self):
        """创建 TaskBoardManager 实例"""
        from derisk.agent.shared.task_board import TaskBoardManager
        return TaskBoardManager(
            session_id="session_001",
            agent_id="agent_001",
            file_system=None,
        )

    @pytest.mark.asyncio
    async def test_create_todo(self, task_board):
        """测试创建 Todo"""
        from derisk.agent.shared.task_board import TaskPriority, TaskStatus
        
        await task_board.load()
        
        todo = await task_board.create_todo(
            title="测试任务",
            description="这是一个测试任务",
            priority=TaskPriority.HIGH,
        )
        
        assert todo.id is not None
        assert todo.title == "测试任务"
        assert todo.status == TaskStatus.PENDING
        assert todo.priority == TaskPriority.HIGH

    @pytest.mark.asyncio
    async def test_update_todo_status(self, task_board):
        """测试更新 Todo 状态"""
        from derisk.agent.shared.task_board import TaskStatus
        
        await task_board.load()
        
        todo = await task_board.create_todo(title="测试任务")
        
        updated = await task_board.update_todo_status(
            task_id=todo.id,
            status=TaskStatus.WORKING,
        )
        
        assert updated.status == TaskStatus.WORKING
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_complete_todo(self, task_board):
        """测试完成 Todo"""
        from derisk.agent.shared.task_board import TaskStatus
        
        await task_board.load()
        
        todo = await task_board.create_todo(title="测试任务")
        
        updated = await task_board.update_todo_status(
            task_id=todo.id,
            status=TaskStatus.COMPLETED,
        )
        
        assert updated.status == TaskStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.progress == 1.0

    @pytest.mark.asyncio
    async def test_list_todos(self, task_board):
        """测试列出 Todo"""
        await task_board.load()
        
        await task_board.create_todo(title="任务1")
        await task_board.create_todo(title="任务2")
        await task_board.create_todo(title="任务3")
        
        todos = await task_board.list_todos()
        
        assert len(todos) == 3

    @pytest.mark.asyncio
    async def test_create_kanban(self, task_board):
        """测试创建 Kanban"""
        await task_board.load()
        
        result = await task_board.create_kanban(
            mission="完成测试任务",
            stages=[
                {"stage_id": "plan", "description": "规划"},
                {"stage_id": "execute", "description": "执行"},
                {"stage_id": "verify", "description": "验证"},
            ]
        )
        
        assert result["status"] == "success"
        kanban = await task_board.get_kanban()
        assert kanban is not None
        assert len(kanban.stages) == 3

    @pytest.mark.asyncio
    async def test_kanban_submit_deliverable(self, task_board):
        """测试提交 Kanban 交付物"""
        await task_board.load()
        
        await task_board.create_kanban(
            mission="测试任务",
            stages=[
                {"stage_id": "s1", "description": "阶段1"},
                {"stage_id": "s2", "description": "阶段2"},
            ]
        )
        
        result = await task_board.submit_deliverable(
            stage_id="s1",
            deliverable={"result": "deliverable content"},
        )
        
        assert result["status"] == "success"
        assert result.get("next_stage") is not None

    @pytest.mark.asyncio
    async def test_get_status_report(self, task_board):
        """测试获取状态报告"""
        await task_board.load()
        
        await task_board.create_todo(title="任务1")
        await task_board.create_todo(title="任务2")
        
        report = await task_board.get_status_report()
        
        assert "## 任务状态概览" in report
        assert "待处理: 2" in report


class TestSharedSessionContext:
    """SharedSessionContext 测试"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_create_context(self, temp_dir):
        """测试创建共享上下文"""
        from derisk.agent.shared import SharedSessionContext, SharedContextConfig
        
        config = SharedContextConfig(
            archive_threshold_tokens=1000,
            auto_archive=True,
            enable_task_board=True,
            enable_archiver=True,
        )
        
        ctx = await SharedSessionContext.create(
            session_id="session_001",
            conv_id="conv_001",
            config=config,
        )
        
        assert ctx.session_id == "session_001"
        assert ctx.file_system is not None
        assert ctx.task_board is not None
        assert ctx.archiver is not None
        
        await ctx.close()

    @pytest.mark.asyncio
    async def test_context_statistics(self, temp_dir):
        """测试上下文统计"""
        from derisk.agent.shared import SharedSessionContext
        
        ctx = await SharedSessionContext.create(
            session_id="session_001",
            conv_id="conv_001",
        )
        
        stats = ctx.get_statistics()
        
        assert stats["session_id"] == "session_001"
        assert stats["components"]["file_system"] is True
        
        await ctx.close()

    @pytest.mark.asyncio
    async def test_context_context_manager(self, temp_dir):
        """测试上下文管理器模式"""
        from derisk.agent.shared import SharedSessionContext
        
        async with SharedSessionContext.create(
            session_id="session_001",
            conv_id="conv_001",
        ) as ctx:
            assert ctx.is_initialized is True
        
        # 自动调用 close


class TestAdapters:
    """适配器测试"""

    @pytest.fixture
    def shared_context(self, temp_dir):
        """创建共享上下文 fixture"""
        async def create():
            from derisk.agent.shared import SharedSessionContext
            return await SharedSessionContext.create(
                session_id="session_001",
                conv_id="conv_001",
            )
        return create

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.asyncio
    async def test_v1_adapter_create(self, shared_context):
        """测试 V1 适配器创建"""
        from derisk.agent.shared import V1ContextAdapter
        
        ctx = await shared_context()
        adapter = V1ContextAdapter(ctx)
        
        assert adapter.session_id == "session_001"
        assert adapter.file_system is not None
        
        await ctx.close()

    @pytest.mark.asyncio
    async def test_v1_adapter_process_output(self, shared_context):
        """测试 V1 适配器处理输出"""
        from derisk.agent.shared import V1ContextAdapter
        
        ctx = await shared_context()
        adapter = V1ContextAdapter(ctx)
        
        result = await adapter.process_tool_output(
            tool_name="test",
            output="small output",
        )
        
        assert "content" in result
        
        await ctx.close()

    @pytest.mark.asyncio
    async def test_v2_adapter_create(self, shared_context):
        """测试 V2 适配器创建"""
        from derisk.agent.shared import V2ContextAdapter
        
        ctx = await shared_context()
        adapter = V2ContextAdapter(ctx)
        
        assert adapter.session_id == "session_001"
        assert adapter._hooks_registered is False
        
        await ctx.close()

    @pytest.mark.asyncio
    async def test_v2_adapter_get_tools(self, shared_context):
        """测试 V2 适配器获取工具"""
        from derisk.agent.shared import V2ContextAdapter
        
        ctx = await shared_context()
        adapter = V2ContextAdapter(ctx)
        
        tools = await adapter.get_enhanced_tools()
        
        # 如果 ToolBase 可用，应该有 Todo 和 Kanban 工具
        # 否则为空列表
        assert isinstance(tools, list)
        
        await ctx.close()


@pytest.mark.asyncio
async def test_integration_workflow():
    """集成测试：完整工作流"""
    from derisk.agent.shared import (
        SharedSessionContext,
        V1ContextAdapter,
        TaskStatus,
        TaskPriority,
    )
    
    async with SharedSessionContext.create(
        session_id="integration_test",
        conv_id="conv_test",
    ) as ctx:
        # 使用适配器
        adapter = V1ContextAdapter(ctx)
        
        # 创建 Todo
        todo = await ctx.create_todo(
            title="集成测试任务",
            description="验证完整工作流",
            priority=TaskPriority.HIGH,
        )
        
        assert todo.id is not None
        
        # 模拟处理工具输出
        small_output = await adapter.process_tool_output(
            tool_name="read",
            output="small content",
        )
        assert small_output["archived"] is False
        
        # 获取状态报告
        report = await adapter.get_task_status_for_prompt()
        assert "集成测试任务" in report
        
        # 检查统计
        stats = ctx.get_statistics()
        assert stats["components"]["task_board"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])