import json
from typing import List, Optional

from derisk.agent import AgentMessage, AgentContext, ActionOutput, ConversableAgent
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.reasoning.reasoning_action import AgentAction, parse_action_reports
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import (
    ReasoningAgent,
)
from derisk_serve.agent.db import GptsConversationsDao

_NAME = "DEFAULT_HISTORY_ARG_SUPPLIER"
_DESCRIPTION = "默认参数引擎: history"

_SEPARATOR = "\n\n--------------\n\n"

MODEL_CONTEXT_LENGTH = {
    'aistudio/DeepSeek-V3': 64000,
    'aistudio/DeepSeek-R1': 64000,
    'aistudio/QwQ-32B': 64000,
}


class DefaultHistoryArgSupplier(ReasoningArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def arg_key(self) -> str:
        return "history"

    async def supply(
            self,
            prompt_param: dict,
            agent: ReasoningAgent,
            agent_context: AgentContext,
            received_message: AgentMessage,
            **kwargs,
    ):
        histories: list[str] = []

        conversations = GptsConversationsDao().get_like_conv_id_asc(session_id_from_conv_id(agent_context.conv_id))
        for idx, conversation in enumerate(conversations):
            messages: List[GptsMessage] = await agent.memory.gpts_memory.get_messages(conv_id=conversation.conv_id)
            messages = self.kick_message(messages, received_message, agent)
            if not messages:
                return
            is_current_conv = idx >= len(conversations) - 1
            if len(conversations) > 1:
                histories.append("#### 当前轮次会话" if is_current_conv else f"#### 第{idx + 1}轮会话\n\n")
            for message in messages:
                if message.sender_name == "User" and not is_current_conv and len(conversations) > 1:
                    histories.append(f"sender: User\nreceiver: {message.receiver_name}\ncontent: {message.content}")

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

                    action_report_prompt = self._format_action_report_prompt(agent=agent, message=message,
                                                                             action_report=action_report)
                    if action_report_prompt:
                        histories.append(action_report_prompt)

        history: str = self._join_history(histories, agent=agent)
        if history:
            prompt_param[self.arg_key] = history
        else:
            prompt_param[self.arg_key] = ""

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

        length = get_agent_llm_context_length(kwargs.get("agent")) - 8000
        idx = len(histories) - 1
        history_size = 0
        for index in range(len(histories) - 1, -1, -1):
            new_size = history_size + len(histories[index])
            if new_size > length:
                break
            idx = index
            history_size = new_size
        return idx, histories[idx:]

    def custom_filter(self, received_message: AgentMessage, message: GptsMessage, agent: ReasoningAgent,
                      action_report: ActionOutput,
                      sender_agent_name: str, receiver_agent_name: str) -> bool:
        return False

    def _format_action_report_prompt(self, agent: ReasoningAgent, message: GptsMessage, action_report: ActionOutput) -> \
            Optional[str]:
        return "\n".join([item for item in [
            f"message_id: {message.message_id}" if message.message_id else None,
            f"action_id: {action_report.action_id}" if action_report.action_id else None,
            f"action_handler: {message.sender_name}" if message.sender_name else None,
            f"action_name: {action_report.action_name}" if action_report.action_name else None,
            f"action: {action_report.action}" if action_report.action else None,
            f"action_input: {action_report.action_input}" if action_report.action_input else None,
            f"action_output: {action_report.content}",
        ] if item])

    def _join_history(self, histories: list, **kwargs) -> Optional[str]:
        size, kicked_histories = self.kick_actions_prompts(histories=histories, **kwargs)
        if size:
            kicked_histories = [f"由于长度限制, {size}条最早的历史数据被剔除"] + kicked_histories
        return _SEPARATOR.join(kicked_histories)


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


def session_id_from_conv_id(conv_id: str) -> str:
    idx = conv_id.rfind("_")
    return conv_id[:idx] if idx else conv_id
