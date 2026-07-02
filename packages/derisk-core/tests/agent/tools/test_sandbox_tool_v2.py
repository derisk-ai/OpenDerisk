"""Sandbox 工具 V2 迁移测试 —— 验证 _get_sandbox_client 从 get_resource("sandbox_client") 读取。

Task 19: 沙箱工具 Bash/Read/Write/Edit 迁移到 ToolContext。
策略: get_resource 优先 (V2), config 回退 (BAIZE 兼容)。
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.builtin.sandbox.shell_exec import ShellExecTool


def _make_mock_sandbox_client():
    """创建一个模拟的沙箱客户端，提供工具所需的最小接口。"""
    client = MagicMock()
    client.work_dir = "/home/ubuntu"
    client.agent_file_system = None

    # shell.exec_command 模拟
    client.shell = MagicMock()
    client.shell.exec_command = AsyncMock()

    # file.read / file.write 模拟
    client.file = MagicMock()
    client.file.read = AsyncMock()
    client.file.write = AsyncMock()

    return client


class TestSandboxToolBaseGetClient:
    """验证 SandboxToolBase._get_sandbox_client 的查找路径。

    使用 ShellExecTool（SandboxToolBase 的具体子类）来测试 _get_sandbox_client。
    """

    def test_v2_path_get_resource_first(self):
        """V2 路径: get_resource("sandbox_client") 命中。"""
        mock_client = _make_mock_sandbox_client()
        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        tool = ShellExecTool()
        result = tool._get_sandbox_client(ctx)
        assert result is mock_client

    def test_baize_fallback_config(self):
        """BAIZE 回退: context.config["sandbox_client"] 命中。"""
        mock_client = _make_mock_sandbox_client()
        ctx = ToolContext()
        ctx.config["sandbox_client"] = mock_client

        tool = ShellExecTool()
        result = tool._get_sandbox_client(ctx)
        assert result is mock_client

    def test_baize_fallback_sandbox_manager(self):
        """BAIZE 回退: context.config["sandbox_manager"] 命中。"""
        mock_client = _make_mock_sandbox_client()
        mock_manager = MagicMock()
        mock_manager.client = mock_client

        ctx = ToolContext()
        ctx.config["sandbox_manager"] = mock_manager

        tool = ShellExecTool()
        result = tool._get_sandbox_client(ctx)
        assert result is mock_client

    def test_v2_priority_over_config(self):
        """V2 路径优先: 同时设置 get_resource 和 config 时，get_resource 返回的优先。"""
        v2_client = _make_mock_sandbox_client()
        baize_client = _make_mock_sandbox_client()

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", v2_client)
        ctx.config["sandbox_client"] = baize_client

        tool = ShellExecTool()
        result = tool._get_sandbox_client(ctx)
        assert result is v2_client

    def test_no_client_returns_none(self):
        """无沙箱客户端时返回 None。"""
        ctx = ToolContext()
        tool = ShellExecTool()
        result = tool._get_sandbox_client(ctx)
        assert result is None

    def test_context_none_returns_none(self):
        """context=None 时返回 None。"""
        tool = ShellExecTool()
        result = tool._get_sandbox_client(None)
        assert result is None

    def test_dict_context_sandbox_client(self):
        """字典类型 context 也能获取 sandbox_client。"""
        mock_client = _make_mock_sandbox_client()
        ctx = {"sandbox_client": mock_client}
        tool = ShellExecTool()
        result = tool._get_sandbox_client(ctx)
        assert result is mock_client


class TestBashToolV2Execute:
    """BashTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_bash_v2_resource_path(self):
        """BashTool 通过 get_resource 获取 sandbox_client 并执行命令。"""
        from derisk.agent.tools.builtin.shell.bash import BashTool

        mock_client = _make_mock_sandbox_client()
        mock_client.shell.exec_command.return_value = MagicMock(
            status="completed", exit_code=0
        )

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        with patch(
            "derisk.agent.tools.builtin.shell.bash.BashTool._execute_sandbox",
            new_callable=AsyncMock,
        ) as mock_exec_sandbox:
            mock_exec_sandbox.return_value = MagicMock(success=True, output="ok")
            tool = BashTool()
            result = await tool.execute({"command": "echo hello"}, context=ctx)
            mock_exec_sandbox.assert_called_once()
            assert result.success

    async def test_bash_no_client_local_fallback(self):
        """BashTool 无 sandbox_client 时走本地执行路径。"""
        from derisk.agent.tools.builtin.shell.bash import BashTool

        ctx = ToolContext()
        tool = BashTool()
        result = await tool.execute(
            {"command": "echo hello", "timeout": 1}, context=ctx
        )
        # 本地执行应该成功
        assert result is not None


