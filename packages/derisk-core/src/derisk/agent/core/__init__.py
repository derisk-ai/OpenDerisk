"""Core Module for the Agent.

There are four modules in DERISK agent core according the paper
`A survey on large language model based autonomous agents
<https://link.springer.com/article/10.1007/s11704-024-40231-1>`
by `Lei Wang, Chen Ma, Xueyang Feng, et al.`:

1. Profiling Module: The profiling module aims to indicate the profiles of the agent
roles.

2. Memory Module: It stores information perceived from the environment and leverages
the recorded memories to facilitate future actions.

3. Planning Module: When faced with a complex task, humans tend to deconstruct it into
simpler subtasks and solve them individually. The planning module aims to empower the
agents with such human capability, which is expected to make the agent behave more
reasonably, powerfully, and reliably

4. Action Module: The action module is responsible for translating the agent's
decisions into specific outcomes. This module is located at the most downstream
position and directly interacts with the environment.

Refactored (v2): Added new Agent configuration system inspired by opencode/openclaw:
- AgentInfo: Declarative agent configuration
- PermissionRuleset: Fine-grained permission control
- ExecutionLoop: Simplified execution loop
- AgentProfile: Simplified profile configuration
- SimpleMemory: Simplified memory system
- Skill: Modular skill system

Added (v3): User Interaction and Recovery System:
- InteractionAdapter: Interactive user communication
- RecoveryCoordinator: Interrupt recovery management
- TodoManager: Task list management
- Full interaction protocol support
"""

from derisk.agent.core.system_tool_registry import system_tool_dict
from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool_dict

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
    ExecutionState,
    LoopContext,
    ExecutionMetrics,
    ExecutionContext,
    SimpleExecutionLoop,
    create_execution_context,
    create_execution_loop,
    LLMConfig,
    LLMOutput,
    StreamChunk,
    LLMExecutor,
    create_llm_config,
    create_llm_executor,
)
from derisk.agent.core.execution_engine import (
    ExecutionStatus,
    ExecutionStep,
    ExecutionResult,
    ExecutionHooks,
    ExecutionEngine,
    ToolExecutor,
    SessionManager,
    ToolRegistry,
    tool,
)
from derisk.agent.core.prompt_v2 import (
    AgentProfile,
    PromptFormat,
    PromptTemplate,
    PromptVariable,
    SystemPromptBuilder,
    UserProfile,
    compose_prompts,
    load_prompt,
)
from derisk.agent.core.simple_memory import (
    MemoryEntry,
    MemoryScope,
    MemoryPriority,
    BaseMemory,
    SimpleMemory,
    SessionMemory,
    MemoryManager,
    create_memory,
)
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
from derisk.agent.core.context_lifecycle import (
    # V2 推荐（简化版）
    ContentType,
    ContentState,
    ContentSlot,
    SimpleContextManager,
    AgentContextIntegration,
    # V1 完整功能
    SlotType,
    SlotState,
    EvictionPolicy,
    ContextSlot,
    ContextSlotManager,
    ExitTrigger,
    SkillExitResult,
    SkillManifest,
    SkillLifecycleManager,
    ToolCategory,
    ToolManifest,
    ToolLifecycleManager,
    ContextLifecycleOrchestrator,
    create_context_lifecycle,
    ContextAssembler,
    create_context_assembler,
    CoreAgentContextIntegration,
    CoreV2AgentContextIntegration,
)

__all__ = [
    # Tools
    "system_tool_dict",
    "sandbox_tool_dict",
    # Agent Info
    "AgentInfo",
    "AgentMode",
    "AgentRegistry",
    "PermissionAction",
    "PermissionRule",
    "PermissionRuleset",
    "create_agent_info",
    # Execution Loop
    "ExecutionState",
    "LoopContext",
    "ExecutionMetrics",
    "ExecutionContext",
    "SimpleExecutionLoop",
    "create_execution_context",
    "create_execution_loop",
    # LLM Executor
    "LLMConfig",
    "LLMOutput",
    "StreamChunk",
    "LLMExecutor",
    "create_llm_config",
    "create_llm_executor",
    # Execution Engine
    "ExecutionStatus",
    "ExecutionStep",
    "ExecutionResult",
    "ExecutionHooks",
    "ExecutionEngine",
    "ToolExecutor",
    "SessionManager",
    "ToolRegistry",
    "tool",
    # Prompt V2
    "AgentProfile",
    "PromptFormat",
    "PromptTemplate",
    "PromptVariable",
    "SystemPromptBuilder",
    "UserProfile",
    "compose_prompts",
    "load_prompt",
    # Simple Memory
    "MemoryEntry",
    "MemoryScope",
    "MemoryPriority",
    "BaseMemory",
    "SimpleMemory",
    "SessionMemory",
    "MemoryManager",
    "create_memory",
    # Skill System
    "Skill",
    "SkillType",
    "SkillStatus",
    "SkillMetadata",
    "FunctionSkill",
    "SkillRegistry",
    "SkillManager",
    "skill",
    "create_skill_registry",
    "create_skill_manager",
    # Context Lifecycle V2 (推荐)
    "ContentType",
    "ContentState",
    "ContentSlot",
    "SimpleContextManager",
    "AgentContextIntegration",
    # Context Lifecycle V1 (完整功能)
    "SlotType",
    "SlotState",
    "EvictionPolicy",
    "ContextSlotManager",
    "ExitTrigger",
    "SkillExitResult",
    "SkillManifest",
    "SkillLifecycleManager",
    "ToolCategory",
    "ToolManifest",
    "ToolLifecycleManager",
    "ContextLifecycleOrchestrator",
    "create_context_lifecycle",
    "ContextAssembler",
    "create_context_assembler",
    "CoreAgentContextIntegration",
    "CoreV2AgentContextIntegration",
    # Interaction System (User Interaction)
    "InteractionAdapter",
    "create_interaction_adapter",
]

# Interaction System
from derisk.agent.core.interaction_adapter import (
    InteractionAdapter,
    create_interaction_adapter,
)
