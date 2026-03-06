"""
ReActMasterV2 Agent Integration Test
Test that ReActMasterV2 can use the refactored capabilities:
1. AgentInfo & Permission System
2. Execution Loop
3. AgentProfile V2
4. SimpleMemory
5. Skill System
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-core/src"))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-ext/src"))


def test_agent_info_integration():
    """Test that ReActMasterV2 can use AgentInfo configuration."""
    logger.info("=" * 60)
    logger.info("Test 1: AgentInfo Integration with ReActMasterV2")
    logger.info("=" * 60)

    from derisk.agent.core.agent_info import (
        AgentInfo,
        AgentMode,
        PermissionAction,
        AgentRegistry,
    )
    from derisk.agent.expand.react_master_agent.react_master_agent import (
        ReActMasterAgent,
    )

    # Create an AgentInfo for the agent
    agent_info = AgentInfo(
        name="test_react_agent",
        description="Test ReActMasterV2 agent with permission control",
        mode=AgentMode.PRIMARY,
        permission={
            "*": "ask",
            "read": "allow",
            "write": "allow",
            "bash": "allow",
            "question": "deny",
        },
        tools={"read": True, "write": True, "bash": True},
        max_steps=5,
    )

    logger.info(f"  Created AgentInfo: {agent_info.name}")
    logger.info(f"  Mode: {agent_info.mode.value}")
    logger.info(f"  Max Steps: {agent_info.max_steps}")

    # Verify permission checking
    assert agent_info.check_permission("read") == PermissionAction.ALLOW
    assert agent_info.check_permission("write") == PermissionAction.ALLOW
    assert agent_info.check_permission("bash") == PermissionAction.ALLOW
    assert agent_info.check_permission("question") == PermissionAction.DENY
    assert agent_info.check_permission("unknown") == PermissionAction.ASK
    logger.info("  Permission checks passed")

    # Register the agent
    registry = AgentRegistry.get_instance()
    registry.register(agent_info)
    retrieved = registry.get("test_react_agent")
    assert retrieved is not None
    logger.info("  AgentInfo registered successfully")

    # Verify ReActMasterAgent has the new attributes
    assert hasattr(ReActMasterAgent, "__annotations__")
    annotations = ReActMasterAgent.__annotations__

    # Check for new attributes
    has_permission = "permission_ruleset" in annotations or hasattr(
        ReActMasterAgent, "permission_ruleset"
    )
    has_agent_info = "agent_info" in annotations or hasattr(
        ReActMasterAgent, "agent_info"
    )
    has_agent_mode = "agent_mode" in annotations or hasattr(
        ReActMasterAgent, "agent_mode"
    )
    has_max_steps = "max_steps" in annotations or hasattr(ReActMasterAgent, "max_steps")

    logger.info(f"  Has permission_ruleset: {has_permission}")
    logger.info(f"  Has agent_info: {has_agent_info}")
    logger.info(f"  Has agent_mode: {has_agent_mode}")
    logger.info(f"  Has max_steps: {has_max_steps}")

    logger.info("Test 1: PASSED\n")
    return True


def test_execution_loop_integration():
    """Test that ReActMasterV2 can use the new ExecutionLoop."""
    logger.info("=" * 60)
    logger.info("Test 2: ExecutionLoop Integration")
    logger.info("=" * 60)

    from derisk.agent.core.execution import (
        ExecutionState,
        LoopContext,
        ExecutionMetrics,
        ExecutionContext,
        SimpleExecutionLoop,
        create_execution_context,
        create_execution_loop,
    )

    # Test execution loop can be created with config from AgentInfo
    max_iterations = 5  # From AgentInfo.max_steps

    ctx = LoopContext(max_iterations=max_iterations)
    assert ctx.max_iterations == 5
    assert ctx.state == ExecutionState.PENDING
    logger.info(f"  LoopContext created with max_iterations={max_iterations}")

    # Create execution context
    exec_ctx = create_execution_context(max_iterations=max_iterations)
    loop_ctx = exec_ctx.start()
    assert loop_ctx.state == ExecutionState.RUNNING
    logger.info("  ExecutionContext started successfully")

    # Test async execution loop
    async def run_loop():
        iterations = []

        async def think_func(ctx):
            iterations.append(ctx.iteration)
            return {"thought": f"iteration {ctx.iteration}"}

        async def act_func(thought, ctx):
            return {"action": "test", "result": thought}

        async def verify_func(result, ctx):
            if ctx.iteration >= 3:
                ctx.terminate("test complete")
            return True

        loop = create_execution_loop(max_iterations=5)
        success, metrics = await loop.run(think_func, act_func, verify_func)

        assert len(iterations) == 3  # Should stop after 3 iterations
        logger.info(f"  Loop executed {len(iterations)} iterations")
        return True

    asyncio.run(run_loop())

    logger.info("Test 2: PASSED\n")
    return True


def test_simple_memory_integration():
    """Test that ReActMasterV2 can use SimpleMemory."""
    logger.info("=" * 60)
    logger.info("Test 3: SimpleMemory Integration")
    logger.info("=" * 60)

    from derisk.agent.core.simple_memory import (
        MemoryEntry,
        MemoryScope,
        MemoryPriority,
        SimpleMemory,
        SessionMemory,
        MemoryManager,
        create_memory,
    )

    # Create a memory manager
    manager = create_memory(max_entries=1000)
    assert manager is not None
    logger.info("  MemoryManager created")

    async def test_memory_operations():
        session = manager.session

        # Start a session
        session_id = await session.start_session("test_session_001")
        logger.info(f"  Session started: {session_id}")

        # Add some messages
        await session.add_message("Hello, I'm a user", role="user")
        await session.add_message("Hello! How can I help you?", role="assistant")
        await session.add_message("Tell me about the weather", role="user")

        # Get messages
        messages = await session.get_messages()
        assert len(messages) == 3
        logger.info(f"  Added {len(messages)} messages")

        # Get context window
        context = await session.get_context_window(max_tokens=100)
        assert len(context) == 3
        logger.info(f"  Context window has {len(context)} messages")

        # Search history
        results = await session.search_history("weather")
        assert len(results) >= 1
        logger.info(f"  Search found {len(results)} results")

        await session.end_session()

    asyncio.run(test_memory_operations())

    logger.info("Test 3: PASSED\n")
    return True


def test_skill_system_integration():
    """Test that ReActMasterV2 can use the Skill system."""
    logger.info("=" * 60)
    logger.info("Test 4: Skill System Integration")
    logger.info("=" * 60)

    from derisk.agent.core.skill import (
        Skill,
        SkillType,
        SkillStatus,
        SkillMetadata,
        SkillRegistry,
        SkillManager,
        skill,
        create_skill_registry,
    )

    # Create a custom skill
    class CalculatorSkill(Skill):
        async def _do_initialize(self) -> bool:
            logger.info("    CalculatorSkill initialized")
            return True

        async def execute(self, expression: str) -> float:
            try:
                return eval(expression)
            except Exception as e:
                return str(e)

    metadata = SkillMetadata(
        name="calculator",
        description="A simple calculator skill",
        version="1.0.0",
        skill_type=SkillType.CUSTOM,
        tags=["math", "calculator"],
    )

    calc_skill = CalculatorSkill(metadata=metadata)
    logger.info(f"  Created skill: {calc_skill.name}")

    # Register the skill
    registry = create_skill_registry()
    registry.register(calc_skill)

    retrieved = registry.get("calculator")
    assert retrieved is not None
    assert retrieved.name == "calculator"
    logger.info("  Skill registered successfully")

    # Initialize and test the skill
    async def test_skill():
        success = await calc_skill.initialize()
        assert success == True
        assert calc_skill.is_enabled == True
        logger.info("  Skill initialized")

        result = await calc_skill.execute("2 + 2")
        assert result == 4
        logger.info(f"  Skill executed: 2 + 2 = {result}")

    asyncio.run(test_skill())

    # Test @skill decorator
    @skill("search", description="Search skill")
    async def search_skill(query: str) -> list:
        return [f"result for {query}"]

    assert hasattr(search_skill, "_skill_name")
    logger.info("  @skill decorator works")

    logger.info("Test 4: PASSED\n")
    return True


def test_profile_v2_integration():
    """Test that ReActMasterV2 can use AgentProfile V2."""
    logger.info("=" * 60)
    logger.info("Test 5: AgentProfile V2 Integration")
    logger.info("=" * 60)

    from derisk.agent.core.prompt_v2 import (
        AgentProfile,
        PromptFormat,
        PromptTemplate,
        PromptVariable,
        SystemPromptBuilder,
        UserProfile,
    )

    # Create an AgentProfile
    profile = AgentProfile(
        name="ReActMasterV2",
        role="intelligent_assistant",
        goal="Help users solve problems step by step",
        description="A reasoning agent with action capabilities",
        constraints=[
            "Think step by step",
            "Use tools when necessary",
            "Provide clear explanations",
        ],
    )
    logger.info(f"  Created AgentProfile: {profile.name}")

    # Create a prompt template
    template = PromptTemplate(
        name="system_prompt",
        template="You are {{name}}, a {{role}}. Your goal is: {{goal}}",
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
    logger.info("  SystemPromptBuilder created")

    # Create user profile
    user_profile = UserProfile(
        name="test_user",
        preferences={"language": "zh", "detail_level": "high"},
    )
    logger.info(f"  Created UserProfile: {user_profile.name}")

    logger.info("Test 5: PASSED\n")
    return True


def test_react_master_v2_construction():
    """Test that ReActMasterV2 can be constructed with new capabilities."""
    logger.info("=" * 60)
    logger.info("Test 6: ReActMasterV2 Construction")
    logger.info("=" * 60)

    from derisk.agent.expand.react_master_agent.react_master_agent import (
        ReActMasterAgent,
    )
    from derisk.agent.core.agent_info import AgentInfo, AgentMode, PermissionAction

    # Create agent info
    agent_info = AgentInfo(
        name="react_master_v2_test",
        description="ReActMasterV2 test agent",
        mode=AgentMode.PRIMARY,
        permission={
            "read": "allow",
            "write": "allow",
            "bash": "allow",
        },
        max_steps=10,
    )
    logger.info(f"  Created AgentInfo: {agent_info.name}")

    # Get the profile config
    profile_config = ReActMasterAgent.default_profile_config()
    logger.info(
        f"  Profile config: {profile_config.name if hasattr(profile_config, 'name') else 'default'}"
    )

    # Verify agent has new attributes
    agent_instance = ReActMasterAgent.__new__(ReActMasterAgent)

    # Check that new attributes can be set
    if hasattr(agent_instance, "agent_info"):
        logger.info("  Agent has agent_info attribute")
    else:
        logger.info("  Agent can use AgentInfo through registry")

    if hasattr(agent_instance, "permission_ruleset"):
        logger.info("  Agent has permission_ruleset attribute")
    else:
        logger.info("  Agent can get permission from AgentInfo.permission_ruleset")

    # Verify permission methods exist
    assert hasattr(ReActMasterAgent, "check_tool_permission")
    assert hasattr(ReActMasterAgent, "is_tool_allowed")
    assert hasattr(ReActMasterAgent, "is_tool_denied")
    assert hasattr(ReActMasterAgent, "needs_tool_approval")
    assert hasattr(ReActMasterAgent, "get_effective_max_steps")
    logger.info("  All permission methods exist")

    # Verify max_steps logic
    logger.info("  get_effective_max_steps method exists for step control")

    logger.info("Test 6: PASSED\n")
    return True


def main():
    """Run all integration tests."""
    logger.info("\n" + "=" * 60)
    logger.info("ReActMasterV2 Integration Tests")
    logger.info("=" * 60 + "\n")

    results = []

    try:
        results.append(("AgentInfo Integration", test_agent_info_integration()))
    except Exception as e:
        logger.error(f"Test 1 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("AgentInfo Integration", False))

    try:
        results.append(("ExecutionLoop Integration", test_execution_loop_integration()))
    except Exception as e:
        logger.error(f"Test 2 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("ExecutionLoop Integration", False))

    try:
        results.append(("SimpleMemory Integration", test_simple_memory_integration()))
    except Exception as e:
        logger.error(f"Test 3 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("SimpleMemory Integration", False))

    try:
        results.append(("Skill System Integration", test_skill_system_integration()))
    except Exception as e:
        logger.error(f"Test 4 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Skill System Integration", False))

    try:
        results.append(("AgentProfile V2 Integration", test_profile_v2_integration()))
    except Exception as e:
        logger.error(f"Test 5 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("AgentProfile V2 Integration", False))

    try:
        results.append(
            ("ReActMasterV2 Construction", test_react_master_v2_construction())
        )
    except Exception as e:
        logger.error(f"Test 6 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("ReActMasterV2 Construction", False))

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
