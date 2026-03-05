"""
Agent Core Modules Test - Quick validation for refactored modules (Sync version).
"""

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


def test_agent_info_and_permission():
    """Test AgentInfo and Permission system."""
    logger.info("=" * 60)
    logger.info("Test 1: AgentInfo and Permission System")
    logger.info("=" * 60)

    from derisk.agent.core.agent_info import (
        AgentInfo,
        AgentMode,
        PermissionAction,
        PermissionRuleset,
        PermissionRule,
        AgentRegistry,
    )

    # Test 1.1: PermissionRuleset
    rules = [
        PermissionRule(
            action=PermissionAction.ALLOW, pattern="read", permission="read"
        ),
        PermissionRule(
            action=PermissionAction.ASK, pattern="write", permission="write"
        ),
        PermissionRule(
            action=PermissionAction.DENY, pattern="delete", permission="delete"
        ),
    ]
    ruleset = PermissionRuleset(rules)
    logger.info("  Created PermissionRuleset with 3 rules")

    assert ruleset.check("read") == PermissionAction.ALLOW, "read should be ALLOW"
    assert ruleset.check("write") == PermissionAction.ASK, "write should be ASK"
    assert ruleset.check("delete") == PermissionAction.DENY, "delete should be DENY"
    logger.info("  Permission checks passed")

    assert ruleset.is_allowed("read") == True
    assert ruleset.is_denied("delete") == True
    assert ruleset.needs_ask("write") == True
    logger.info("  Helper methods passed")

    # Test 1.2: AgentInfo creation
    agent_info = AgentInfo(
        name="test_agent",
        description="Test agent for validation",
        mode=AgentMode.PRIMARY,
        permission={"read": "allow", "write": "ask", "delete": "deny"},
        tools={"read": True, "write": True, "delete": False},
    )
    logger.info(f"  Created AgentInfo: {agent_info.name}")

    # Test 1.3: AgentInfo permission checking
    assert agent_info.check_permission("read") == PermissionAction.ALLOW
    assert agent_info.check_permission("write") == PermissionAction.ASK
    assert agent_info.check_permission("delete") == PermissionAction.DENY
    logger.info("  AgentInfo permission checks passed")

    assert agent_info.is_tool_enabled("read") == True
    assert agent_info.is_tool_enabled("delete") == False
    logger.info("  Tool enablement checks passed")

    # Test 1.4: AgentRegistry
    registry = AgentRegistry.get_instance()
    registry.register(agent_info)
    retrieved = registry.get("test_agent")
    assert retrieved is not None
    assert retrieved.name == "test_agent"
    logger.info("  AgentRegistry operations passed")

    # Test 1.5: Markdown parsing
    markdown_content = """---
name: markdown_agent
description: Agent from markdown
mode: subagent
tools:
  write: false
  edit: false
---
You are a markdown-defined agent."""

    parsed_info = AgentInfo.from_markdown(markdown_content)
    assert parsed_info.name == "markdown_agent"
    assert parsed_info.description == "Agent from markdown"
    assert parsed_info.mode == AgentMode.SUBAGENT
    logger.info("  Markdown parsing passed")

    # Test 1.6: Default agents registration
    AgentRegistry.register_defaults()
    build_agent = registry.get("build")
    plan_agent = registry.get("plan")
    explore_agent = registry.get("explore")
    assert build_agent is not None
    assert plan_agent is not None
    assert explore_agent is not None
    logger.info("  Default agents registration passed")

    logger.info("Test 1: PASSED\n")
    return True


