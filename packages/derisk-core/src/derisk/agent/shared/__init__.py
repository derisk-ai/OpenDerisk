"""
Shared Infrastructure - 共享基础设施层

为 Core V1 和 Core V2 提供统一的基础设施组件：

核心组件：
- SharedSessionContext: 统一会话上下文容器
- ContextArchiver: 上下文自动归档器
- TaskBoardManager: Todo/Kanban 任务管理器

适配器：
- V1ContextAdapter: Core V1 适配器
- V2ContextAdapter: Core V2 适配器

设计原则：
- 统一资源平面：所有基础数据存储管理使用同一套组件
- 架构无关：不依赖特定 Agent 架构实现
- 会话隔离：每个会话独立管理资源
"""

from derisk.agent.shared.context import (
    SharedSessionContext,
    SharedContextConfig,
    create_shared_context,
)

from derisk.agent.shared.context_archiver import (
    ContextArchiver,
    ArchiveRule,
    ArchiveEntry,
    ArchiveTrigger,
    ContentType,
    create_context_archiver,
)

from derisk.agent.shared.task_board import (
    TaskBoardManager,
    TaskItem,
    TaskStatus,
    TaskPriority,
    Kanban,
    Stage,
    StageStatus,
    WorkEntry,
    create_task_board_manager,
)

from derisk.agent.shared.adapters.v1_adapter import (
    V1ContextAdapter,
    create_v1_adapter,
)

from derisk.agent.shared.adapters.v2_adapter import (
    V2ContextAdapter,
    create_v2_adapter,
)

__all__ = [
    # Context
    "SharedSessionContext",
    "SharedContextConfig",
    "create_shared_context",
    
    # Archiver
    "ContextArchiver",
    "ArchiveRule",
    "ArchiveEntry",
    "ArchiveTrigger",
    "ContentType",
    "create_context_archiver",
    
    # Task Board
    "TaskBoardManager",
    "TaskItem",
    "TaskStatus",
    "TaskPriority",
    "Kanban",
    "Stage",
    "StageStatus",
    "WorkEntry",
    "create_task_board_manager",
    
    # Adapters
    "V1ContextAdapter",
    "V2ContextAdapter",
    "create_v1_adapter",
    "create_v2_adapter",
]