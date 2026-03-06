"""Tests for new capability modules."""

import pytest
import asyncio
from pathlib import Path
import tempfile
import os

# Permission System Tests
class TestPermissionSystem:
    """权限系统测试"""
    
    def test_permission_action_enum(self):
        from derisk_core.permission import PermissionAction
        
        assert PermissionAction.ALLOW.value == "allow"
        assert PermissionAction.DENY.value == "deny"
        assert PermissionAction.ASK.value == "ask"
    
    def test_permission_rule(self):
        from derisk_core.permission import PermissionRule, PermissionAction
        
        rule = PermissionRule(
            tool_pattern="bash",
            action=PermissionAction.ALLOW
        )
        assert rule.tool_pattern == "bash"
        assert rule.action == PermissionAction.ALLOW
    
    def test_permission_ruleset(self):
        from derisk_core.permission import PermissionRuleset, PermissionRule, PermissionAction
        
        ruleset = PermissionRuleset(
            rules={
                "*": PermissionRule(tool_pattern="*", action=PermissionAction.ALLOW),
                "*.env": PermissionRule(tool_pattern="*.env", action=PermissionAction.ASK),
            },
            default_action=PermissionAction.DENY
        )
        
        # Test exact match
        assert ruleset.check("read") == PermissionAction.ALLOW
        
        # Test wildcard match
        assert ruleset.check(".env") == PermissionAction.ASK
        
        # Test default
        ruleset2 = PermissionRuleset(default_action=PermissionAction.DENY)
        assert ruleset2.check("unknown") == PermissionAction.DENY
    
    def test_preset_permissions(self):
        from derisk_core.permission import (
            PRIMARY_PERMISSION,
            READONLY_PERMISSION,
            EXPLORE_PERMISSION,
            SANDBOX_PERMISSION,
            PermissionAction
        )
        
        # Primary permission
        assert PRIMARY_PERMISSION.check("bash") == PermissionAction.ALLOW
        assert PRIMARY_PERMISSION.check(".env") == PermissionAction.ASK
        
        # Readonly permission
        assert READONLY_PERMISSION.check("read") == PermissionAction.ALLOW
        assert READONLY_PERMISSION.check("write") == PermissionAction.DENY
        
        # Explore permission
        assert EXPLORE_PERMISSION.check("glob") == PermissionAction.ALLOW
        assert EXPLORE_PERMISSION.check("bash") == PermissionAction.DENY
        
        # Sandbox permission
        assert SANDBOX_PERMISSION.check("bash") == PermissionAction.ALLOW
        assert SANDBOX_PERMISSION.check(".env") == PermissionAction.DENY
    
    @pytest.mark.asyncio
    async def test_permission_checker(self):
        from derisk_core.permission import PermissionChecker, PermissionRuleset, PermissionAction
        
        ruleset = PermissionRuleset(
            rules={
                "allow_tool": PermissionRule(tool_pattern="allow_tool", action=PermissionAction.ALLOW),
                "deny_tool": PermissionRule(tool_pattern="deny_tool", action=PermissionAction.DENY),
            },
            default_action=PermissionAction.ASK
        )
        
        checker = PermissionChecker(ruleset)
        
        # Test allow
        result = await checker.check("allow_tool")
        assert result.allowed is True
        
        # Test deny
        result = await checker.check("deny_tool")
        assert result.allowed is False


