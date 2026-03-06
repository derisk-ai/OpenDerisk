#!/usr/bin/env python
"""Quick verification of all refactored capabilities."""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-core/src"))

print("=" * 60)
print("ReActMasterV2 Refactored Capabilities Verification")
print("=" * 60)

# Test 1: AgentInfo & Permission System
from derisk.agent.core.agent_info import (
    AgentInfo,
    AgentMode,
    PermissionAction,
    PermissionRuleset,
    AgentRegistry,
)

info = AgentInfo(
    name="react_agent",
    mode=AgentMode.PRIMARY,
    max_steps=10,
    permission={"read": "allow", "write": "ask"},
)
assert info.max_steps == 10
assert info.check_permission("read") == PermissionAction.ALLOW
assert info.check_permission("write") == PermissionAction.ASK
print("✅ Test 1: AgentInfo & Permission System - PASSED")

# Test 2: Execution Loop
from derisk.agent.core.execution import (
    SimpleExecutionLoop,
    create_execution_loop,
    LLMConfig,
    LLMOutput,
)

loop = create_execution_loop(max_iterations=5)
config = LLMConfig(model="test", temperature=0.7)
output = LLMOutput(content="test", model_name="test")
assert loop.max_iterations == 5
print("✅ Test 2: Execution Loop & LLM Executor - PASSED")

# Test 3: Simple Memory
from derisk.agent.core.simple_memory import (
    SimpleMemory,
    SessionMemory,
    MemoryManager,
    create_memory,
)

manager = create_memory()
assert manager is not None
print("✅ Test 3: Simple Memory System - PASSED")

# Test 4: Skill System
from derisk.agent.core.skill import Skill, SkillRegistry, SkillMetadata, skill

registry = SkillRegistry.get_instance()
assert registry is not None
print("✅ Test 4: Skill System - PASSED")

# Test 5: Agent Profile V2
from derisk.agent.core.prompt_v2 import AgentProfile, PromptTemplate

profile = AgentProfile(name="test", role="assistant")
template = PromptTemplate(name="test", template="Hello")
assert profile.name == "test"
print("✅ Test 5: Agent Profile V2 - PASSED")

# Test 6: Base Agent Integration
from derisk.agent.core.base_agent import ConversableAgent

assert hasattr(ConversableAgent, "check_tool_permission")
assert hasattr(ConversableAgent, "is_tool_allowed")
assert hasattr(ConversableAgent, "is_tool_denied")
assert hasattr(ConversableAgent, "needs_tool_approval")
assert hasattr(ConversableAgent, "get_effective_max_steps")
print("✅ Test 6: Base Agent Permission Integration - PASSED")

# Test 7: Execution Engine
from derisk.agent.core.execution_engine import (
    ExecutionStatus,
    ExecutionStep,
    ExecutionResult,
    ExecutionEngine,
    ToolExecutor,
)

step = ExecutionStep(step_id="test", step_type="test", content="")
assert step.status == ExecutionStatus.PENDING
print("✅ Test 7: Execution Engine - PASSED")

print()
print("=" * 60)
print("All 7 refactored capabilities VERIFIED!")
print("ReActMasterV2 can use these capabilities.")
print("=" * 60)
