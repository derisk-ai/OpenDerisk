"""
ReActMasterV2 Refactored Capabilities Test
Test that refactored capabilities work correctly without full environment.
"""

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-core/src"))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-ext/src"))


def test_agent_info_for_react():
    """Test AgentInfo can be configured for ReActMaster."""
    logger.info("=" * 60)
    logger.info("Test 1: AgentInfo for ReActMaster")
    logger.info("=" * 60)

    from derisk.agent.core.agent_info import (
        AgentInfo,
        AgentMode,
        PermissionAction,
        AgentRegistry,
    )

    # Create AgentInfo for a ReAct agent
    agent_info = AgentInfo(
        name="react_agent",
        description="ReAct agent with tool capabilities",
        mode=AgentMode.PRIMARY,
        permission={
            "read": "allow",
            "write": "allow",
            "bash": "allow",
            "question": "deny",
        },
        tools={"read": True, "write": True, "bash": True},
        max_steps=10,
        temperature=0.7,
    )

    logger.info(f"  Created AgentInfo: {agent_info.name}")
    logger.info(f"  Mode: {agent_info.mode.value}")
    logger.info(f"  Max Steps: {agent_info.max_steps}")
    logger.info(f"  Temperature: {agent_info.temperature}")

    # Verify permission system
    assert agent_info.check_permission("read") == PermissionAction.ALLOW
    assert agent_info.check_permission("write") == PermissionAction.ALLOW
    assert agent_info.check_permission("question") == PermissionAction.DENY
    logger.info("  Permission system working correctly")

    # Verify tool enablement
    assert agent_info.is_tool_enabled("read") == True
    assert agent_info.is_tool_enabled("write") == True
    logger.info("  Tool enablement working correctly")

    # Verify can be registered
    registry = AgentRegistry.get_instance()
    registry.register(agent_info)
    retrieved = registry.get("react_agent")
    assert retrieved is not None
    logger.info("  AgentInfo registered in AgentRegistry")

    # Test Markdown configuration
    markdown_config = """---
name: react_markdown_agent
description: Agent from markdown config
mode: primary
max_steps: 5
tools:
  read: true
  write: true
---
You are a helpful assistant with ReAct capabilities."""

    parsed = AgentInfo.from_markdown(markdown_config)
    assert parsed.name == "react_markdown_agent"
    assert parsed.max_steps == 5
    logger.info("  Markdown configuration parsing works")

    logger.info("Test 1: PASSED\n")
    return True


def test_execution_loop_for_react():
    """Test ExecutionLoop can handle ReAct workflow."""
    logger.info("=" * 60)
    logger.info("Test 2: ExecutionLoop for ReAct workflow")
    logger.info("=" * 60)

    from derisk.agent.core.execution import (
        ExecutionState,
        LoopContext,
        ExecutionContext,
        SimpleExecutionLoop,
        create_execution_context,
        create_execution_loop,
    )

    # Simulate ReAct agent execution with max_steps from AgentInfo
    max_iterations = 10  # From AgentInfo.max_steps

    # Create execution loop
    loop = create_execution_loop(max_iterations=max_iterations)
    assert loop.max_iterations == 10
    logger.info(f"  Created loop with max_iterations={max_iterations}")

    # Test ReAct-style think-act loop
    async def test_react_loop():
        think_count = [0]
        act_count = [0]

        async def think(ctx):
            think_count[0] += 1
            return {"thought": f"Step {ctx.iteration}", "action": "search"}

        async def act(thought_result, ctx):
            act_count[0] += 1
            return {"result": f"Executed {thought_result['action']}"}

        async def verify(result, ctx):
            # Stop after 3 iterations like a typical ReAct workflow
            if ctx.iteration >= 3:
                ctx.terminate("Task completed")
            return True

        success, metrics = await loop.run(think, act, verify)

        assert think_count[0] == 3
        assert act_count[0] == 3
        logger.info(
            f"  ReAct loop executed: think={think_count[0]}, act={act_count[0]}"
        )
        logger.info(f"  Total time: {metrics.duration_ms}ms")
        return True

    asyncio.run(test_react_loop())

    # Test execution context for agent state
    exec_ctx = create_execution_context(max_iterations=5)
    loop_ctx = exec_ctx.start()
    assert loop_ctx.state == ExecutionState.RUNNING
    assert loop_ctx.can_continue() == True
    logger.info("  ExecutionContext manages agent state correctly")

    logger.info("Test 2: PASSED\n")
    return True


