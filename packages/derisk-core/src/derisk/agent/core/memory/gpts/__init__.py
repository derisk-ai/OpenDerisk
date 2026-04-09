"""Memory module for GPTS messages, plans and files.

It stores the messages, plans and files generated of multiple agents in the conversation.

It is different from the agent memory as it is a formatted structure to store the
messages, plans and files, and it can be stored in a database or a file.
"""

from .base import (  # noqa: F401
    GptsMessage,
    GptsMessageMemory,
    GptsPlan,
    GptsPlansMemory,
    MESSAGE_DATA_VERSION_V2,
)
from .default_gpts_memory import (  # noqa: F401
    DefaultGptsMessageMemory,
    DefaultGptsPlansMemory,
)
from .gpts_memory import GptsMemory  # noqa: F401

# File memory exports
from .file_base import (  # noqa: F401
    AgentFileMetadata,
    AgentFileMemory,
    AgentFileCatalog,
    FileType,
    FileStatus,
    FileMetadataStorage,        # V2: 文件元数据存储接口
    SimpleFileMetadataStorage,  # V2: 简单内存存储实现
    # WorkLog exports
    WorkLogStorage,             # WorkLog 存储接口
    WorkLogStatus,              # WorkLog 状态枚举
    WorkEntry,                  # WorkLog 条目
    WorkLogSummary,             # WorkLog 摘要
    SimpleWorkLogStorage,       # 简单内存 WorkLog 存储
    # Kanban exports
    KanbanStorage,              # Kanban 存储接口
    Kanban,                     # Kanban 数据模型
    KanbanStage,                # Kanban 阶段
    StageStatus,                # 阶段状态枚举
    SimpleKanbanStorage,        # 简单内存 Kanban 存储
    # Todo exports
    TodoStorage,                # Todo 存储接口
    TodoItem,                   # Todo 条目
    TodoStatus,                 # Todo 状态枚举
    TodoPriority,               # Todo 优先级枚举
    SimpleTodoStorage,          # 简单内存 Todo 存储
)
from .default_file_memory import (  # noqa: F401
    DefaultAgentFileMemory,
)