from typing import Optional

from derisk.agent import AgentMessage, AgentContext, Agent
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)

_NAME = "DEFAULT_KNOWLEDGE_ARG_SUPPLIER"
_DESCRIPTION = "默认参数引擎: knowledge"


class DefaultKnowledgeArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "knowledge"

    async def supply(
        self,
        prompt_param: dict,
        agent: Agent,
        agent_context: Optional[AgentContext] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> None:
        pass
