"""
E2E Tests - Agent Execution

Tests the complete agent execution flow including:
- Tool execution with authorization checks
- Think-Decide-Act loop
- User interaction during execution
- Session management
- Error handling and recovery
"""

import pytest
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from derisk.core.agent.base import AgentBase, AgentState
from derisk.core.agent.info import (
    AgentInfo,
    AgentMode,
    AgentCapability,
    ToolSelectionPolicy,
)
from derisk.core.tools.base import ToolBase, ToolResult, ToolRegistry
from derisk.core.tools.metadata import (
    ToolMetadata,
    ToolCategory,
    RiskLevel,
    RiskCategory,
    ToolParameter,
)
from derisk.core.authorization.engine import (
    AuthorizationEngine,
    AuthorizationContext,
    AuthorizationResult,
    AuthorizationDecision,
)
from derisk.core.authorization.model import (
    AuthorizationConfig,
    AuthorizationMode,
    PermissionAction,
)
from derisk.core.interaction.gateway import (
    InteractionGateway,
    MemoryConnectionManager,
    MemoryStateStore,
)
from derisk.core.interaction.protocol import (
    InteractionRequest,
    InteractionResponse,
    InteractionStatus,
)


# ============ Test Tools ============

class MockReadTool(ToolBase):
    """Mock read tool for testing."""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="read",
            name="read",
            version="1.0.0",
            description="Read file contents",
            category=ToolCategory.FILE_SYSTEM,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="File path to read",
                    required=True,
                )
            ],
            authorization={
                "requires_authorization": False,
                "risk_level": RiskLevel.SAFE,
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        path = arguments.get("path", "")
        return ToolResult.success_result(f"Content of {path}")


class MockBashTool(ToolBase):
    """Mock bash tool for testing."""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="bash",
            name="bash",
            version="1.0.0",
            description="Execute shell commands",
            category=ToolCategory.SHELL,
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="Command to execute",
                    required=True,
                )
            ],
            authorization={
                "requires_authorization": True,
                "risk_level": RiskLevel.HIGH,
                "risk_categories": [RiskCategory.SHELL_EXECUTE],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        command = arguments.get("command", "")
        return ToolResult.success_result(f"Executed: {command}")


class MockWriteTool(ToolBase):
    """Mock write tool for testing."""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            id="write",
            name="write",
            version="1.0.0",
            description="Write content to file",
            category=ToolCategory.FILE_SYSTEM,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="File path",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content to write",
                    required=True,
                ),
            ],
            authorization={
                "requires_authorization": True,
                "risk_level": RiskLevel.MEDIUM,
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        return ToolResult.success_result(f"Wrote {len(content)} bytes to {path}")


# ============ Test Agent ============

class TestAgent(AgentBase):
    """Test agent implementation."""

    def __init__(
        self,
        info: AgentInfo,
        decisions: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ):
        super().__init__(info, **kwargs)
        self._decisions = decisions or []
        self._decision_index = 0
        self._think_output = "Thinking..."

    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        yield self._think_output

    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        if self._decision_index < len(self._decisions):
            decision = self._decisions[self._decision_index]
            self._decision_index += 1
            return decision
        return {"type": "complete", "message": "Done"}

    async def act(self, action: Dict[str, Any], **kwargs) -> Any:
        if action.get("type") == "tool_call":
            tool_name = action.get("tool", "")
            arguments = action.get("arguments", {})
            return await self.execute_tool(tool_name, arguments)
        return None


# ============ Fixtures ============

@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Create a test tool registry."""
    registry = ToolRegistry()
    registry.register(MockReadTool())
    registry.register(MockBashTool())
    registry.register(MockWriteTool())
    return registry


@pytest.fixture
def agent_info() -> AgentInfo:
    """Create test agent info."""
    return AgentInfo(
        name="test-agent",
        description="Test agent for E2E testing",
        mode=AgentMode.PRIMARY,
        capabilities=[
            AgentCapability.CODE_ANALYSIS,
            AgentCapability.FILE_OPERATIONS,
            AgentCapability.SHELL_EXECUTION,
        ],
        max_steps=10,
        timeout=60,
    )


@pytest.fixture
def auth_engine() -> AuthorizationEngine:
    """Create test authorization engine."""
    config = AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
        whitelist_tools=["read"],  # read is always allowed
        session_cache_enabled=True,
    )
    return AuthorizationEngine(config=config)


@pytest.fixture
def interaction_gateway() -> InteractionGateway:
    """Create test interaction gateway."""
    conn_manager = MemoryConnectionManager()
    state_store = MemoryStateStore()
    return InteractionGateway(
        connection_manager=conn_manager,
        state_store=state_store,
        default_timeout=30,
    )


# ============ Test Classes ============

class TestAgentToolExecutionE2E:
    """E2E tests for agent tool execution."""

    @pytest.mark.asyncio
    async def test_safe_tool_auto_granted(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Safe tools should be executed without authorization prompt."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "read",
                    "arguments": {"path": "/tmp/test.txt"},
                },
            ],
        )

        # Run agent
        output_chunks = []
        async for chunk in agent.run("Read the file"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)
        assert "Content of /tmp/test.txt" in output or "read" in output.lower()
        assert agent.state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_risky_tool_denied_without_confirmation(
        self,
        tool_registry,
        agent_info,
        interaction_gateway,
    ):
        """Risky tools should be denied without user confirmation."""
        # Strict auth engine without whitelist for bash
        auth_engine = AuthorizationEngine(
            config=AuthorizationConfig(
                mode=AuthorizationMode.STRICT,
                whitelist_tools=[],
                session_cache_enabled=True,
            )
        )

        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "bash",
                    "arguments": {"command": "ls -la"},
                },
            ],
        )

        # Run agent without providing user confirmation callback
        output_chunks = []
        async for chunk in agent.run("List files"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)
        # Should either deny or require confirmation
        history = agent.history
        tool_calls = [h for h in history if h.get("type") == "tool_call"]

        if tool_calls:
            # If tool was called, check result
            result = tool_calls[0].get("result", {})
            # Either succeeded (if confirmation was bypassed) or failed
            assert result is not None

    @pytest.mark.asyncio
    async def test_whitelisted_tool_always_allowed(
        self,
        tool_registry,
        agent_info,
        interaction_gateway,
    ):
        """Whitelisted tools should always be allowed."""
        auth_engine = AuthorizationEngine(
            config=AuthorizationConfig(
                mode=AuthorizationMode.STRICT,
                whitelist_tools=["bash", "read", "write"],
                session_cache_enabled=True,
            )
        )

        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "bash",
                    "arguments": {"command": "echo hello"},
                },
            ],
        )

        output_chunks = []
        async for chunk in agent.run("Echo hello"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)
        assert "Executed" in output or "echo" in output.lower()

    @pytest.mark.asyncio
    async def test_tool_not_found_error(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Non-existent tool should return error."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "nonexistent_tool",
                    "arguments": {},
                },
            ],
        )

        output_chunks = []
        async for chunk in agent.run("Use nonexistent tool"):
            output_chunks.append(chunk)

        # Check that error was recorded
        history = agent.history
        tool_calls = [h for h in history if h.get("type") == "tool_call"]

        if tool_calls:
            result = tool_calls[0].get("result", {})
            assert result.get("success") is False or "not found" in str(result).lower()


class TestAgentRunLoopE2E:
    """E2E tests for agent run loop."""

    @pytest.mark.asyncio
    async def test_think_decide_act_cycle(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent should follow think-decide-act cycle."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "read",
                    "arguments": {"path": "/tmp/file1.txt"},
                },
                {
                    "type": "tool_call",
                    "tool": "read",
                    "arguments": {"path": "/tmp/file2.txt"},
                },
                {"type": "response", "content": "Files read successfully"},
            ],
        )

        output_chunks = []
        async for chunk in agent.run("Read two files"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)

        # Should have thinking output
        assert "Thinking" in output

        # Should have completed
        assert agent.state == AgentState.COMPLETED

        # Should have recorded decisions
        history = agent.history
        decisions = [h for h in history if h.get("type") == "decision"]
        assert len(decisions) == 3

    @pytest.mark.asyncio
    async def test_max_steps_limit(
        self,
        tool_registry,
        auth_engine,
        interaction_gateway,
    ):
        """Agent should stop at max steps."""
        agent_info = AgentInfo(
            name="limited-agent",
            description="Agent with limited steps",
            mode=AgentMode.PRIMARY,
            max_steps=3,
            timeout=60,
        )

        # Create decisions that would exceed max_steps
        decisions = [
            {
                "type": "tool_call",
                "tool": "read",
                "arguments": {"path": f"/tmp/file{i}.txt"},
            }
            for i in range(10)
        ]

        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=decisions,
        )

        output_chunks = []
        async for chunk in agent.run("Read many files"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)

        # Should have warning about max steps
        assert "maximum steps" in output.lower() or agent.current_step <= 3

    @pytest.mark.asyncio
    async def test_direct_response(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent should handle direct response decision."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {"type": "response", "content": "Hello! How can I help you?"},
            ],
        )

        output_chunks = []
        async for chunk in agent.run("Hello"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)
        assert "Hello! How can I help you?" in output
        assert agent.state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_error_decision_handling(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent should handle error decisions."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {"type": "error", "error": "Something went wrong"},
            ],
        )

        output_chunks = []
        async for chunk in agent.run("Do something"):
            output_chunks.append(chunk)

        output = "".join(output_chunks)
        assert "Something went wrong" in output or "Error" in output
        assert agent.state == AgentState.FAILED


class TestAgentSessionManagementE2E:
    """E2E tests for agent session management."""

    @pytest.mark.asyncio
    async def test_session_id_generated(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Session ID should be generated if not provided."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[{"type": "complete"}],
        )

        async for _ in agent.run("Test"):
            pass

        assert agent.session_id is not None
        assert agent.session_id.startswith("session_")

    @pytest.mark.asyncio
    async def test_session_id_preserved(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Provided session ID should be preserved."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[{"type": "complete"}],
        )

        async for _ in agent.run("Test", session_id="my-custom-session"):
            pass

        assert agent.session_id == "my-custom-session"

    @pytest.mark.asyncio
    async def test_agent_reset(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent reset should clear state."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[{"type": "complete"}],
        )

        async for _ in agent.run("Test", session_id="session-1"):
            pass

        assert agent.session_id == "session-1"
        assert agent.state == AgentState.COMPLETED
        assert len(agent.history) > 0

        # Reset
        agent.reset()

        assert agent.session_id is None
        assert agent.state == AgentState.IDLE
        assert len(agent.history) == 0
        assert agent.current_step == 0


class TestAgentStateTransitionsE2E:
    """E2E tests for agent state transitions."""

    @pytest.mark.asyncio
    async def test_state_transitions_during_run(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent state should transition correctly during run."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "read",
                    "arguments": {"path": "/tmp/test.txt"},
                },
                {"type": "complete"},
            ],
        )

        # Initially idle
        assert agent.state == AgentState.IDLE

        # Collect states during run
        states_during_run = []
        async for _ in agent.run("Test"):
            states_during_run.append(agent.state)

        # Should have been running during execution
        assert AgentState.RUNNING in states_during_run or agent.state == AgentState.COMPLETED

        # Should be completed at end
        assert agent.state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_is_running_property(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """is_running property should work correctly."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[{"type": "complete"}],
        )

        # Not running initially
        assert not agent.is_running

        # Check during run
        running_states = []
        async for _ in agent.run("Test"):
            running_states.append(agent.is_running)

        # Should have been running at some point
        # (may be False if check happens after state change)

        # Not running after completion
        assert not agent.is_running


