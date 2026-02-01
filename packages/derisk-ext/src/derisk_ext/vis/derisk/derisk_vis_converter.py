import json
import logging
from enum import Enum
from typing import List, Optional, Dict, Union

from derisk.agent import ActionOutput, UserProxyAgent
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.vis.vis_converter import VisProtocolConverter, SystemVisTag
from derisk_ext.vis.derisk.tags.drsk_content import DrskContent, DrskTextContent
from derisk_ext.vis.derisk.tags.drsk_msg import DrskMsg, DrskMsgContent
from derisk_ext.vis.derisk.tags.drsk_thinking import DrskThinking, DrskThinkingContent

NONE_GOAL_PREFIX: str = "none_goal_count_"
logger = logging.getLogger(__name__)


class DrskVisTagPackage(Enum):
    """System Vis Tags."""
    NexMessage = "nex-msg"
    NexStep = "nex-step"

    DrskMessage = "drsk-msg"
    DrskPlans = "drsk-plan"
    DrskStep = "drsk-step"
    DrskSteps = "drsk-steps"
    DrskThinking = "drsk-thinking"
    DeriskThinking = "d-thinking"
    DrskContent = "drsk-content"
    DrskSelect = "drsk-select"
    DrskRefs = "drsk-refs"
    NexPlanningWindow = "nex-planning-window"
    NexRunningWindow = "nex-running-window"
    DrskConfirm = "drsk-confirm"

    WorkFolder = 'work-folder'
    NexReport = "nex-report"




class DeriskVisConverter(VisProtocolConverter):
    def __init__(self, paths: Optional[str] = None, **kwargs):
        default_tag_paths = ["derisk_ext.vis.derisk.tags", "derisk_ext.vis.common.tags"]
        super().__init__(paths if paths else default_tag_paths, **kwargs)

    @property
    def web_use(self) -> bool:
        return False
    @property
    def render_name(self):
        return "derisk_vis_all"


    def system_vis_tag_map(self):
        return {
            SystemVisTag.VisMessage.value: DrskVisTagPackage.DrskMessage.value,
            SystemVisTag.VisPlans.value: DrskVisTagPackage.DrskPlans.value,
            SystemVisTag.VisText.value: DrskVisTagPackage.DrskContent.value,
            SystemVisTag.VisThinking.value: DrskVisTagPackage.DrskThinking.value,
            SystemVisTag.VisTool.value: DrskVisTagPackage.DrskStep.value,
            SystemVisTag.VisTools.value: DrskVisTagPackage.DrskSteps.value,
            SystemVisTag.VisSelect.value: DrskVisTagPackage.DrskSelect.value,
            SystemVisTag.VisRefs.value: DrskVisTagPackage.DrskRefs.value,
            # SystemVisTag.VisChart.value: GptVisTagPackage.Chart.value,
            # SystemVisTag.VisCode.value: GptVisTagPackage.Code.value,
            # SystemVisTag.VisTool.value: GptVisTagPackage.Plugin.value,
            # SystemVisTag.VisDashboard.value: GptVisTagPackage.Dashboard.value,
        }

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str,"GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
    ):
        return await self.visualization(messages, plans_map)

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
        vis_items: List[str] = []
        for message in deal_messages:
            vis_items.append(await self.gen_message_vis(message))
        message_view = "\n".join(vis_items)
        if stream_msg:
            temp_view = await self.gen_stream_message_vis(stream_msg)
            message_view = message_view + "\n" + temp_view
        return message_view

    async def gen_message_vis(self, message: GptsMessage) -> str:
        # from derisk.agent import get_agent_manager
        # agent_mange = get_agent_manager()
        uid = message.message_id
        action_report_str = message.action_report
        view_info = message.content
        if action_report_str and len(action_report_str) > 0:
            action_out = ActionOutput.from_dict(json.loads(action_report_str))
            if action_out is not None:  # noqa
                if action_out.is_exe_success:  # noqa
                    view = action_out.view
                    view_info = view if view else action_out.content

        thinking = message.thinking
        if thinking:
            thinking_content = DrskThinkingContent(
                markdown=message.thinking,
                uid=uid + "_thinking",
                type="all",
                think_link=f"{self._derisk_url}/nexa/drsk/thinking/detail?message_id={uid}",
            )
            vis_thinking = self.vis_inst(SystemVisTag.VisThinking.value).sync_display(
                content=thinking_content.to_dict()
            )
            view_info = vis_thinking + "\n" + view_info

        drsk_msg_content = DrskMsgContent(
            uid=uid,
            type="all",
            role=message.sender,
            markdown=view_info,
            # thinking tasks内置包含？ 还是外链
            name=None,
            avatar=message.avatar,
            model=message.model_name,
        )
        return DrskMsg().sync_display(content=drsk_msg_content.to_dict())

    async def gen_stream_message_vis(
        self,
        message: Dict,
    ):
        """Get agent stream message."""

        thinking = message.get("thinking")
        markdown = message.get("content")
        uid = message.get("uid")
        avatar = message.get("avatar")
        action_report: Optional[ActionOutput] = message.get("action_report")
        msg_markdown = ""
        if thinking:
            thinking_content = DrskThinkingContent(
                markdown=thinking,
                uid=uid + "_thinking",
                type="incr",
                think_link=f"{self._derisk_url}/nexa/drsk/thinking/detail?message_id={uid}",
            )
            vis_thinking = DrskThinking().sync_display(
                content=thinking_content.to_dict()
            )
            msg_markdown = vis_thinking

        if markdown or action_report:
            act_markdown = None
            if action_report:
                act_markdown = action_report.view or action_report.content
            llm_content = DrskTextContent(
                dynamic=True, markdown=act_markdown or markdown, uid=uid + "_content", type="incr"
            )
            vis_content = DrskContent().sync_display(
                content=llm_content.to_dict(exclude_none=True)
            )
            msg_markdown = msg_markdown + "\n" + vis_content
        content = DrskMsgContent(
            uid=uid,
            type="all",
            markdown=msg_markdown,
            role=message.get("sender"),
            name=message.get("sender"),
            avatar=avatar,
            model=message.get("model"),
        )

        return await DrskMsg().display(content=content.to_dict())