# Sandbox System Tests
class TestSandboxSystem:
    """沙箱系统测试"""
    
    def test_sandbox_config(self):
        from derisk_core.sandbox import SandboxConfig
        
        config = SandboxConfig(
            image="python:3.11-slim",
            timeout=300,
            memory_limit="512m"
        )
        
        assert config.image == "python:3.11-slim"
        assert config.timeout == 300
        assert config.memory_limit == "512m"
    
    def test_sandbox_result(self):
        from derisk_core.sandbox import SandboxResult
        
        result = SandboxResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr=""
        )
        
        assert result.success is True
        assert result.exit_code == 0
    
    @pytest.mark.asyncio
    async def test_local_sandbox(self):
        from derisk_core.sandbox import LocalSandbox
        
        sandbox = LocalSandbox()
        
        # Start should succeed
        assert await sandbox.start() is True
        
        # Execute simple command
        result = await sandbox.execute("echo 'hello'", timeout=10)
        assert result.success is True
        assert "hello" in result.stdout
        
        # Stop should succeed
        assert await sandbox.stop() is True
    
    @pytest.mark.asyncio
    async def test_local_sandbox_forbidden_command(self):
        from derisk_core.sandbox import LocalSandbox
        
        sandbox = LocalSandbox()
        
        # Forbidden command should fail
        result = await sandbox.execute("rm -rf /")
        assert result.success is False
        assert "禁止" in result.error


# Tools System Tests
class TestToolsSystem:
    """工具系统测试"""
    
    def test_tool_metadata(self):
        from derisk_core.tools import ToolMetadata, ToolCategory, ToolRisk
        
        meta = ToolMetadata(
            name="test_tool",
            description="A test tool",
            category=ToolCategory.SYSTEM,
            risk=ToolRisk.MEDIUM
        )
        
        assert meta.name == "test_tool"
        assert meta.category == ToolCategory.SYSTEM
    
    def test_tool_result(self):
        from derisk_core.tools import ToolResult
        
        result = ToolResult(
            success=True,
            output="test output",
            metadata={"key": "value"}
        )
        
        assert result.success is True
        assert result.output == "test output"
    
    @pytest.mark.asyncio
    async def test_read_tool(self):
        from derisk_core.tools import ReadTool
        
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("line 1\nline 2\nline 3\n")
            temp_path = f.name
        
        try:
            tool = ReadTool()
            result = await tool.execute({"file_path": temp_path})
            
            assert result.success is True
            assert "line 1" in result.output
            assert "line 2" in result.output
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_write_tool(self):
        from derisk_core.tools import WriteTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            
            tool = WriteTool()
            result = await tool.execute({
                "file_path": file_path,
                "content": "test content"
            })
            
            assert result.success is True
            assert os.path.exists(file_path)
            
            with open(file_path) as f:
                assert f.read() == "test content"
    
    @pytest.mark.asyncio
    async def test_edit_tool(self):
        from derisk_core.tools import EditTool, WriteTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.py")
            
            # Write initial content
            write_tool = WriteTool()
            await write_tool.execute({
                "file_path": file_path,
                "content": "print('old')"
            })
            
            # Edit content
            edit_tool = EditTool()
            result = await edit_tool.execute({
                "file_path": file_path,
                "old_string": "print('old')",
                "new_string": "print('new')"
            })
            
            assert result.success is True
            
            with open(file_path) as f:
                assert "print('new')" in f.read()
    
    @pytest.mark.asyncio
    async def test_glob_tool(self):
        from derisk_core.tools import GlobTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            Path(tmpdir, "file1.py").touch()
            Path(tmpdir, "file2.py").touch()
            Path(tmpdir, "file3.txt").touch()
            
            tool = GlobTool()
            result = await tool.execute({
                "pattern": "*.py",
                "path": tmpdir
            })
            
            assert result.success is True
            assert "file1.py" in result.output
            assert "file2.py" in result.output
            assert "file3.txt" not in result.output
    
    @pytest.mark.asyncio
    async def test_grep_tool(self):
        from derisk_core.tools import GrepTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.py")
            with open(file_path, 'w') as f:
                f.write("def hello():\n    print('hello')\n\ndef world():\n    print('world')\n")
            
            tool = GrepTool()
            result = await tool.execute({
                "pattern": r"def\s+\w+\(",
                "path": tmpdir,
                "include": "*.py"
            })
            
            assert result.success is True
            assert "def hello()" in result.output
            assert "def world()" in result.output
    
    def test_tool_registry(self):
        from derisk_core.tools import tool_registry, register_builtin_tools, ToolCategory
        
        # Register builtin tools
        register_builtin_tools()
        
        # Check tools are registered
        assert tool_registry.get("read") is not None
        assert tool_registry.get("write") is not None
        assert tool_registry.get("edit") is not None
        assert tool_registry.get("glob") is not None
        assert tool_registry.get("grep") is not None
        assert tool_registry.get("bash") is not None
        assert tool_registry.get("webfetch") is not None
        assert tool_registry.get("websearch") is not None
        
        # Check schemas
        schemas = tool_registry.get_schemas()
        assert "read" in schemas
        assert "parameters" in schemas["read"]