class TestReadToolV2Execute:
    """ReadTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_read_v2_resource_path(self, tmp_path):
        """ReadTool 通过 get_resource 获取 sandbox_client 并走沙箱路径。"""
        from derisk.agent.tools.builtin.file_system.read import ReadTool

        mock_client = _make_mock_sandbox_client()
        mock_client.work_dir = str(tmp_path)

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        with patch(
            "derisk.agent.tools.builtin.file_system.read.ReadTool._execute_sandbox",
            new_callable=AsyncMock,
        ) as mock_exec_sandbox:
            mock_exec_sandbox.return_value = MagicMock(success=True, output="content")
            tool = ReadTool()
            result = await tool.execute(
                {"path": "/test/file.txt"}, context=ctx
            )
            mock_exec_sandbox.assert_called_once()
            assert result.success

    async def test_read_no_client_local_fallback(self, tmp_path):
        """ReadTool 无 sandbox_client 时走本地文件系统。"""
        from derisk.agent.tools.builtin.file_system.read import ReadTool

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        ctx = ToolContext()
        tool = ReadTool()
        result = await tool.execute({"path": str(test_file)}, context=ctx)
        assert result.success
        assert "hello world" in result.output


class TestWriteToolV2Execute:
    """WriteTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_write_v2_resource_path(self, tmp_path):
        """WriteTool 通过 get_resource 获取 sandbox_client 并走沙箱路径。"""
        from derisk.agent.tools.builtin.file_system.write import WriteTool

        mock_client = _make_mock_sandbox_client()
        mock_client.work_dir = str(tmp_path)

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        with patch(
            "derisk.agent.tools.builtin.file_system.write.WriteTool._execute_sandbox",
            new_callable=AsyncMock,
        ) as mock_exec_sandbox:
            mock_exec_sandbox.return_value = MagicMock(success=True, output="created")
            tool = WriteTool()
            result = await tool.execute(
                {"path": "/test/out.txt", "content": "data"}, context=ctx
            )
            mock_exec_sandbox.assert_called_once()
            assert result.success

    async def test_write_no_client_local_fallback(self, tmp_path):
        """WriteTool 无 sandbox_client 时走本地文件系统。"""
        from derisk.agent.tools.builtin.file_system.write import WriteTool

        test_file = tmp_path / "out.txt"
        ctx = ToolContext()
        tool = WriteTool()
        result = await tool.execute(
            {"path": str(test_file), "content": "hello"}, context=ctx
        )
        assert result.success
        assert test_file.read_text() == "hello"


class TestEditToolV2Execute:
    """EditTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_edit_v2_resource_path(self, tmp_path):
        """EditTool 通过 get_resource 获取 sandbox_client 并走沙箱路径。"""
        from derisk.agent.tools.builtin.file_system.edit import EditTool

        mock_client = _make_mock_sandbox_client()
        mock_client.work_dir = str(tmp_path)

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        with patch(
            "derisk.agent.tools.builtin.file_system.edit.EditTool._execute_sandbox",
            new_callable=AsyncMock,
        ) as mock_exec_sandbox:
            mock_exec_sandbox.return_value = MagicMock(success=True, output="edited")
            tool = EditTool()
            result = await tool.execute(
                {"path": "/test/f.txt", "old_string": "a", "new_string": "b"},
                context=ctx,
            )
            mock_exec_sandbox.assert_called_once()
            assert result.success

    async def test_edit_no_client_local_fallback(self, tmp_path):
        """EditTool 无 sandbox_client 时走本地文件系统。"""
        from derisk.agent.tools.builtin.file_system.edit import EditTool

        test_file = tmp_path / "f.txt"
        test_file.write_text("hello world")

        ctx = ToolContext()
        tool = EditTool()
        result = await tool.execute(
            {"path": str(test_file), "old_string": "hello", "new_string": "hi"},
            context=ctx,
        )
        assert result.success
        assert "hi world" in test_file.read_text()


class TestShellExecToolV2Execute:
    """ShellExecTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_shell_exec_v2_resource_path(self):
        """ShellExecTool 通过 get_resource 获取 sandbox_client 并执行命令。"""
        mock_client = _make_mock_sandbox_client()
        mock_client.shell.exec_command.return_value = MagicMock(
            status="completed", exit_code=0
        )

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        with patch(
            "derisk.sandbox.sandbox_utils.collect_shell_output",
            return_value="hello\n",
        ):
            tool = ShellExecTool()
            result = await tool.execute({"command": "echo hello"}, context=ctx)
            assert result.success
            mock_client.shell.exec_command.assert_called_once()

    async def test_shell_exec_no_client_fails(self):
        """ShellExecTool 无 sandbox_client 时返回失败。"""
        ctx = ToolContext()
        tool = ShellExecTool()
        result = await tool.execute({"command": "echo hello"}, context=ctx)
        assert not result.success
        assert "沙箱" in result.error


