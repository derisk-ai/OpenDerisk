import json
import logging
import uuid
from typing import List, Optional, Dict, Union

from derisk.agent import ActionOutput, UserProxyAgent
from derisk.agent.core.action.base import AskUserType
from derisk.agent.core.reasoning.reasoning_action import AgentAction
from derisk.agent.core.types import MessageType
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.vis.schema import VisConfirm, VisPlansContent, VisTextContent, VisTaskContent, VisInteract
from derisk.vis.vis_converter import SystemVisTag
from  .derisk_vis_converter import DeriskVisConverter
from derisk_ext.vis.derisk.ask_user.manager import convert

from derisk_ext.vis.derisk.tags.drsk_content import DrskTextContent, DrskContent
from derisk_ext.vis.derisk.tags.drsk_interact import DrskInteract
from derisk_ext.vis.derisk.tags.drsk_msg import DrskMsgContent
from derisk_ext.vis.derisk.tags.drsk_thinking import DrskThinkingContent, DrskThinking
from derisk_serve.agent.db import GptsMessagesDao

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
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
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
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
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

    async def _gen_action_view(self, message: GptsMessage):
        return message.view()

    async def gen_final_report_vis(self, message: GptsMessage):
        uid = message.message_id + "_report"

        if message.message_type == MessageType.RouterMessage.value:
            # final_report屏蔽路由消息
            return None
        content_view = await self._gen_action_view(message)

        report_content = DrskTextContent(
            dynamic=False, markdown=content_view, uid=uid + "_content", type="all"
        )
        return DrskContent().sync_display(
            content=report_content.to_dict(exclude_none=True)
        )

    async def gen_message_vis(self, message: GptsMessage) -> str:
        # from derisk.agent import get_agent_manager
        # agent_mange = get_agent_manager()
        uid = message.message_id
        content_view = await self._gen_action_view(message)

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
        action_report: Optional[ActionOutput] = message.get("action_report")
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
            msg_markdown = msg_markdown + "\n\n" + vis_content
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

    async def gen_final_notice_vis(self, messages: list[GptsMessage]) -> Optional[str]:
        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        view: Optional[str] = None
        for message in messages:
            if message.receiver != HUMAN_ROLE or not message.action_report:
                continue

            view = await self.gen_one_final_notice_vis(message) or view
        return view

    async def gen_one_final_notice_vis(self, message: GptsMessage) -> Optional[str]:
        action_report = message.action_report[0]
        if not action_report or not action_report.extra or not action_report.extra.get("ask_user_content"):
            return None

        view = DrskInteract().sync_display(content=VisInteract(
            uid=message.message_id + "_interact",
            message_id=message.message_id + "_interact",
            type="all",
            title="请补充信息",
            markdown=action_report.extra.get("ask_user_content"),
            interact_type="notice",
            position="tail",
        ).to_dict())
        return view

    async def gen_ask_user_vis(self, message: GptsMessage) -> Optional[str]:
        ask_user_action_reports = await self.ask_user_action_reports(message.action_report)
        if not ask_user_action_reports:
            return None

        # 按照ask_type分类处理
        ask_user_action_report_map = {}
        for ask_user_action_report in ask_user_action_reports:
            ask_type = ask_user_action_report.ask_type
            reports = ask_user_action_report_map.get(ask_type, [])
            reports.append(ask_user_action_report)
            ask_user_action_report_map[ask_type] = reports
        vis = [vs for ask_type, action_reports in ask_user_action_report_map.items() if
               (vs := await convert(ask_type, action_reports, message))]
        return "\n\n".join(vis) if vis else None

    async def ask_user_action_reports(self, parsed_action_reports: list[ActionOutput]) -> list[ActionOutput]:
        action_reports: list[ActionOutput] = []
        if not parsed_action_reports:
            return action_reports
        try:
            for action_report in parsed_action_reports:
                if not action_report.ask_user:
                    # 无需询问用户
                    continue
                # elif action_report.name != "Agent":
                elif action_report.name != "Agent" or action_report.ask_type == AskUserType.CONCLUSION_INCOMPLETE.value:
                    # 询问用户
                    action_reports.append(action_report)
                else:
                    # 子Agent询问用户
                    message_id = action_report.content
                    if not message_id:
                        continue
                    gpts_message = GptsMessagesDao().get_by_message_id(message_id)
                    if not gpts_message:
                        continue
                    action_reports += await self.ask_user_action_reports(gpts_message.action_report)
        except Exception as e:
            logger.exception("ask_user_action_reports exception")
            return action_reports

        return action_reports

    async def _render_actions_view(
        self, action_reports: list[ActionOutput], message_id: str
    ) -> str:
        # AgentAction放前面 统一放在VisPlansContent里
        # 其他Action(Tool/RAG)放后面 统一放在VisStepContent里
        all_views: List[str] = []
        agent_action_contents: List[VisTaskContent] = []
        agent_action_views: List[str] = []
        other_action_views: List[str] = []
        for output in action_reports:
            if output.name == AgentAction.name:

                if not output.view:
                    content = VisTaskContent(task_uid=uuid.uuid4().hex, task_content=output.action_input,
                                             task_name=output.action_input, agent_name=output.action)
                    agent_action_contents.append(content)
                else:
                    agent_action_views.append(output.view)
            else:
                other_action_views.append(output.view or output.content)
        if action_reports[0].thoughts:
            reasoning_view = self.vis_inst(SystemVisTag.VisText.value).sync_display(content=VisTextContent(
                markdown=action_reports[0].thoughts, type="all", uid=message_id + "_reason", message_id=message_id
            ).to_dict())
            all_views.append(reasoning_view)
        if agent_action_views:
            all_views.extend(agent_action_views)
        if agent_action_contents:
            all_views.append(self.vis_inst(vis_tag=SystemVisTag.VisPlans.value).sync_display(
                content=VisPlansContent(
                    uid=message_id + "_action_agent",
                    type="all",
                    message_id=message_id + "_action_agent",
                    tasks=agent_action_contents,
                ).to_dict()
            ))
        if other_action_views:
            all_views.extend(other_action_views)

        return "\n".join(all_views)

    async def _render_confirm_action(self, message_id: str, action_reports: list[ActionOutput]) -> str:

        def _make_one_markdown(report: ActionOutput) -> str:
            return f"* 动作:{report.action_name}({report.action}),参数:{report.action_input}"

        markdown = "\n\n".join([_make_one_markdown(report)
                                for report in action_reports if report.ask_user])
        if not markdown:
            return ""

        markdown = "将执行如下动作:\n\n" + markdown + "\n\n是否确认执行?"
        return await self.vis_inst(vis_tag=SystemVisTag.VisConfirm.value).display(
            content=VisConfirm(
                uid=message_id + "_confirm",
                message_id=message_id + "_confirm",
                type="all",
                disabled=False,
                markdown=markdown,
                extra={"approval_message_id": message_id}
            ).to_dict()
        )