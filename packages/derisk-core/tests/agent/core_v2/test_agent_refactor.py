"""Tests for refactored Agent system."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from derisk.agent.core.agent_info import (
    AgentInfo,
    AgentMode,
    AgentRegistry,
    PermissionAction,
    PermissionRule,
    PermissionRuleset,
    create_agent_info,
)
from derisk.agent.core.execution import (
    ExecutionEngine,
    ExecutionHooks,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStep,
    AgentExecutor,
    SessionManager,
    ToolExecutor,
    ToolRegistry,
    tool,
)
from derisk.agent.core.prompt_v2 import (
    AgentProfile,
    PromptTemplate,
    SystemPromptBuilder,
    compose_prompts,
)


class TestPermissionSystem:
    """Tests for Permission System."""

    def test_permission_rule_creation(self):
        """Test creating a permission rule."""
        rule = PermissionRule(
            action=PermissionAction.ALLOW, pattern="read", permission="read"
        )
        assert rule.action == PermissionAction.ALLOW
        assert rule.pattern == "read"

    def test_permission_ruleset_from_config(self):
        """Test creating ruleset from configuration."""
        config = {
            "*": "ask",
            "read": "allow",
            "write": "deny",
            "bash": {
                "*": "ask",
                "git status": "allow",
            },
        }
        ruleset = PermissionRuleset.from_config(config)

        assert ruleset.check("read") == PermissionAction.ALLOW
        assert ruleset.check("write") == PermissionAction.DENY
        assert ruleset.check("edit") == PermissionAction.ASK

    def test_permission_ruleset_merge(self):
        """Test merging multiple rulesets."""
        ruleset1 = PermissionRuleset.from_config(
            {
                "*": "deny",
                "read": "allow",
            }
        )
        ruleset2 = PermissionRuleset.from_config(
            {
                "write": "ask",
            }
        )

        merged = PermissionRuleset.merge(ruleset1, ruleset2)
        assert merged.check("read") == PermissionAction.ALLOW
        assert merged.check("write") == PermissionAction.ASK
        assert merged.check("edit") == PermissionAction.DENY

    def test_permission_is_allowed(self):
        """Test is_allowed convenience method."""
        ruleset = PermissionRuleset.from_config({"read": "allow"})
        assert ruleset.is_allowed("read")
        assert not ruleset.is_allowed("write")


class TestAgentInfo:
    """Tests for AgentInfo configuration model."""

    def test_agent_info_creation(self):
        """Test creating AgentInfo."""
        info = AgentInfo(
            name="test-agent",
            description="Test agent",
            mode=AgentMode.PRIMARY,
        )
        assert info.name == "test-agent"
        assert info.mode == AgentMode.PRIMARY
        assert info.hidden is False

    def test_agent_info_permission_check(self):
        """Test permission checking on AgentInfo."""
        info = AgentInfo(
            name="readonly-agent", permission={"write": "deny", "read": "allow"}
        )

        assert info.check_permission("read") == PermissionAction.ALLOW
        assert info.check_permission("write") == PermissionAction.DENY

    def test_agent_info_from_markdown(self):
        """Test parsing AgentInfo from markdown."""
        content = """---
name: code-reviewer
description: Reviews code for quality
mode: subagent
tools:
  write: false
  edit: false
