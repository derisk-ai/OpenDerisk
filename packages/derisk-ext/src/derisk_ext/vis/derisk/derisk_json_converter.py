import json
import logging
from typing import List, Optional, Dict, Union

from derisk.agent import ActionOutput, UserProxyAgent
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.vis.vis_converter import VisProtocolConverter, SystemVisTag
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.tags.drsk_msg import DrskTaskPlanContent

NONE_GOAL_PREFIX: str = "none_goal_count_"
logger = logging.getLogger(__name__)


class DeriskJsonConverter(VisProtocolConverter):


    def __init__(self, paths: Optional[str] = None, **kwargs):
        self._derisk_url = kwargs.get("derisk_url", "")
        default_tag_paths = ["derisk_ext.vis.derisk.tags"]
        super().__init__(paths if paths else default_tag_paths)

    @property
    def render_name(self):
        return "derisk_json_all"

    @property
    def description(self) -> str:
        return "JSON数据转换器(返回JSON格式数据，API使用，页面无法展示)"

    @property
    def web_use(self) -> bool:
        return False

    def tag_config(self):
        return {"derisk_url": self._derisk_url}

    def system_vis_tag_map(self):
        return {
            SystemVisTag.VisMessage.value: DrskVisTagPackage.DrskMessage.value,
            SystemVisTag.VisPlans.value: DrskVisTagPackage.DrskPlans.value,
            SystemVisTag.VisText.value: DrskVisTagPackage.DrskContent.value,
            SystemVisTag.VisThinking.value: DrskVisTagPackage.DrskThinking.value,
            SystemVisTag.VisTool.value: DrskVisTagPackage.DrskStep.value,
            SystemVisTag.VisTools.value: DrskVisTagPackage.DrskSteps.value,
        }

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str,"GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
    ):
        deal_messages: List[GptsMessage] = []

        for message in messages:
            if not message.action_report and message.receiver != UserProxyAgent.role:
                continue
            deal_messages.append(message)

        deal_messages = sorted(deal_messages, key=lambda _message: _message.rounds)
        vis_items: List[dict[any, any]] = []
        for message in deal_messages:
            vis_items.append(await self.gen_message_vis(message))

        return json.dumps(vis_items)

    async def visualization_stream(self, stream_msg: Optional[Union[Dict, str]] = None):
        return json.dump(await self.gen_stream_message_vis(stream_msg))

    async def visualization(
        self,
        messages: List[GptsMessage],
        plans_map: Optional[Dict[str, GptsPlan]] = None,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
    ):
        ## 使用增量传递模式，复用VIS协议规范
        ##  增量数据和全量数据进行逻辑比对

        # 当前全量模式
        ## 1.过滤传递消息
        ## 2.合并重试消息
        deal_messages: List[GptsMessage] = []

        for message in messages:
            if not message.action_report and message.receiver != UserProxyAgent.role:
                continue
            deal_messages.append(message)

        deal_messages = sorted(deal_messages, key=lambda _message: _message.rounds)
        vis_items: List[dict[any, any]] = []
        for message in deal_messages:
            vis_items.append(await self.gen_message_vis(message))
        if stream_msg:
            vis_items.append(await self.gen_stream_message_vis(stream_msg))
        return json.dumps(vis_items)

    async def gen_message_vis(self, message: GptsMessage) -> dict:
        # from derisk.agent import get_agent_manager
        # agent_mange = get_agent_manager()
        view_infos: List[str] = []
        if message.action_report:
            for action_out in message.action_report:
                if action_out is not None:  # noqa
                    if action_out.is_exe_success:  # noqa
                        view_infos.append(action_out.content)
        view_info = "\n".join(view_infos)
        if view_info:
            view_info = message.content
        content = DrskTaskPlanContent(
            uid=message.conv_id,
            app_code=message.app_code,
            type="all",
            thinking=message.thinking,
            content=view_info,
            role=message.role,
            name=message.sender,
            avatar=message.avatar,
            model=message.model_name,
            dynamic=False,
        )
        return content.to_dict()

    async def gen_stream_message_vis(
        self,
        message: Dict,
    ):
        """Get agent stream message."""

        content = DrskTaskPlanContent(
            uid=message.get("conv_id", ""),
            app_code=message.get("app_code"),
            type="all",
            thinking=message.get("thinking"),
            content=message.get("content"),
            role=message.get("sender"),
            name=message.get("sender"),
            avatar=message.get("avatar"),
            model=message.get("model"),
            dynamic=False,
        )

        return content.to_dict()