class TestViewToolV2Execute:
    """ViewTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_view_v2_resource_path(self):
        """ViewTool 通过 get_resource 获取 sandbox_client。"""
        from derisk.agent.tools.builtin.sandbox.view import ViewTool

        mock_client = _make_mock_sandbox_client()

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        # normalize_sandbox_path 和 detect_path_kind 在 execute 内部
        # 局部导入（from derisk.sandbox.sandbox_utils import ...），
        # 所以需要 patch 源模块。
        with patch(
            "derisk.sandbox.sandbox_utils.normalize_sandbox_path",
            return_value="/home/ubuntu",
        ), patch(
            "derisk.sandbox.sandbox_utils.detect_path_kind",
            new_callable=AsyncMock,
        ) as mock_detect:
            mock_detect.return_value = "dir"
            with patch(
                "derisk.agent.tools.builtin.sandbox.view._render_directory_listing",
                new_callable=AsyncMock,
            ) as mock_render:
                mock_render.return_value = "listing"
                tool = ViewTool()
                result = await tool.execute({"path": "/home/ubuntu"}, context=ctx)
                assert result.success
                assert result.output == "listing"

    async def test_view_no_client_fails(self):
        """ViewTool 无 sandbox_client 时返回失败。"""
        from derisk.agent.tools.builtin.sandbox.view import ViewTool

        ctx = ToolContext()
        tool = ViewTool()
        result = await tool.execute({"path": "/test"}, context=ctx)
        assert not result.success
        assert "沙箱" in result.error


class TestCreateFileToolV2Execute:
    """CreateFileTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_create_file_v2_resource_path(self):
        """CreateFileTool 通过 get_resource 获取 sandbox_client 并创建文件。"""
        from derisk.agent.tools.builtin.sandbox.create_file import CreateFileTool

        mock_client = _make_mock_sandbox_client()

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        # normalize_sandbox_path 和 ensure_directory 在 execute 内部
        # 局部导入，所以 patch 源模块。
        with patch(
            "derisk.sandbox.sandbox_utils.normalize_sandbox_path",
            return_value="/home/ubuntu/test.txt",
        ), patch(
            "derisk.sandbox.sandbox_utils.ensure_directory",
            new_callable=AsyncMock,
        ):
            tool = CreateFileTool()
            result = await tool.execute(
                {
                    "description": "test",
                    "path": "test.txt",
                    "file_text": "hello",
                },
                context=ctx,
            )
            assert result.success
            mock_client.file.write.assert_called_once()

    async def test_create_file_no_client_fails(self):
        """CreateFileTool 无 sandbox_client 时返回失败。"""
        from derisk.agent.tools.builtin.sandbox.create_file import CreateFileTool

        ctx = ToolContext()
        tool = CreateFileTool()
        result = await tool.execute(
            {"description": "test", "path": "test.txt", "file_text": "hello"},
            context=ctx,
        )
        assert not result.success
        assert "沙箱" in result.error


class TestEditFileToolV2Execute:
    """EditFileTool.execute() 从 V2 ToolContext 读取 sandbox_client。"""

    async def test_edit_file_v2_resource_path(self):
        """EditFileTool 通过 get_resource 获取 sandbox_client 并编辑文件。"""
        from derisk.agent.tools.builtin.sandbox.edit_file import EditFileTool

        mock_client = _make_mock_sandbox_client()
        mock_client.file.read = AsyncMock()
        mock_client.file.read.return_value = MagicMock(content="hello world")

        ctx = ToolContext()
        ctx.set_resource("sandbox_client", mock_client)

        # normalize_sandbox_path 和 detect_path_kind 在 execute 内部
        # 局部导入（from derisk.sandbox.sandbox_utils import ...），
        # 所以需要 patch 源模块。
        with patch(
            "derisk.sandbox.sandbox_utils.normalize_sandbox_path",
            return_value="/home/ubuntu/test.txt",
        ), patch(
            "derisk.sandbox.sandbox_utils.detect_path_kind",
            new_callable=AsyncMock,
        ) as mock_detect:
            mock_detect.return_value = "file"
            tool = EditFileTool()
            result = await tool.execute(
                {
                    "description": "test",
                    "path": "test.txt",
                    "new_str": " world!",
                    "append": True,
                },
                context=ctx,
            )
            assert result.success
            mock_client.file.write.assert_called_once()

    async def test_edit_file_no_client_fails(self):
        """EditFileTool 无 sandbox_client 时返回失败。"""
        from derisk.agent.tools.builtin.sandbox.edit_file import EditFileTool

        ctx = ToolContext()
        tool = EditFileTool()
        result = await tool.execute(
            {"description": "test", "path": "test.txt", "new_str": "x"},
            context=ctx,
        )
        assert not result.success
        assert "沙箱" in result.error
