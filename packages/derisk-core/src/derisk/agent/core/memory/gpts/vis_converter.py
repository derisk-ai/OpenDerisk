import json
from abc import ABC
from typing import List, Optional, Union, Dict

from derisk.agent import ActionOutput
from derisk.vis import vis_client, VisAgentMessages, VisAgentPlans
from . import GptsMessage, GptsPlan


class VisProtocolConverter(ABC):
    async def visualization(
        self,
        messages: List[GptsMessage],
        plans: Optional[List[GptsPlan]] = None,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
    ):
        pass


class DefaultVisConverter(VisProtocolConverter):
    async def visualization(
        self,
        messages: List[GptsMessage],
        plans: Optional[List[GptsPlan]] = None,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
    ):
        simple_message_list = []
        for message in messages:
            if message.sender == "Human":
                continue

            action_report_str = message.action_report
            view_info = message.content
            action_out = None
            if action_report_str and len(action_report_str) > 0:
                action_out = ActionOutput.from_dict(json.loads(action_report_str))
            if action_out is not None:
                view_info = action_out.content

            simple_message_list.append(
                {
                    "sender": message.sender,
                    "receiver": message.receiver,
                    "model": message.model_name,
                    "markdown": view_info,
                }
            )
        if temp_msg:
            simple_message_list.append(self._view_stream_message(temp_msg))

        return simple_message_list

    async def _view_stream_message(self, message: Union[Dict, str]):
        """Get agent stream message."""
        messages_view = []
        if isinstance(message, dict):
            messages_view.append(
                {
                    "sender": message["sender"],
                    "receiver": message["receiver"],
                    "model": message["model"],
                    "markdown": message["markdown"],
                }
            )
        else:
            messages_view.append(
                {
                    "sender": "?",
                    "receiver": "?",
                    "model": "?",
                    "markdown": message,
                }
            )

        return messages_view
