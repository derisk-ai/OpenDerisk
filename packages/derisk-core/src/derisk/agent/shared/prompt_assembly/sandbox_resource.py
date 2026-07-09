"""向后兼容重导出——SandboxResource 已迁移至 ``derisk.agent.capabilities.sandbox``。

新代码请从 ``derisk.agent.capabilities.sandbox`` 导入。
"""

from derisk.agent.capabilities.sandbox.resource import (  # noqa: F401
    SANDBOX_DELEGATED_TOOLS,
    SandboxResource,
)