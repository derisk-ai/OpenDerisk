from typing import Optional

from derisk.agent import AgentMessage, AgentContext, Agent
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)

_NAME = "DEFAULT_OUTPUT_SCHEMA_ARG_SUPPLIER"
_DESCRIPTION = "默认参数引擎: output_schema"
_DEFAULT_OUTPUT_SCHEMA = """严格按以下JSON格式输出，确保可直接解析：
{
  "reason": "详细解释状态判定和plan拆解依据（需引用具体分析结论或执行结果）",
  "status": "planing (仅当需要执行下一步动作时) | done (仅当任务可终结时) | abort (仅当任务异常或无法推进或需要用户提供更多信息时)",
  "plans"?: [{
    "reason": "必须执行的具体依据（需关联前置分析或执行结果）"
    "intention": "新动作目标（需对比历史动作确保不重复）",
    "id": "工具ID", 
    "parameters": {"参数键":"值"}
  }],
  "plans_brief_description"?: "简短介绍要执行的动作，不超过10个字",
  "answer"?: "当done/abort状态时出现，根据上下文信息给出任务结论"
}"""


class DefaultOutputSchemaArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "output_schema"

    @property
    def detail(self) -> Optional[str]:
        return _DEFAULT_OUTPUT_SCHEMA

    async def supply(
        self,
        prompt_param: dict,
        agent: Agent,
        agent_context: Optional[AgentContext] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> None:
        prompt_param[self.arg_key] = _DEFAULT_OUTPUT_SCHEMA