def test_execution_loop():
    """Test Execution Loop module."""
    logger.info("=" * 60)
    logger.info("Test 2: Execution Loop Module")
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

    # Test 2.1: LoopContext
    ctx = LoopContext(max_iterations=10)
    assert ctx.state == ExecutionState.PENDING
    assert ctx.can_continue() == False

    ctx.state = ExecutionState.RUNNING
    assert ctx.can_continue() == True
    logger.info("  LoopContext state transitions passed")

    ctx.increment()
    assert ctx.iteration == 1
    logger.info("  LoopContext increment passed")

    ctx.terminate("test termination")
    assert ctx.should_terminate == True
    logger.info("  LoopContext termination passed")

    ctx.mark_completed()
    assert ctx.state == ExecutionState.COMPLETED
    logger.info("  LoopContext completion passed")

    ctx.mark_failed("test error")
    assert ctx.state == ExecutionState.FAILED
    assert ctx.error_message == "test error"
    logger.info("  LoopContext failure passed")

    # Test 2.2: ExecutionContext
    exec_ctx = create_execution_context(max_iterations=5)
    loop_ctx = exec_ctx.start()
    assert loop_ctx.state == ExecutionState.RUNNING
    assert loop_ctx.max_iterations == 5
    logger.info("  ExecutionContext start passed")

    metrics = exec_ctx.end()
    assert metrics.total_iterations >= 0
    logger.info("  ExecutionContext end passed")

    # Test 2.3: ExecutionMetrics
    metrics = ExecutionMetrics(
        start_time_ms=1000,
        end_time_ms=2000,
        total_iterations=5,
        total_tokens=100,
        llm_calls=3,
        tool_calls=2,
    )
    assert metrics.duration_ms == 1000
    metrics_dict = metrics.to_dict()
    assert "start_time_ms" in metrics_dict
    assert "total_tokens" in metrics_dict
    logger.info("  ExecutionMetrics passed")

    # Test 2.4: SimpleExecutionLoop creation
    loop = create_execution_loop(max_iterations=5)
    assert loop.max_iterations == 5
    assert loop.enable_retry == True
    logger.info("  SimpleExecutionLoop creation passed")

    logger.info("Test 2: PASSED\n")
    return True


def test_llm_executor():
    """Test LLM Executor module."""
    logger.info("=" * 60)
    logger.info("Test 3: LLM Executor Module")
    logger.info("=" * 60)

    from derisk.agent.core.execution import (
        LLMConfig,
        LLMOutput,
        StreamChunk,
        create_llm_config,
    )

    # Test 3.1: LLMConfig
    config = create_llm_config(model="DeepSeek-V3", temperature=0.7, max_tokens=2048)
    assert config.model == "DeepSeek-V3"
    assert config.temperature == 0.7
    assert config.max_tokens == 2048
    assert config.stream == True
    logger.info("  LLMConfig creation passed")

    # Test 3.2: LLMOutput
    output = LLMOutput(
        content="Test output",
        thinking_content="Test thinking",
        model_name="DeepSeek-V3",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    )
    assert output.content == "Test output"
    assert output.thinking_content == "Test thinking"
    assert output.total_tokens == 30
    logger.info("  LLMOutput creation passed")

    # Test 3.3: LLMOutput to_dict
    output_dict = output.to_dict()
    assert "content" in output_dict
    assert "thinking_content" in output_dict
    assert "model_name" in output_dict
    logger.info("  LLMOutput serialization passed")

    # Test 3.4: StreamChunk
    chunk = StreamChunk(content_delta="test", is_first=True)
    assert chunk.content_delta == "test"
    assert chunk.is_first == True
    logger.info("  StreamChunk creation passed")

    logger.info("Test 3: PASSED\n")
    return True


