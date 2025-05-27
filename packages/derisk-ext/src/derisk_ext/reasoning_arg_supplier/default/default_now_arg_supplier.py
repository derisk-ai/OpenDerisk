from datetime import datetime

from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import ReasoningAgent

_NAME = "DEFAULT_NOW_TIME_ARG_SUPPLIER"
_DESCRIPTION = "默认参数引擎: now，解析当前时间，格式"


class DefaultNowArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "now"

    async def supply(
        self,
        prompt_param: dict,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs,
    ):
        prompt_param[self.arg_key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
