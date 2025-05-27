from typing import List

from derisk.agent import AgentMessage
from derisk.agent.core.memory.gpts import GptsMessage
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import ReasoningAgent
from derisk_ext.reasoning_arg_supplier.default.default_history_arg_supplier import DefaultHistoryArgSupplier

_NAME = "SENDER_RECEIVER_HISTORY_ARG_SUPPLIER"
_DESCRIPTION = "history: 只看自己发送/发给自己的消息"

_SEPARATOR = "\n\n--------------\n\n"


class SenderReceiverHistoryArgSupplier(DefaultHistoryArgSupplier):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    def kick_message(
        self,
        messages: List[GptsMessage],
        received_message: AgentMessage,
        agent: ReasoningAgent,
    ) -> List[GptsMessage]:
        return [message for message in messages if message.sender_name == agent.name or message.receiver_name == agent.name]