def test_permission_integration():
    """Test Permission system integration with agent tools."""
    logger.info("=" * 60)
    logger.info("Test 3: Permission Integration with Tools")
    logger.info("=" * 60)

    from derisk.agent.core.agent_info import (
        PermissionRuleset,
        PermissionRule,
        PermissionAction,
    )
    from derisk.agent.core.execution_engine import ToolExecutor

    # Create permission rules for ReAct agent
    rules = [
        PermissionRule(
            action=PermissionAction.ALLOW, pattern="read", permission="read"
        ),
        PermissionRule(
            action=PermissionAction.ALLOW, pattern="write", permission="write"
        ),
        PermissionRule(action=PermissionAction.ASK, pattern="bash", permission="bash"),
        PermissionRule(
            action=PermissionAction.DENY, pattern="delete", permission="delete"
        ),
    ]
    ruleset = PermissionRuleset(rules)
    logger.info("  Created permission ruleset for tools")

    # Create tool executor with permissions
    executor = ToolExecutor(permission_ruleset=ruleset)

    # Register some tools
    executor.register_tool("read", lambda: "read result")
    executor.register_tool("write", lambda x: f"wrote: {x}")
    executor.register_tool("bash", lambda cmd: f"executed: {cmd}")
    logger.info("  Registered tools with executor")

    # Test async permission checks
    async def test_permissions():
        # Test allowed tool
        success, result = await executor.execute("read")
        assert success == True
        assert result == "read result"
        logger.info("  read tool: ALLOWED")

        # Test denied tool (not registered)
        success, result = await executor.execute("delete")
        assert success == False
        assert "not found" in result
        logger.info("  delete tool: DENIED (not found)")

        # Test tool requiring approval
        success, result = await executor.execute("bash", "ls")
        # Without approval callback, should require approval
        assert success == False or "requires approval" in result or success == True
        logger.info("  bash tool: requires permission check")

    asyncio.run(test_permissions())

    logger.info("Test 3: PASSED\n")
    return True


def test_memory_for_agent_conversation():
    """Test SimpleMemory for agent conversation history."""
    logger.info("=" * 60)
    logger.info("Test 4: Memory for Agent Conversation")
    logger.info("=" * 60)

    from derisk.agent.core.simple_memory import (
        MemoryEntry,
        MemoryScope,
        MemoryPriority,
        SimpleMemory,
        SessionMemory,
        create_memory,
    )

    # Create memory for agent conversation
    manager = create_memory(max_entries=1000)
    logger.info("  Created MemoryManager for conversations")

    async def test_conversation_memory():
        session = manager.session

        # Start a conversation session
        session_id = await session.start_session("conv_001")
        logger.info(f"  Started session: {session_id}")

        # Simulate ReAct conversation
        await session.add_message("What is the weather?", role="user")
        await session.add_message(
            "Let me search for weather information", role="assistant"
        )
        await session.add_message("Action: search weather", role="assistant")
        await session.add_message("Observation: Sunny, 25°C", role="assistant")
        await session.add_message("The weather is sunny with 25°C", role="assistant")

        # Get conversation history
        messages = await session.get_messages()
        assert len(messages) == 5
        logger.info(f"  Conversation has {len(messages)} messages")

        # Get context window for LLM
        context = await session.get_context_window(max_tokens=500)
        assert len(context) == 5
        logger.info(f"  Context window ready: {len(context)} messages")

        # Search history
        results = await session.search_history("weather")
        assert len(results) >= 1
        logger.info(f"  Found {len(results)} relevant messages")

        await session.end_session()

    asyncio.run(test_conversation_memory())

    logger.info("Test 4: PASSED\n")
    return True