# Composition Tests
class TestComposition:
    """工具组合测试"""
    
    @pytest.mark.asyncio
    async def test_batch_executor(self):
        from derisk_core.tools import BatchExecutor, register_builtin_tools
        
        register_builtin_tools()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files
            Path(tmpdir, "a.txt").write_text("content a")
            Path(tmpdir, "b.txt").write_text("content b")
            
            executor = BatchExecutor()
            result = await executor.execute([
                {"tool": "read", "args": {"file_path": str(Path(tmpdir, "a.txt"))}},
                {"tool": "read", "args": {"file_path": str(Path(tmpdir, "b.txt"))}},
            ])
            
            assert result.success_count == 2
            assert result.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_task_executor(self):
        from derisk_core.tools import TaskExecutor, register_builtin_tools
        
        register_builtin_tools()
        
        executor = TaskExecutor()
        result = await executor.spawn({
            "tool": "glob",
            "args": {"pattern": "*"}
        })
        
        assert result.success is True
        assert result.task_id.startswith("task_")


# Config System Tests
class TestConfigSystem:
    """配置系统测试"""
    
    def test_model_config(self):
        from derisk_core.config import ModelConfig
        
        config = ModelConfig(
            provider="openai",
            model_id="gpt-4",
            temperature=0.7
        )
        
        assert config.provider == "openai"
        assert config.model_id == "gpt-4"
    
    def test_permission_config(self):
        from derisk_core.config import PermissionConfig
        
        config = PermissionConfig(
            default_action="ask",
            rules={"*": "allow"}
        )
        
        assert config.default_action == "ask"
    
    def test_agent_config(self):
        from derisk_core.config import AgentConfig
        
        config = AgentConfig(
            name="test_agent",
            description="Test agent",
            max_steps=10
        )
        
        assert config.name == "test_agent"
        assert config.max_steps == 10
    
    def test_app_config(self):
        from derisk_core.config import AppConfig
        
        config = AppConfig(name="TestApp")
        
        assert config.name == "TestApp"
        assert "primary" in config.agents
    
    def test_config_loader_defaults(self):
        from derisk_core.config import ConfigLoader
        
        config = ConfigLoader._load_defaults()
        
        assert config.name == "OpenDeRisk"
    
    def test_config_save_and_load(self):
        from derisk_core.config import ConfigLoader, AppConfig
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "test_config.json")
            
            # Create and save config
            config = AppConfig(name="TestProject")
            ConfigLoader.save(config, config_path)
            
            # Load config
            loaded = ConfigLoader.load(config_path)
            
            assert loaded.name == "TestProject"


# Network Tools Tests (marked as skip if no aiohttp)
class TestNetworkTools:
    """网络工具测试"""
    
    @pytest.mark.skipif(
        not pytest.importorskip("aiohttp", reason="aiohttp not installed"),
        reason="aiohttp not installed"
    )
    @pytest.mark.asyncio
    async def test_webfetch_tool(self):
        from derisk_core.tools import WebFetchTool
        
        tool = WebFetchTool()
        
        # This might fail in CI without network
        try:
            result = await tool.execute({
                "url": "https://httpbin.org/get",
                "format": "json",
                "timeout": 10
            })
            assert result.success is True
        except Exception:
            pytest.skip("Network not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])