import json
from typing import List, Optional

from derisk.agent import AgentMessage, AgentContext, ActionOutput, ConversableAgent
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.reasoning.reasoning_action import AgentAction, parse_action_reports
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)

_NAME = "INDEX_HISTORY_ARG_SUPPLIER"
_DESCRIPTION = "自定义参数引擎: index_history"

_SEPARATOR = "\n\n--------------\n\n"

MODEL_CONTEXT_LENGTH = {
    'aistudio/DeepSeek-V3': 64000,
    'aistudio/DeepSeek-R1': 64000,
    'aistudio/QwQ-32B': 64000,
}


class IndexHistoryArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "index_history"

    async def supply(
        self,
        prompt_param: dict,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs,
    ):
        messages: List[GptsMessage] = await agent.memory.gpts_memory.get_messages(conv_id=agent_context.conv_id)
        messages = self.kick_message(messages, received_message, agent)
        if not messages:
            return

        histories: list[str] = []
        for message in messages:
            if not message.action_report:
                continue

            action_reports = parse_action_reports(message.action_report)
            for action_report in action_reports:
                if not action_report.content:
                    # 踢掉空白action
                    continue

                if action_report.action_name == AgentAction().name and (
                    not action_report.action_id or not action_report.action_id.endswith("answer")):
                    # agent action只看answer
                    continue

                if self.custom_filter(received_message=received_message, message=message,
                                      agent=agent, action_report=action_report,
                                      sender_agent_name=message.sender_name,
                                      receiver_agent_name=message.receiver_name):
                    continue

                action_report_prompt = self._format_action_report_prompt(agent=agent, action_report=action_report,
                                                                         sender_agent_name=message.sender_name,
                                                                         receiver_agent_name=message.receiver_name)
                if action_report_prompt:
                    histories.append(action_report_prompt)

        history: str = self._join_history(histories, agent=agent)
        if history:
            prompt_param[self.arg_key] = history

    def kick_message(
        self,
        messages: List[GptsMessage],
        received_message: AgentMessage,
        agent: ReasoningAgent,
    ) -> List[GptsMessage]:
        return messages

    def kick_actions_prompts(self, histories: list[str], **kwargs) -> tuple[int, list[str]]:
        """
        剔除action report rompt
        :param histories: 原始action report rompt
        :param kwargs:
        :return: ti
        """
        if not histories:
            return 0, histories

        length = get_agent_llm_context_length(kwargs.get("agent")) - 1000
        idx = len(histories) - 1
        history_size = 0
        for index in range(len(histories) - 1, -1, -1):
            if history_size + len(histories[index]) > length:
                break
            idx = index
        return idx, histories[idx:]

    def custom_filter(self, received_message: AgentMessage, message: GptsMessage, agent: ReasoningAgent,
                      action_report: ActionOutput,
                      sender_agent_name: str, receiver_agent_name: str) -> bool:
        return False

    def _format_action_report_prompt(self, agent: ReasoningAgent, action_report: ActionOutput,
                                     sender_agent_name: str, receiver_agent_name: str) -> Optional[str]:
        return "\n".join([item for item in [
            f"action_id: {action_report.action_id}" if action_report.action_id else None,
            f"action_handler: {sender_agent_name}" if sender_agent_name else None,
            f"action_name: {action_report.action_name}" if action_report.action_name else None,
            f"action: {action_report.action}" if action_report.action else None,
            f"action_input: {action_report.action_input}" if action_report.action_input else None,
            f"action_output: {action_report.content}",
        ] if item])

    def _join_history(self, histories: list, **kwargs) -> Optional[str]:
        size, kicked_histories = self.kick_actions_prompts(histories=histories, **kwargs)
        return ((f"由于长度限制, {size}条最早的历史数据被剔除\n\n" if size > 0 else "")
                + ((_SEPARATOR + _SEPARATOR.join(kicked_histories)) if kicked_histories else ""))

def get_agent_llm_context_length(agent: ConversableAgent) -> int:
    default_length = 32000
    if not agent:
        return default_length

    model_list = agent.llm_config.strategy_context
    if not model_list:
        return default_length
    if isinstance(model_list, str):
        try:
            model_list = json.loads(model_list)
        except Exception:
            return default_length

    return MODEL_CONTEXT_LENGTH.get(model_list[0], default_length)