def test_base_agent_permission_integration():
    """Test base_agent permission integration."""
    logger.info("=" * 60)
    logger.info("Test 4: Base Agent Permission Integration")
    logger.info("=" * 60)

    from derisk.agent.core.agent_info import (
        AgentInfo,
        AgentMode,
        PermissionAction,
        PermissionRuleset,
    )

    # Verify that permission methods exist in ConversableAgent
    import derisk.agent.core.base_agent as base_agent_module

    # Check for permission-related attributes
    assert hasattr(base_agent_module.ConversableAgent, "check_tool_permission")
    assert hasattr(base_agent_module.ConversableAgent, "is_tool_allowed")
    assert hasattr(base_agent_module.ConversableAgent, "is_tool_denied")
    assert hasattr(base_agent_module.ConversableAgent, "needs_tool_approval")
    assert hasattr(base_agent_module.ConversableAgent, "get_effective_max_steps")
    logger.info("  Permission methods exist in ConversableAgent")

    # Check AgentInfo integration
    assert hasattr(base_agent_module.ConversableAgent, "__annotations__")
    annotations = base_agent_module.ConversableAgent.__annotations__
    assert "permission_ruleset" in annotations or "permission_ruleset" in dir(
        base_agent_module.ConversableAgent
    )
    logger.info("  permission_ruleset attribute exists")

    assert "agent_info" in annotations or "agent_info" in dir(
        base_agent_module.ConversableAgent
    )
    logger.info("  agent_info attribute exists")

    assert "agent_mode" in annotations or "agent_mode" in dir(
        base_agent_module.ConversableAgent
    )
    logger.info("  agent_mode attribute exists")

    assert "max_steps" in annotations or "max_steps" in dir(
        base_agent_module.ConversableAgent
    )
    logger.info("  max_steps attribute exists")

    logger.info("Test 4: PASSED\n")
    return True


def test_agent_profile_v2():
    """Test AgentProfile v2 module."""
    logger.info("=" * 60)
    logger.info("Test 5: AgentProfile V2")
    logger.info("=" * 60)

    from derisk.agent.core.prompt_v2 import (
        AgentProfile,
        PromptFormat,
        PromptTemplate,
        PromptVariable,
        SystemPromptBuilder,
        UserProfile,
        compose_prompts,
    )

    # Test 5.1: AgentProfile creation
    profile = AgentProfile(
        name="test_profile",
        role="assistant",
        goal="Help users",
        description="Test profile",
    )
    assert profile.name == "test_profile"
    assert profile.role == "assistant"
    logger.info("  AgentProfile creation passed")

    # Test 5.2: UserProfile
    user_profile = UserProfile(
        name="test_user",
        preferences={"language": "zh"},
    )
    assert user_profile.name == "test_user"
    logger.info("  UserProfile creation passed")

    # Test 5.3: PromptTemplate
    template = PromptTemplate(
        name="test_template",
        template="Hello {{name}}, your goal is {{goal}}",
        format=PromptFormat.JINJA2,
    )
    assert template.name == "test_template"
    logger.info("  PromptTemplate creation passed")

    # Test 5.4: SystemPromptBuilder
    builder = SystemPromptBuilder()
    assert builder is not None
    logger.info("  SystemPromptBuilder creation passed")

    logger.info("Test 5: PASSED\n")
    return True


def test_execution_engine():
    """Test ExecutionEngine from execution_engine.py"""
    logger.info("=" * 60)
    logger.info("Test 6: ExecutionEngine")
    logger.info("=" * 60)

    from derisk.agent.core.execution_engine import (
        ExecutionStatus,
        ExecutionStep,
        ExecutionResult,
        ExecutionHooks,
        ExecutionEngine,
        ToolExecutor,
        SessionManager,
        ToolRegistry,
    )

    # Test 6.1: ExecutionStep
    step = ExecutionStep(
        step_id="test_step",
        step_type="thinking",
        content="test content",
    )
    assert step.step_id == "test_step"
    assert step.status == ExecutionStatus.PENDING
    step.complete("result")
    assert step.status == ExecutionStatus.SUCCESS
    logger.info("  ExecutionStep passed")

    # Test 6.2: ExecutionResult
    result = ExecutionResult()
    result.add_step(step)
    assert len(result.steps) == 1
    assert result.success == False
    result.status = ExecutionStatus.SUCCESS
    assert result.success == True
    logger.info("  ExecutionResult passed")

    # Test 6.3: ExecutionHooks
    hooks = ExecutionHooks()
    hooks.on("before_thinking", lambda: None)
    hooks.on("after_action", lambda: None)
    logger.info("  ExecutionHooks passed")

    # Test 6.4: ToolRegistry
    ToolRegistry.register("test_tool", lambda: "test")
    assert ToolRegistry.get("test_tool") is not None
    assert "test_tool" in ToolRegistry.list()
    logger.info("  ToolRegistry passed")

    # Test 6.5: SessionManager (sync test)
    manager = SessionManager()
    logger.info("  SessionManager creation passed")

    # Test 6.6: ToolExecutor
    executor = ToolExecutor()
    executor.register_tool("test", lambda x: x)
    logger.info("  ToolExecutor creation passed")

    logger.info("Test 6: PASSED\n")
    return True


