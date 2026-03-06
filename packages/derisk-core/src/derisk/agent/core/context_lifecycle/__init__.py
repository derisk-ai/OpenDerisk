"""
Context Lifecycle Management - 上下文生命周期管理

提供Skill和工具的主动退出机制，保证上下文空间的高效利用。

=== 核心版本 ===

V2 (推荐，基于OpenCode最佳实践):
- SimpleContextManager: 简化版管理器
- AgentContextIntegration: Agent集成封装
- 特点：加载新Skill自动压缩旧Skill，无不可靠检测

V1 (完整功能):
- ContextSlotManager: 完整槽位管理
- SkillLifecycleManager: Skill生命周期
- ToolLifecycleManager: 工具生命周期
- ContextLifecycleOrchestrator: 编排器

=== 快速开始 ===

from derisk.agent.core.context_lifecycle import AgentContextIntegration

# 创建集成实例
integration = AgentContextIntegration(token_budget=50000)

# 初始化
await integration.initialize(session_id="xxx", system_prompt="...")

# 加载Skill（自动压缩前一个）
result = await integration.prepare_skill(
    skill_name="code_review",
    skill_content=skill_content,
    required_tools=["read", "grep"],
)

# 构建消息（注入上下文）
messages = integration.build_messages(user_message="分析代码")

# 完成当前Skill
await integration.complete_skill(summary="完成分析")
"""

# V2 推荐使用（简化版）
from .simple_manager import (
    ContentType,
    ContentState,
    ContentSlot,
    SimpleContextManager,
    AgentContextIntegration,
)

# V1 完整功能
from .slot_manager import (
    SlotType,
    SlotState,
    EvictionPolicy,
    ContextSlot,
    ContextSlotManager,
)
from .skill_lifecycle import (
    ExitTrigger,
    SkillExitResult,
    SkillManifest,
    SkillLifecycleManager,
)
from .tool_lifecycle import (
    ToolCategory,
    ToolManifest,
    ToolLifecycleManager,
)
from .orchestrator import (
    ContextLifecycleOrchestrator,
    create_context_lifecycle,
)
from .context_assembler import (
    PromptSection,
    AssembledPrompt,
    ContextAssembler,
    create_context_assembler,
)
from .agent_integration import (
    CoreAgentContextIntegration,
    CoreV2AgentContextIntegration,
)

__all__ = [
    # V2 推荐使用（简化版）
    "ContentType",
    "ContentState",
    "ContentSlot",
    "SimpleContextManager",
    "AgentContextIntegration",
    # V1 槽位管理
    "SlotType",
    "SlotState",
    "EvictionPolicy",
    "ContextSlot",
    "ContextSlotManager",
    # V1 Skill管理
    "ExitTrigger",
    "SkillExitResult",
    "SkillManifest",
    "SkillLifecycleManager",
    # V1 工具管理
    "ToolCategory",
    "ToolManifest",
    "ToolLifecycleManager",
    # V1 编排器
    "ContextLifecycleOrchestrator",
    "create_context_lifecycle",
    # 上下文组装器
    "PromptSection",
    "AssembledPrompt",
    "ContextAssembler",
    "create_context_assembler",
    # Agent集成
    "CoreAgentContextIntegration",
    "CoreV2AgentContextIntegration",
]