---
You are a code reviewer."""

        info = AgentInfo.from_markdown(content)
        assert info.name == "code-reviewer"
        assert info.mode == AgentMode.SUBAGENT
        assert "code reviewer" in info.prompt.lower()

    def test_agent_info_to_markdown(self):
        """Test exporting AgentInfo to markdown."""
        info = AgentInfo(
            name="test-agent",
            description="Test agent",
            mode=AgentMode.PRIMARY,
            prompt="Test prompt",
        )

        markdown = info.to_markdown()
        assert "name: test-agent" in markdown
        assert "Test prompt" in markdown

    def test_agent_registry(self):
        """Test AgentRegistry functionality."""
        registry = AgentRegistry.get_instance()
        registry._agents = {}

        info = AgentInfo(name="registered-agent", mode=AgentMode.PRIMARY)
        registry.register(info)

        assert registry.get("registered-agent") is not None
        assert len(registry.list()) >= 1

    def test_agent_registry_defaults(self):
        """Test registering default agents."""
        registry = AgentRegistry.register_defaults()

        build_agent = registry.get("build")
        assert build_agent is not None
        assert build_agent.mode == AgentMode.PRIMARY

        plan_agent = registry.get("plan")
        assert plan_agent is not None


class TestExecutionEngine:
    """Tests for Execution Engine."""

    @pytest.mark.asyncio
    async def test_execution_step(self):
        """Test execution step lifecycle."""
        step = ExecutionStep(step_id="test-1", step_type="thinking", content=None)

        assert step.status == ExecutionStatus.PENDING

        step.complete("result")
        assert step.status == ExecutionStatus.SUCCESS
        assert step.content == "result"
        assert step.end_time is not None

    @pytest.mark.asyncio
    async def test_execution_engine_simple(self):
        """Test simple execution loop."""
        engine = ExecutionEngine(max_steps=2)

        think_calls = 0
        act_calls = 0

        async def think_func(x):
            nonlocal think_calls
            think_calls += 1
            return f"thought_{think_calls}"

        async def act_func(x):
            nonlocal act_calls
            act_calls += 1
            return f"action_{act_calls}"

        async def verify_func(x):
            return (True, None)

        result = await engine.execute(
            initial_input="test_input",
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert think_calls == 1
        assert act_calls == 1

    @pytest.mark.asyncio
    async def test_execution_engine_with_retry(self):
        """Test execution with retries."""
        engine = ExecutionEngine(max_steps=5)

        call_count = 0

        async def think_func(x):
            return "thinking"

        async def act_func(x):
            nonlocal call_count
            call_count += 1
            return f"action_{call_count}"

        async def verify_func(x):
            nonlocal call_count
            return (call_count >= 3, "not done yet") if call_count < 3 else (True, None)

        result = await engine.execute(
            initial_input="test_input",
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execution_hooks(self):
        """Test execution hooks."""
        hooks = ExecutionHooks()

        events = []

        async def capture_event(event_name):
            def handler(*args, **kwargs):
                events.append(event_name)

            return handler

        hooks.on("before_thinking", lambda *a, **k: events.append("before_thinking"))
        hooks.on("after_thinking", lambda *a, **k: events.append("after_thinking"))

        engine = ExecutionEngine(max_steps=1, hooks=hooks)

        result = await engine.execute(
            initial_input="test",
            think_func=lambda x: "thought",
            act_func=lambda x: "action",
        )

        assert "before_thinking" in events
        assert "after_thinking" in events


class TestSessionManager:
    """Tests for Session Manager."""

    @pytest.mark.asyncio
    async def test_session_creation(self):
        """Test creating a session."""
        manager = SessionManager()

        session_id = await manager.create_session("test-session-1", "test-agent")

        assert session_id == "test-session-1"

        session = await manager.get_session("test-session-1")
        assert session is not None
        assert session["agent_id"] == "test-agent"

    @pytest.mark.asyncio
    async def test_session_state_update(self):
        """Test updating session state."""
        manager = SessionManager()

        await manager.create_session("test-session-2", "test-agent")
        await manager.update_state("test-session-2", {"key": "value"})

        session = await manager.get_session("test-session-2")
        assert session["state"]["key"] == "value"


class TestToolExecutor:
    """Tests for Tool Executor."""

    @pytest.mark.asyncio
    async def test_tool_registration(self):
        """Test registering tools."""
        executor = ToolExecutor()

        def my_tool(x):
            return f"result: {x}"

        executor.register_tool("my_tool", my_tool)

        success, result = await executor.execute("my_tool", "test")
        assert success
        assert result == "result: test"

    @pytest.mark.asyncio
    async def test_tool_with_permission_deny(self):
        """Test tool execution with permission deny."""
        ruleset = PermissionRuleset.from_config({"my_tool": "deny"})
        executor = ToolExecutor(permission_ruleset=ruleset)

        def my_tool(x):
            return "result"

        executor.register_tool("my_tool", my_tool)

        success, result = await executor.execute("my_tool", "test")
        assert not success
        assert "denied" in result.lower()


class TestPromptSystem:
    """Tests for Prompt System."""

    def test_system_prompt_builder(self):
        """Test SystemPromptBuilder."""
        prompt = (
            SystemPromptBuilder()
            .role("Code Reviewer")
            .goal("Review code for quality")
            .constraints(["Be constructive", "Focus on important issues"])
            .build()
        )

        assert "Code Reviewer" in prompt
        assert "Review code for quality" in prompt
        assert "Be constructive" in prompt

    def test_prompt_template_rendering(self):
        """Test PromptTemplate rendering."""
        template = PromptTemplate(
            template="Hello {{ name }}!",
            variables={"name": PromptVariable(name="name", default="World")},
        )

        result = template.render(name="Agent")
        assert "Agent" in result

    def test_agent_profile_from_markdown(self):
        """Test parsing AgentProfile from markdown."""
        content = """---
name: Test Agent
role: A test agent
goal: Test functionality
constraints:
  - Be helpful
  - Be accurate
temperature: 0.5
---
You are a test agent for testing purposes."""

        profile = AgentProfile.from_markdown(content)
        assert profile.name == "Test Agent"
        assert profile.role == "A test agent"
        assert profile.goal == "Test functionality"
        assert len(profile.constraints) == 2

    def test_agent_profile_build_system_prompt(self):
        """Test building system prompt from profile."""
        profile = AgentProfile(
            name="Test Agent",
            role="A test agent",
            goal="Test functionality",
            constraints=["Be helpful"],
            language="zh",
        )

        prompt = profile.build_system_prompt(tools=["read", "write"])

        assert "A test agent" in prompt
        assert "Test functionality" in prompt

    def test_compose_prompts(self):
        """Test composing multiple prompts."""
        result = compose_prompts("First", "Second", "Third")

        assert "First" in result
        assert "Second" in result
        assert "Third" in result


class TestToolDecorator:
    """Tests for tool decorator."""

    def test_tool_decorator_basic(self):
        """Test basic tool decorator."""

        @tool("my_custom_tool")
        def my_custom_tool(x: str) -> str:
            return f"processed: {x}"

        assert hasattr(my_custom_tool, "_tool_name")
        assert my_custom_tool._tool_name == "my_custom_tool"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
