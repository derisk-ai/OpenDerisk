"""
单元测试 - Tool系统

测试ToolBase、ToolRegistry、BashTool等
"""

import pytest
from derisk.agent.tools import (
    ToolBase,
    ToolMetadata,
    ToolResult,
    ToolCategory,
    ToolRiskLevel,
    ToolRegistry,
    tool_registry,
)
from derisk.agent.tools.builtin.shell import BashTool


class TestToolBase:
    """ToolBase测试"""

    def test_create_tool_metadata(self):
        """测试创建工具元数据"""
        metadata = ToolMetadata(
            name="test_tool",
            description="Test tool",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
        )

        assert metadata.name == "test_tool"
        assert metadata.description == "Test tool"
        assert metadata.category == ToolCategory.UTILITY
        assert metadata.risk_level == ToolRiskLevel.LOW
        assert metadata.requires_permission is True

    def test_tool_result_success(self):
        """测试工具结果(成功)"""
        result = ToolResult(
            success=True, output="Success output", metadata={"key": "value"}
        )

        assert result.success is True
        assert result.output == "Success output"
        assert result.error is None
        assert result.metadata["key"] == "value"

    def test_tool_result_failure(self):
        """测试工具结果(失败)"""
        result = ToolResult(success=False, output="", error="Error message")

        assert result.success is False
        assert result.error == "Error message"


class TestToolRegistry:
    """ToolRegistry测试"""

    def test_register_tool(self):
        """测试注册工具"""
        registry = ToolRegistry()
        tool = BashTool()

        registry.register(tool)

        retrieved = registry.get("bash")
        assert retrieved is not None
        assert retrieved.metadata.name == "bash"

    def test_unregister_tool(self):
        """测试注销工具"""
        registry = ToolRegistry()
        tool = BashTool()

        registry.register(tool)
        registry.unregister("bash")

        retrieved = registry.get("bash")
        assert retrieved is None

    def test_list_all_tools(self):
        """测试列出所有工具"""
        registry = ToolRegistry()
        tool = BashTool()

        registry.register(tool)
        tools = registry.list_all()

        assert len(tools) == 1
        assert tools[0].metadata.name == "bash"

    def test_list_by_category(self):
        """测试按类别列出工具"""
        registry = ToolRegistry()
        tool = BashTool()

        registry.register(tool)
        shell_tools = registry.list_by_category(ToolCategory.SHELL)

        assert len(shell_tools) == 1
        assert shell_tools[0].metadata.name == "bash"


class TestBashTool:
    """BashTool测试"""

    @pytest.fixture
    def tool(self):
        """创建BashTool"""
        return BashTool()

    def test_bash_tool_metadata(self, tool):
        """测试Bash工具元数据"""
        assert tool.metadata.name == "bash"
        assert tool.metadata.category == ToolCategory.SHELL
        assert tool.metadata.risk_level == ToolRiskLevel.HIGH

    def test_bash_tool_parameters(self, tool):
        """测试Bash工具参数"""
        params = tool.parameters

        assert "command" in params["properties"]
        assert "command" in params["required"]
        assert "timeout" in params["properties"]
        assert "cwd" in params["properties"]

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, tool):
        """测试执行简单命令"""
        result = await tool.execute({"command": "echo 'Hello'", "timeout": 10})

        assert result.success is True
        assert "Hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_command_with_timeout(self, tool):
        """测试命令超时"""
        result = await tool.execute({"command": "sleep 5", "timeout": 1})

        assert result.success is False
        assert "超时" in result.error or "timeout" in result.error.lower()

    def test_validate_args(self, tool):
        """测试参数验证"""
        # 有效参数
        assert tool.validate_args({"command": "ls"}) is True

        # 缺少必需参数
        assert tool.validate_args({}) is False

    def test_to_openai_tool_format(self, tool):
        """测试转换为OpenAI工具格式"""
        openai_tool = tool.to_openai_tool()

        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "bash"
        assert "parameters" in openai_tool["function"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
