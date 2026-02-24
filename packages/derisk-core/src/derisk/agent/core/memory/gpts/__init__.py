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
)
from .default_file_memory import (  # noqa: F401
    DefaultAgentFileMemory,
)
