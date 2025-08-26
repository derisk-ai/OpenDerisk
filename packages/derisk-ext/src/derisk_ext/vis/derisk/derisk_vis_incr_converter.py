import json
import logging
from typing import List, Optional, Dict, Union

from derisk.agent import ActionOutput, UserProxyAgent
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.vis.derisk.derisk_vis_converter import  DeriskVisConverter
from derisk_ext.vis.derisk.tags.drsk_content import DrskTextContent, DrskContent
from derisk_ext.vis.derisk.tags.drsk_msg import DrskMsgContent
from derisk_ext.vis.derisk.tags.drsk_thinking import DrskThinkingContent, DrskThinking
from derisk_ext.vis.derisk.tags.nex_report import NexReport

NONE_GOAL_PREFIX: str = "none_goal_count_"
logger = logging.getLogger(__name__)


class DeriskVisIncrConverter(DeriskVisConverter):


    @property
    def incremental(self) -> bool:
        return True
    @property
    def web_use(self) -> bool:
        return True
    @property
    def render_name(self):
        return "derisk_vis_incr"
    @property
    def description(self) -> str:
        return "(消息模式)VIS可视化布局数据转换协议"

    async def visualization(
            self,
            messages: List[GptsMessage],
            plans_map: Optional[Dict[str, GptsPlan]] = None,
            gpt_msg: Optional[GptsMessage] = None,
            stream_msg: Optional[Union[Dict, str]] = None,
            new_plans: Optional[List[GptsPlan]] = None,
            is_first_chunk: bool = False,
            incremental: bool = False,
            senders_map: Optional[Dict[str, "ConversableAgent"]] = None
    ):
        # logger.info(f"visualization:{messages},{is_first_chunk}")
        ## 使用增量传递模式
        message_view = ""
        if gpt_msg:
            temp_view = await self.gen_message_vis(gpt_msg)
            message_view = message_view + "\n" + temp_view
        if stream_msg:
            temp_view = await self.gen_stream_message_vis(
                stream_msg, is_first_chunk=is_first_chunk
            )
            if temp_view:
                message_view = message_view + "\n" + temp_view
        return message_view

    async def final_view(
            self,
            messages: List["GptsMessage"],
            plans_map: Optional[Dict[str, "GptsPlan"]] = None,
            senders_map: Optional[Dict[str, "ConversableAgent"]] = None
    ):
        deal_messages: List[GptsMessage] = []

        for message in messages:
            if not message.action_report and message.receiver != UserProxyAgent.role:
                continue
            deal_messages.append(message)

        deal_messages = sorted(deal_messages, key=lambda _message: _message.rounds)
        vis_items: List[str] = []
        for message in deal_messages:
            vis_items.append(await self.gen_message_vis(message))
        message_view = "\n".join(vis_items)
        return message_view

    async def gen_final_report_vis(self, message: GptsMessage):
        uid = message.message_id + "_report"
        action_report_str = message.action_report
        content_view = message.content
        if action_report_str and len(action_report_str) > 0:
            action_out = ActionOutput.from_dict(json.loads(action_report_str))
            if action_out is not None:  # noqa
                view = action_out.observations or action_out.view
                content_view = view if view else action_out.content


        report_content = DrskTextContent(
            dynamic=False, markdown=content_view, uid=uid + "_content", type="all"
        )
        return NexReport().sync_display(
            content=report_content.to_dict(exclude_none=True)
        )



    async def gen_message_vis(self, message: GptsMessage) -> str:
        # from derisk.agent import get_agent_manager
        # agent_mange = get_agent_manager()
        uid = message.message_id
        action_report_str = message.action_report
        content_view = message.content
        if action_report_str and len(action_report_str) > 0:
            action_out = ActionOutput.from_dict(json.loads(action_report_str))
            if action_out is not None:  # noqa
                if action_out.is_exe_success:  # noqa
                    view = action_out.view
                    content_view = view if view else action_out.content

        view_info = ""
        thinking = message.thinking
        if thinking:
            thinking_content = DrskThinkingContent(
                dynamic=False,
                markdown=message.thinking,
                uid=uid + "_thinking",
                type="all",
                think_link=f"{self._derisk_url}/nexa/drsk/thinking/detail?message_id={uid}",
            )
            vis_thinking = self.vis_inst(SystemVisTag.VisThinking.value).sync_display(
                content=thinking_content.to_dict()
            )
            view_info = vis_thinking + "\n" + view_info

        if content_view:
            llm_content = DrskTextContent(
                dynamic=False, markdown=content_view, uid=uid + "_content", type="all"
            )
            vis_content = DrskContent().sync_display(
                content=llm_content.to_dict(exclude_none=True)
            )
            view_info = view_info + "\n" + vis_content

        drsk_msg_content = DrskMsgContent(
            uid=uid,
            type="all",
            dynamic=False,
            role=message.sender,
            markdown=view_info,
            # thinking tasks内置包含？ 还是外链
            name=message.sender_name,
            avatar=message.avatar,
            model=message.model_name,
            start_time=message.created_at,
            task_id=message.goal_id
        )
        return self.vis(SystemVisTag.VisMessage.value)().sync_display(content=drsk_msg_content.to_dict())


    async def gen_stream_message_vis(
            self,
            message: Dict,
            is_first_chunk: bool = False,
    ):
        """Get agent stream message."""

        thinking = message.get("thinking")
        markdown = message.get("content")
        uid = message.get("uid")
        avatar = message.get("avatar")
        msg_markdown = ""
        if thinking:
            if is_first_chunk:
                thinking_content = DrskThinkingContent(
                    dynamic=True,
                    markdown=thinking,
                    uid=uid + "_thinking",
                    type="incr",
                    think_link=f"{self._derisk_url}/nexa/drsk/thinking/detail?message_id={uid}",
                )
            else:
                thinking_content = DrskThinkingContent(
                    dynamic=True,
                    markdown=thinking,
                    uid=uid + "_thinking",
                    type="incr",
                )
            vis_thinking = DrskThinking().sync_display(
                content=thinking_content.to_dict(exclude_none=True)
            )
            msg_markdown = vis_thinking
        if markdown:
            llm_content = DrskTextContent(
                dynamic=True, markdown=markdown, uid=uid + "_content", type="incr"
            )
            vis_content = DrskContent().sync_display(
                content=llm_content.to_dict(exclude_none=True)
            )
            msg_markdown = msg_markdown + "\n" + vis_content
        if len(msg_markdown) > 0:
            content = DrskMsgContent(
                uid=uid,
                type="incr",
                markdown=msg_markdown,
                role=message.get("sender"),
                name=message.get("sender"),
                avatar=avatar,
                model=message.get("model"),
                start_time=message.get("start_time"),


            )

            return await self.vis(SystemVisTag.VisMessage.value)().display(content=content.to_dict())
        else:
            return None