def test_simple_memory():
    """Test SimpleMemory module."""
    logger.info("=" * 60)
    logger.info("Test 7: SimpleMemory System")
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

    # Test 7.1: MemoryEntry
    entry = MemoryEntry(
        content="Test memory content",
        role="assistant",
        priority=MemoryPriority.HIGH,
        scope=MemoryScope.SESSION,
    )
    assert entry.content == "Test memory content"
    assert entry.role == "assistant"
    assert entry.priority == MemoryPriority.HIGH
    assert entry.scope == MemoryScope.SESSION
    logger.info("  MemoryEntry creation passed")

    # Test 7.2: MemoryEntry serialization
    entry_dict = entry.to_dict()
    assert "content" in entry_dict
    assert "role" in entry_dict
    assert "priority" in entry_dict
    restored = MemoryEntry.from_dict(entry_dict)
    assert restored.content == entry.content
    logger.info("  MemoryEntry serialization passed")

    # Test 7.3: SimpleMemory
    async def test_simple_memory_async():
        memory = SimpleMemory(max_entries=100)

        entry_id = await memory.add(entry)
        assert entry_id is not None
        logger.info("  SimpleMemory add passed")

        retrieved = await memory.get(entry_id)
        assert retrieved is not None
        assert retrieved.content == entry.content
        logger.info("  SimpleMemory get passed")

        results = await memory.search("Test")
        assert len(results) == 1
        logger.info("  SimpleMemory search passed")

        count = await memory.count()
        assert count == 1
        logger.info("  SimpleMemory count passed")

    import asyncio

    asyncio.run(test_simple_memory_async())

    # Test 7.4: SessionMemory
    async def test_session_memory_async():
        session = SessionMemory()

        session_id = await session.start_session()
        assert session.session_id == session_id
        logger.info("  SessionMemory start_session passed")

        msg_id = await session.add_message("Hello", role="user")
        assert msg_id is not None
        logger.info("  SessionMemory add_message passed")

        messages = await session.get_messages()
        assert len(messages) == 1
        logger.info("  SessionMemory get_messages passed")

        context = await session.get_context_window(max_tokens=1000)
        assert len(context) == 1
        logger.info("  SessionMemory get_context_window passed")

        await session.end_session()

    asyncio.run(test_session_memory_async())

    # Test 7.5: MemoryManager
    manager = create_memory(max_entries=1000)
    assert manager is not None
    assert manager.session is not None
    assert manager.global_memory is not None
    logger.info("  MemoryManager creation passed")

    logger.info("Test 7: PASSED\n")
    return True


