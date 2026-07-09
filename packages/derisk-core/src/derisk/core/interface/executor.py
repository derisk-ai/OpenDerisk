"""向后兼容重导出——执行投影契约已迁移至 ``derisk.core.interface.resource`` 子包。

RFC-005 协议契约按职责拆分:executor/dispatcher 到 resource/{executor,dispatcher}.py。
本模块保留以兼容现有 ``from derisk.core.interface.executor import X`` 导入路径。
新代码请直接从 ``derisk.core.interface.resource.*`` 导入。
"""

from derisk.core.interface.resource.dispatcher import (  # noqa: F401
    ToolDispatchResult,
    ToolDispatcher,
)
from derisk.core.interface.resource.executor import (  # noqa: F401
    Executor,
    ExecutorCall,
    ExecutorRegistry,
    ExecutorStatus,
    InMemoryExecutorRegistry,
    ReleaseReason,
    topological_prepare,
)