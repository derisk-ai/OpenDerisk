from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.ability import Ability
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)

_NAME = "DEFAULT_ABILITY_ARG_SUPPLIER"
_DESCRIPTION = "默认参数引擎: ability"

_SPLITER = "\n\n----- 可用能力 -----\n\n"


class DefaultAbilityArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "ability"

    async def supply(
        self,
        prompt_param: dict,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs,
    ):
        abilities: list[Ability] = agent.abilities if agent else None
        if not abilities:
            return

        prompts = [
            prompt for ability in abilities if (prompt := await ability.get_prompt())
        ]
        if prompts:
            prompt_param[self.arg_key] = (_SPLITER + _SPLITER.join(prompts)).strip()