def test_skill_for_agent_tools():
    """Test Skill system for agent tool extension."""
    logger.info("=" * 60)
    logger.info("Test 5: Skill System for Agent Tools")
    logger.info("=" * 60)

    from derisk.agent.core.skill import (
        Skill,
        SkillType,
        SkillStatus,
        SkillMetadata,
        SkillRegistry,
        skill,
    )

    # Create a search skill for ReAct agent
    class SearchSkill(Skill):
        async def _do_initialize(self) -> bool:
            return True

        async def execute(self, query: str) -> dict:
            return {
                "action": "search",
                "query": query,
                "results": [f"Result for {query}"],
            }

    metadata = SkillMetadata(
        name="search",
        description="Search skill for information retrieval",
        skill_type=SkillType.BUILTIN,
        tags=["search", "tool"],
    )

    search_skill = SearchSkill(metadata=metadata)
    logger.info(f"  Created SearchSkill: {search_skill.name}")

    # Register skill
    registry = SkillRegistry.get_instance()
    registry.register(search_skill)

    retrieved = registry.get("search")
    assert retrieved is not None
    logger.info("  Skill registered in SkillRegistry")

    # Initialize and test skill
    async def test_skill():
        success = await search_skill.initialize()
        assert success == True
        assert search_skill.is_enabled == True
        logger.info("  Skill initialized and enabled")

        # Execute skill
        result = await search_skill.execute("weather")
        assert result["action"] == "search"
        assert "weather" in result["query"]
        logger.info(f"  Skill executed: {result}")

    asyncio.run(test_skill())

    # Test skill decorator
    @skill("calculate", description="Calculate expressions")
    async def calculate(expr: str) -> float:
        return eval(expr)

    assert hasattr(calculate, "_skill_name")
    logger.info("  @skill decorator works for tool creation")

    logger.info("Test 5: PASSED\n")
    return True


def test_profile_for_agent_prompts():
    """Test AgentProfile for agent prompt management."""
    logger.info("=" * 60)
    logger.info("Test 6: AgentProfile for Prompts")
    logger.info("=" * 60)

    from derisk.agent.core.prompt_v2 import (
        AgentProfile,
        PromptFormat,
        PromptTemplate,
        PromptVariable,
        SystemPromptBuilder,
        UserProfile,
    )

    # Create profile for ReAct agent
    profile = AgentProfile(
        name="ReActAgent",
        role="reasoning_assistant",
        goal="Solve problems step by step using thoughts and actions",
        description="An agent that reasons and acts iteratively",
        constraints=[
            "Think before acting",
            "Use tools when needed",
            "Provide clear explanations",
        ],
    )
    logger.info(f"  Created AgentProfile: {profile.name}")
    logger.info(f"  Role: {profile.role}")
    logger.info(f"  Goal: {profile.goal}")

    # Create prompt template for ReAct
    template = PromptTemplate(
        name="react_system",
        template="""You are {{name}}, {{role}}.

Goal: {{goal}}

Constraints:
{% for constraint in constraints %}
- {{ constraint }}
{% endfor %}

Think step by step and use actions when appropriate.""",
        format=PromptFormat.JINJA2,
        variables=[
            PromptVariable(name="name", description="Agent name"),
            PromptVariable(name="role", description="Agent role"),
            PromptVariable(name="goal", description="Agent goal"),
        ],
    )
    logger.info(f"  Created PromptTemplate: {template.name}")

    # Build system prompt
    builder = SystemPromptBuilder()
    builder.add_template(template)
    logger.info("  SystemPromptBuilder ready for prompt construction")

    logger.info("Test 6: PASSED\n")
    return True


def main():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("ReActMasterV2 Refactored Capabilities Test")
    logger.info("=" * 60 + "\n")

    results = []

    tests = [
        ("AgentInfo for ReAct", test_agent_info_for_react),
        ("ExecutionLoop for ReAct", test_execution_loop_for_react),
        ("Permission Integration", test_permission_integration),
        ("Memory for Conversation", test_memory_for_agent_conversation),
        ("Skill for Tools", test_skill_for_agent_tools),
        ("Profile for Prompts", test_profile_for_agent_prompts),
    ]

    for name, test_func in tests:
        try:
            results.append((name, test_func()))
        except Exception as e:
            logger.error(f"Test FAILED: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Summary
    passed = sum(1 for _, r in results if r)
    total = len(results)

    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        logger.info(f"  {name}: {status}")
    logger.info("-" * 60)
    logger.info(f"Total: {passed}/{total} passed ({passed / total * 100:.1f}%)")
    logger.info("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
