"""向后兼容重导出——编排层已迁移至 ``derisk.agent.capabilities``。

ResourceFacade / AgentInputsSnapshot / compute_config_hash 现权威定义在
``derisk.agent.capabilities.facade``。本模块保留以兼容现有导入路径。
新代码请从 ``derisk.agent.capabilities`` 导入。
"""

from derisk.agent.capabilities.facade import (  # noqa: F401
    AgentInputsSnapshot,
    ResourceFacade,
    compute_config_hash,
)