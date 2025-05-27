from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)

_NAME = "INDEX_OUTPUT_SCHEMA_ARG_SUPPLIER"
_DESCRIPTION = "自定义参数引擎: index_output_schema"
_INDEX_OUTPUT_SCHEMA =  """
###
对于answer生成的约束：
- 输出的**任务总结报告**必须为markdown格式
- 先给出**一句话总结**，提炼任务执行结论
- 再给出详尽的**推理总结步骤**，保证结论的逻辑性统一和递进关系
- 参考**历史记录分析**做出合理的推理总结，列出**关键判断依赖**（**关键判断依赖**必须是action_name:Tool的记录，这表明了有具体的工具执行），摘取出action和message_id放到结尾，以“(意图: action) <message_id>: id”的形式

参考：
#### 任务总结报告
##### **一句话总结**：
本任务的结论是xxx。

##### **推理总结步骤**：
1. 任务步骤1实现了xxx
2. 任务步骤2实现了xxx

##### **关键判断依赖**：
1. 获取到a工具的结果是result-aaa(意图: 具体意图-aaa) <message_id>: 8b1dd400832344cc93048cdd6ec230d7
2. 获取到b工具的结果是result-bbb(意图: 具体意图-bbb) <message_id>: 8513ba1ed0a04bd5aaec4a0516523fcd
"""


class IndexOutputSchemaArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "index_output_schema"

    async def supply(
        self,
        prompt_param: dict,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs,
    ):
        prompt_param[self.arg_key] = _INDEX_OUTPUT_SCHEMA
