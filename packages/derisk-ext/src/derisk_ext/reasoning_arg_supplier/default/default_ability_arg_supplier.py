import logging
from typing import Optional

from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.agent import MessageContextType
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk.context.utils import format_ability_by_context
from derisk_ext.agent.agents.reasoning.default.ability import Ability
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)

logger = logging.getLogger("reasoning")

_NAME = "DEFAULT_ABILITY_ARG_SUPPLIER"
_DESCRIPTION = "默认参数引擎: ability"


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

    async def supply(self, prompt_param: dict, **kwargs) -> None:
        return await self._supply_by_agent_ability(prompt_param=prompt_param, **kwargs)
        # context = Manager.current_window()
        # if not context:
        #     # 兼容旧版本
        #     return await self._supply_by_agent_ability(prompt_param=prompt_param, **kwargs)
        #
        # # 根据上下文窗口填充信息
        # return await self._supply_by_context(prompt_param)

    async def _supply_by_context(self, prompt_param: dict):
        prompt_param[self.arg_key] = format_ability_by_context()

    async def _supply_by_agent_ability(
        self,
        prompt_param: dict,
        agent: ReasoningAgent,
        agent_context: Optional[AgentContext] = None,
        received_message: Optional[AgentMessage] = None,
        current_step_message: Optional[AgentMessage] = None,
        **kwargs,
    ):
        abilities: list[Ability] = agent.abilities if agent else None
        logger.info(f"DefaultAbilityArgSupplier, _supply_by_agent_ability, abilities: {[a.name for a in abilities]}")
        if not abilities:
            return

        prompts: list[str] = []
        for idx, ability in enumerate(abilities):
            prompt: str = await ability.get_prompt()
            if not prompt:
                continue

            prompts.append(f"### 可用能力\n" + prompt)
            if current_step_message:
                context = current_step_message.context or {}
                append_context_ability(context, ability)
                current_step_message.context = context
        if prompts:
            prompt_param[self.arg_key] = ("\n\n".join(prompts)).strip()

        context_ability = format_ability_by_context()
        logger.info(f"DefaultAbilityArgSupplier, 可用能力:{'相同' if context_ability == prompt_param[self.arg_key] else '不同'}")
        if context_ability != prompt_param[self.arg_key]:
            logger.info(f"ability: [{prompt_param[self.arg_key]}],context: [{context_ability}]")


def append_context_ability(context: MessageContextType, ability: Ability):
    context_key, item = ability.context_info
    items = context.get(context_key, [])
    items.append(item)
    context[context_key] = items