def test_skill_system():
    """Test Skill system."""
    logger.info("=" * 60)
    logger.info("Test 8: Skill System")
    logger.info("=" * 60)

    from derisk.agent.core.skill import (
        Skill,
        SkillType,
        SkillStatus,
        SkillMetadata,
        FunctionSkill,
        SkillRegistry,
        SkillManager,
        skill,
        create_skill_registry,
        create_skill_manager,
    )

    # Test 8.1: SkillMetadata
    metadata = SkillMetadata(
        name="test_skill",
        description="A test skill",
        version="1.0.0",
        author="test",
        skill_type=SkillType.CUSTOM,
        tags=["test", "example"],
    )
    assert metadata.name == "test_skill"
    assert metadata.skill_type == SkillType.CUSTOM
    metadata_dict = metadata.to_dict()
    assert "name" in metadata_dict
    logger.info("  SkillMetadata passed")

    # Test 8.2: Custom Skill class
    class TestSkill(Skill):
        async def _do_initialize(self) -> bool:
            return True

        async def execute(self, *args, **kwargs):
            return {"result": "executed"}

    test_skill = TestSkill(metadata=metadata)
    assert test_skill.name == "test_skill"
    assert test_skill.status == SkillStatus.DISABLED
    logger.info("  Custom Skill class passed")

    # Test 8.3: Skill initialization
    async def test_skill_init():
        success = await test_skill.initialize()
        assert success == True
        assert test_skill.is_enabled == True

    import asyncio

    asyncio.run(test_skill_init())
    logger.info("  Skill initialization passed")

    # Test 8.4: FunctionSkill
    async def test_function():
        return "function result"

    func_skill = FunctionSkill(test_function, "func_test", "Test function skill")
    assert func_skill.name == "func_test"
    logger.info("  FunctionSkill creation passed")

    # Test 8.5: SkillRegistry
    registry = create_skill_registry()
    registry.register(test_skill)

    retrieved = registry.get("test_skill")
    assert retrieved is not None
    assert retrieved.name == "test_skill"
    logger.info("  SkillRegistry register/get passed")

    skills = registry.list()
    assert len(skills) >= 1
    logger.info("  SkillRegistry list passed")

    registry.unregister("test_skill")
    assert registry.get("test_skill") is None
    logger.info("  SkillRegistry unregister passed")

    # Test 8.6: @skill decorator
    @skill("decorated_skill", description="A decorated skill")
    async def decorated_func(x: int) -> int:
        return x * 2

    assert hasattr(decorated_func, "_skill_name")
    assert decorated_func._skill_name == "decorated_skill"
    logger.info("  @skill decorator passed")

    # Test 8.7: SkillManager
    manager = create_skill_manager()
    assert manager.registry is not None
    logger.info("  SkillManager creation passed")

    logger.info("Test 8: PASSED\n")
    return True


def main():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("Agent Core Modules Validation Tests")
    logger.info("=" * 60 + "\n")

    results = []

    try:
        results.append(("AgentInfo & Permission", test_agent_info_and_permission()))
    except Exception as e:
        logger.error(f"Test 1 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("AgentInfo & Permission", False))

    try:
        results.append(("Execution Loop", test_execution_loop()))
    except Exception as e:
        logger.error(f"Test 2 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Execution Loop", False))

    try:
        results.append(("LLM Executor", test_llm_executor()))
    except Exception as e:
        logger.error(f"Test 3 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("LLM Executor", False))

    try:
        results.append(
            ("Base Agent Permission", test_base_agent_permission_integration())
        )
    except Exception as e:
        logger.error(f"Test 4 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Base Agent Permission", False))

    try:
        results.append(("AgentProfile V2", test_agent_profile_v2()))
    except Exception as e:
        logger.error(f"Test 5 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("AgentProfile V2", False))

    try:
        results.append(("ExecutionEngine", test_execution_engine()))
    except Exception as e:
        logger.error(f"Test 6 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("ExecutionEngine", False))

    try:
        results.append(("SimpleMemory System", test_simple_memory()))
    except Exception as e:
        logger.error(f"Test 7 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("SimpleMemory System", False))

    try:
        results.append(("Skill System", test_skill_system()))
    except Exception as e:
        logger.error(f"Test 8 FAILED: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Skill System", False))

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
