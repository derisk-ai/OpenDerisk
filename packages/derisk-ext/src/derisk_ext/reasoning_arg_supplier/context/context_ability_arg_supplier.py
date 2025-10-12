# from typing import Optional
#
# from derisk.agent import AgentMessage, AgentContext
# from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
# from derisk_ext.agent.agents.reasoning.default.ability import Ability
# from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
#     ReasoningAgent,
# )
# from derisk_ext.reasoning_arg_supplier.default.default_ability_arg_supplier import append_context_ability
#
# _NAME = "CONTEXT_ABILITY_ARG_SUPPLIER"
# _DESCRIPTION = "上下文工程参数引擎: ability"
#
#
# class ContextAbilityArgSupplier(ReasoningArgSupplier):
#     @property
#     def name(self) -> str:
#         return _NAME
#
#     @property
#     def description(self) -> str:
#         return _DESCRIPTION
#
#     @property
#     def arg_key(self) -> str:
#         return "ability"
#
#     async def supply(
#         self,
#         prompt_param: dict,
#         agent: ReasoningAgent,
#         agent_context: Optional[AgentContext] = None,
#         received_message: Optional[AgentMessage] = None,
#             current_step_message: Optional[AgentMessage]=None,
#         **kwargs,
#     ) -> None:
#         abilities: list[Ability] = agent.abilities if agent else None
#         if not abilities:
#             return
#
#         prompts: list[str] = []
#         for idx, ability in enumerate(abilities):
#             prompt: str = await ability.get_prompt()
#             if not prompt:
#                 continue
#
#             prompts.append(f"可用能力{idx + 1}\n" + prompt)
#             if current_step_message:
#                 if current_step_message:
#                     context = current_step_message.context or {}
#                     append_context_ability(context, ability)
#                     current_step_message.context = context
#         if prompts:
#             prompt_param[self.arg_key] = ("\n\n".join(prompts)).strip()