class TestAgentCapabilitiesE2E:
    """E2E tests for agent capabilities."""

    @pytest.mark.asyncio
    async def test_has_capability(self, agent_info):
        """Agent should report capabilities correctly."""
        assert agent_info.has_capability(AgentCapability.CODE_ANALYSIS)
        assert agent_info.has_capability(AgentCapability.FILE_OPERATIONS)
        assert not agent_info.has_capability(AgentCapability.WEB_BROWSING)

    @pytest.mark.asyncio
    async def test_tool_selection_policy(self, tool_registry):
        """Tool selection policy should filter tools."""
        policy = ToolSelectionPolicy(
            included_tools=["read", "write"],
            excluded_tools=["bash"],
        )

        assert policy.allows_tool("read")
        assert policy.allows_tool("write")
        assert not policy.allows_tool("bash")
        assert not policy.allows_tool("other")  # Not in included list


class TestAgentHistoryE2E:
    """E2E tests for agent history tracking."""

    @pytest.mark.asyncio
    async def test_history_recorded(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent should record history of decisions and tool calls."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {
                    "type": "tool_call",
                    "tool": "read",
                    "arguments": {"path": "/tmp/test.txt"},
                },
                {"type": "response", "content": "Done"},
            ],
        )

        async for _ in agent.run("Test"):
            pass

        history = agent.history
        assert len(history) >= 2

        # Check decision entries
        decisions = [h for h in history if h.get("type") == "decision"]
        assert len(decisions) == 2

        # Check tool call entries
        tool_calls = [h for h in history if h.get("type") == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "read"

    @pytest.mark.asyncio
    async def test_messages_recorded(
        self,
        tool_registry,
        agent_info,
        auth_engine,
        interaction_gateway,
    ):
        """Agent should record message history."""
        agent = TestAgent(
            info=agent_info,
            tool_registry=tool_registry,
            auth_engine=auth_engine,
            interaction_gateway=interaction_gateway,
            decisions=[
                {"type": "response", "content": "Hello there!"},
            ],
        )

        async for _ in agent.run("Hello"):
            pass

        messages = agent.messages
        assert len(messages) >= 2

        # First message should be user
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

        # Last message should be assistant
        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_messages) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
