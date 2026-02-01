import json
import logging
import re
import uuid
from collections import defaultdict
from enum import Enum
from typing import List, Optional, Dict, Union, Tuple

from derisk.agent import ActionOutput, ConversableAgent
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan

from derisk.agent.core.schema import Status
from derisk.agent.core.types import MessageType
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.agent.agents.knowledge.action.doc_action import DOC_ACTION
from derisk_ext.agent.agents.knowledge.action.doc_structure import OUTLINE_STRUCTURE_ACTION
from derisk_ext.vis.common.tags.derisk_work_space import WorkSpaceContent
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.derisk_vis_window2_converter import \
    DeriskIncrVisWindow2Converter
from derisk_ext.vis.derisk.tags.drsk_browser import DrskBrowser, DrskBrowserContent
from derisk_ext.vis.derisk.tags.drsk_content import DrskTextContent, DrskContent
from derisk_ext.vis.derisk.tags.drsk_doc import GenerateDocTypeEnum
from derisk_ext.vis.derisk.tags.drsk_doc_report import DrskDocReport
from derisk_ext.vis.derisk.tags.drsk_msg import DrskMsgContent
from derisk_ext.vis.derisk.tags.drsk_outline import DrskOutline
from derisk_ext.vis.derisk.tags.knowledge_window import KnowledgeSpaceWindow, KnowledgeWindowContent

from derisk_ext.vis.derisk.tags.knowledge_planning_window import \
    KnowledgeTaskContent, KnowledgePlansContent, \
    KnowledgePlanningContent
from derisk_ext.vis.nex.tags.drsk_msg import DrskMsg
from derisk_ext.vis.nex.tags.drsk_thinking import DrskThinkingContent

from derisk_ext.vis.vis_protocol_data import UpdateType

logger = logging.getLogger(__name__)

FILE_AVATAR = "https://nexa-api-pre.alipay.com/api/oss/getFileByFileName?fileName=1f29ed80-e11a-46ad-967f-45132c21462e.png"
BROWSER_AVATAR = "https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*Iv0MS5hyUMwAAAAAKBAAAAgAeprcAQ/original"
SHELL_AVATAR = "https://nexa-api-pre.alipay.com/api/oss/getFileByFileName?fileName=8e00c60b-635f-4c19-949c-b8382c24c5ba.png"
VIEW_AVATAR = "https://nexa-api-pre.alipay.com/api/oss/getFileByFileName?fileName=ca671470-ca7c-4945-bc42-893377fc617f.png"


BROWSER = "browser"

class NexVisTagPackage(Enum):
    """System Vis Tags."""
    NexMessage = "nex-msg"
    NexStep = "nex-step"


class KnowledgeVisWindowConverter(DeriskIncrVisWindow2Converter):
    """Incremental task window mode protocol converter.

    """
    def __init__(self, paths: Optional[str] = None, **kwargs):
        default_tag_paths = ["derisk_ext.vis.derisk.tags", "derisk_ext.vis.common.tags"]
        super().__init__(paths if paths else default_tag_paths, **kwargs)
        self.report_uid = uuid.uuid4().hex
        self.report_round_id = uuid.uuid4().hex
        self.conv_round_id = uuid.uuid4().hex
        self.generate_title = "生成文档"
        self.generate_spec_title = "生成SPEC"

    @property
    def reuse_name(self):
        ## 复用下面转换器的前端布局
        from derisk_ext.vis.derisk.derisk_vis_window_converter import DeriskIncrVisWindowConverter
        return DeriskIncrVisWindowConverter().render_name

    def system_vis_tag_map(self):
        return {
            SystemVisTag.VisMessage.value: NexVisTagPackage.NexMessage.value,
            SystemVisTag.VisTool.value: NexVisTagPackage.NexStep.value,

            SystemVisTag.VisPlans.value: DrskVisTagPackage.DrskPlans.value,
            SystemVisTag.VisText.value: DrskVisTagPackage.DrskContent.value,
            SystemVisTag.VisThinking.value: DrskVisTagPackage.DrskThinking.value,
            SystemVisTag.VisTools.value: DrskVisTagPackage.DrskSteps.value,
            SystemVisTag.VisSelect.value: DrskVisTagPackage.DrskSelect.value,
            SystemVisTag.VisRefs.value: DrskVisTagPackage.DrskRefs.value,
        }

    @property
    def web_use(self) -> bool:
        return True

    @property
    def render_name(self):
        return "vis_window_knowledge"

    @property
    def description(self) -> str:
        return "知识生成VIS可视化布局数据转换协议"

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

        new_plans_view = ""
        doc_loading_view = ""
        if stream_msg:
            if stream_msg:
                agent_info = senders_map.get(stream_msg.get("sender"))
                prev_content = stream_msg.get("prev_content")
                if prev_content and agent_info.agent_parser:
                    stream_content = agent_info.agent_parser.parse_streaming_json(
                        prev_content, "reason"
                    )
                    if stream_content:
                        logger.info(f"stream_content is: {stream_content}")
                        items: List[KnowledgePlansContent] = [KnowledgePlansContent(
                            uid=self.conv_round_id,
                            type=UpdateType.INCR.value,
                            title="",
                            description=stream_content,
                            avatar=stream_msg.get("avatar"),
                            items=[],
                        )]
                        planning_window_content = KnowledgePlanningContent(
                            uid=stream_msg.get("conv_id"),
                            type=UpdateType.INCR.value,
                            items=items
                        )
                        new_plans_view = self.vis_inst(
                            DrskVisTagPackage.KnowledgePlanningWindow.value).sync_display(
                            content=planning_window_content.to_dict()
                        )
        if new_plans and len(new_plans) > 0:
            new_plans_map = {item.task_uid: item for item in new_plans}
            new_plans_view, doc_loading_view = await self._planning_vis_build(
                new_plans[0].conv_id, new_plans_map, senders_map, stream_msg
            )

        new_running_view = ""
        report_view = None
        human_report = None
        if gpt_msg or stream_msg:
            human_report = False
            if gpt_msg:
                from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
                if gpt_msg.receiver == HUMAN_ROLE:
                    if gpt_msg:
                        if gpt_msg.action_report:
                            action_out = gpt_msg.action_report[0]
                            if action_out.state == "chat":
                                 temp_view = await self.gen_normal_message_vis(
                                     message=gpt_msg
                                 )
                                 return temp_view
                            else:
                                report_view = await self.gen_final_report_vis(gpt_msg)
                                human_report = True

            new_running_view = await self._running_vis_build(
                gpt_msg=gpt_msg,
                stream_msg=stream_msg,
                senders_map=senders_map,
                is_first_chunk=is_first_chunk
            )
        if report_view:
            new_plans_view = new_plans_view + "\n" + report_view
        if new_plans_view and doc_loading_view:
            return json.dumps({
                "planning_window": new_plans_view,
                "running_window": doc_loading_view
            }, ensure_ascii=False)
        if new_plans_view or new_running_view:
            return json.dumps({
                "planning_window": new_plans_view,
                "running_window": "" if human_report else new_running_view
            }, ensure_ascii=False)
        # if new_plans_view and doc_loading_view:
        #     return json.dumps({
        #         "planning_window": new_plans_view,
        #         "running_window": doc_loading_view
        #     }, ensure_ascii=False)
        # if new_plans_view or new_running_view:
        #     result = {"planning_window": new_plans_view}
        #     if not human_report and new_running_view:
        #         result["running_window"] = new_running_view
        #     return json.dumps(result, ensure_ascii=False)
        else:
            return None

    async def _planning_vis_build(self, planning_uid, plans_map: Optional[Dict[str, GptsPlan]] = None,
                                  senders_map: Optional[Dict[str, "ConversableAgent"]] = None, stream_msg: Optional[Union[Dict, str]] = None):

        from derisk.agent import ResourceType
        markdown = None
        doc_loading_view = None
        plan_items_map: Dict[str, KnowledgePlansContent] = {}
        for k, v in plans_map.items():
            task_agent = senders_map.get(v.sub_task_agent)
            if v.action == "chat":
                return ""
            if v.action == ResourceType.Agent.value:
                avatar = task_agent.avatar if task_agent else None
            elif v.action == ResourceType.Tool.value:
                avatar = None
            elif v.action == ResourceType.KnowledgePack.value:
                avatar = None
            else:
                avatar = None

            from derisk_ext.agent.agents.knowledge.wiki_structure import \
                WikiStructureAgent
            if task_agent and task_agent.role == WikiStructureAgent().profile.role.default:
                markdown = DrskOutline().sync_display(
                    state=v.state,
                    message_id=v.task_uid
                )
            from derisk_ext.agent.agents.knowledge.document_generator import \
                DocGeneratorAgent
            if task_agent and task_agent.role == DocGeneratorAgent().profile.role.default and v.state != Status.COMPLETE.value:
                from derisk_ext.vis.derisk.tags.drsk_doc import DrskDoc
                doc_type = task_agent.agent_context.extra.get('generate_type')
                markdown = DrskDocReport().sync_display(
                    state=v.state,
                    message_id=v.task_uid,
                    doc_type=doc_type,
                )
                self.report_uid = v.task_uid
                self.report_round_id = v.conv_round_id
                doc_loading = DrskDoc().sync_display(
                    state=v.state,
                    type="all",
                    message_id=task_agent.agent_context.conv_id,
                    title=self.generate_spec_title if doc_type == GenerateDocTypeEnum.SPEC.value else self.generate_title,
                    doc_type=doc_type,
                )
                running_window_content = KnowledgeWindowContent(
                    uid=task_agent.agent_context.conv_session_id,
                    type=UpdateType.INCR.value,
                    agent_role=task_agent.role,
                    agent_name=task_agent.name,
                    description=task_agent.desc,
                    avatar=task_agent.avatar,
                    markdown=doc_loading,
                    generate_type="generate_doc",
                )
                doc_loading_view = self.vis_inst(
                    DrskVisTagPackage.KnowledgeSpaceWindow.value).sync_display(
                    content=running_window_content.to_dict()
                )

            if v.sub_task_title or v.sub_task_content:
                if v.result:
                    plan_task = KnowledgeTaskContent(
                        uid=k,
                        type=UpdateType.ALL.value,
                        title=v.sub_task_title or v.sub_task_content,
                        description=v.sub_task_content,
                        task_id=k,
                        status=v.state,
                        avatar=avatar,
                        model=v.agent_model,
                        agent=v.sub_task_agent,
                        task_type=v.action,
                        start_time=v.created_at,
                        markdown=v.result
                    )
                    if v.action == "tool":
                        if "download" in v.sub_task_agent:
                            plan_task.browser = parse_file_vis(v.result)
                            plan_task.markdown = ""
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = SHELL_AVATAR
                        elif "file" in v.sub_task_agent:
                            plan_task.browser = parse_file_vis(v.result)
                            plan_task.markdown = ""
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = FILE_AVATAR
                        elif "shell" in v.sub_task_agent:
                            plan_task.browser, plan_description = parse_shell_vis(
                                v.result
                            )
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = SHELL_AVATAR
                            plan_task.markdown = ""
                            if plan_description:
                                plan_task.description = plan_description
                        elif "view" in v.sub_task_agent:
                            plan_task.browser = parse_view_vis(
                                v.result
                            )
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = VIEW_AVATAR
                            plan_task.markdown = ""
                        else:
                            plan_task.browser = parse_browser_vis(v.result)
                            plan_task.markdown = ""
                            plan_task.step_avatar = BROWSER_AVATAR
                else:
                    plan_task = KnowledgeTaskContent(
                        uid=k,
                        type=UpdateType.ALL.value,
                        title=v.sub_task_title or v.sub_task_content,
                        description=v.sub_task_content,
                        task_id=k,
                        status=v.state,
                        avatar=avatar,
                        model=v.agent_model,
                        agent=v.sub_task_agent,
                        task_type=v.action,
                        start_time=v.created_at,
                        markdown=markdown
                    )
                    if v.action == "tool":
                        if "file" in v.sub_task_agent:
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = FILE_AVATAR
                        elif "shell" in v.sub_task_agent:
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = SHELL_AVATAR
                        elif "view" in v.sub_task_agent:
                            plan_task.agent = "browser_" + v.sub_task_agent
                            plan_task.step_avatar = VIEW_AVATAR
                        else:
                            plan_task.step_avatar = BROWSER_AVATAR
            else:
                plan_task = None
            if v.conv_round_id in plan_items_map:
                plan_items_map.get(v.conv_round_id).items.append(plan_task)
                self.conv_round_id = v.conv_round_id
            else:
                plan_agent = senders_map.get(v.planning_agent)
                cost = None
                if v.created_at and v.updated_at:
                    delta = v.updated_at - v.created_at
                    cost = delta.total_seconds()
                plan_items_map[v.conv_round_id] = KnowledgePlansContent(
                    uid=v.conv_round_id,
                    type=UpdateType.ALL.value,
                    title=v.task_round_title,
                    description=v.task_round_description,
                    model=v.planning_model,
                    agent=v.planning_agent,
                    start_time=v.created_at,
                    cost=cost,
                    avatar=plan_agent.avatar if plan_agent else None,
                    items=[plan_task] if plan_task else []
                )
                self.conv_round_id = v.conv_round_id
        planning_window_content = KnowledgePlanningContent(
            uid=planning_uid,
            type=UpdateType.INCR.value,
            items=plan_items_map.values()
        )

        return self.vis_inst(DrskVisTagPackage.KnowledgePlanningWindow.value).sync_display(
            content=planning_window_content.to_dict()
        ), doc_loading_view

    async def _all_running_vis_build(self, messages: List[GptsMessage],
                                     senders_map: Optional[Dict[str, "ConversableAgent"]] = None):

        from derisk.agent import ConversableAgent
        grouped = defaultdict(list)
        for message in messages:
            grouped[message.sender_name].append(message)

        from derisk_ext.vis.derisk.tags.nex_running_window import RunningContent
        agent_works: List[Union[WorkSpaceContent, RunningContent]] = []

        for k, v in grouped.items():
            sender_agent: ConversableAgent = senders_map.get(k)

            message_view_list = []
            for message in v:
                message_view_list.append(await self.gen_message_vis(message))
            running_content = RunningContent(
                uid=v[0].conv_session_id + k,
                type=UpdateType.ALL.value,
                agent_role=sender_agent.role if sender_agent else None,
                agent_name=k,
                description=sender_agent.desc if sender_agent else None,
                avatar=sender_agent.avatar if sender_agent else None,
                markdown="\n".join(message_view_list)
            )
            agent_works.append(running_content)

        return self.vis_inst(KnowledgeSpaceWindow.vis_tag()).sync_display(
            content=KnowledgeWindowContent(
                uid=messages[0].conv_session_id,
                type=UpdateType.INCR.value,
                markdown=agent_works[-1].markdown,
                # running_agent=None,
            ).to_dict()
        )

    async def _running_vis_build(self, gpt_msg: Optional[GptsMessage] = None,
                                 stream_msg: Optional[Union[Dict, str]] = None,
                                 senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
                                 is_first_chunk: bool = False, ):
        agent_name = None
        running_uid = None
        if gpt_msg:
            agent_name = gpt_msg.sender_name
            running_uid = gpt_msg.conv_session_id
        if stream_msg:
            agent_name = stream_msg.get("sender")
            running_uid = stream_msg.get("conv_session_uid")

        if agent_name not in senders_map:
            logger.error("无法获取发送该消息的应用信息！「{agent_name}」")
            return None
        agent_info = senders_map.get(agent_name)
        chat_final = False
        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        if gpt_msg and gpt_msg.receiver == HUMAN_ROLE:
            chat_final = True

        if not chat_final:
            running_agents: List[str] = []
            for k, v in senders_map.items():
                agent_state = await v.agent_state()
                if agent_state == Status.RUNNING:
                    running_agents.append(v.name)
            running_agent = running_agents

        message_view = ""
        message = None
        if gpt_msg:
            message_view = await self.gen_message_vis(gpt_msg)
            message = gpt_msg
        if stream_msg:
            message_view = await self.gen_stream_message_vis(
                stream_msg, is_first_chunk=is_first_chunk, doc_type=agent_info.agent_context.extra.get('generate_type', GenerateDocTypeEnum.YUQUE.value)
            )
        if not message_view:
            return ""
        generate_type = None
        if message:
            if message.action_report:
                action_out = message.action_report[0]
                if action_out is not None:  # noqa
                    if action_out.is_exe_success:  # noqa
                        generate_type = action_out.action
        running_window_content = KnowledgeWindowContent(
            uid=running_uid,
            type=UpdateType.INCR.value,
            agent_role=agent_info.role,
            agent_name=agent_info.name,
            description=agent_info.desc,
            avatar=agent_info.avatar,
            markdown=message_view,
            generate_type=generate_type,
        )

        return self.vis_inst(DrskVisTagPackage.KnowledgeSpaceWindow.value).sync_display(
            content=running_window_content.to_dict()
        )

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str, "GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
    ):
        if not messages:
            return None
        logger.info(f"final_view:{messages[0].conv_id}")
        new_plans_view, _ = await self._planning_vis_build(messages[0].conv_id, plans_map, senders_map)

        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        report_view = None

        re_messages = messages.copy()
        re_messages.reverse()
        for message in re_messages:
            if message.action_report:
                action_report: ActionOutput = message.action_report[0]
            if message.receiver == HUMAN_ROLE:
                if action_report.state == "chat":
                    return await self.gen_normal_message_vis(message)
                final_report_vis = await self.gen_final_report_vis(message)
                if final_report_vis:
                    report_view = final_report_vis

        new_running_view = await self._all_running_vis_build(messages, senders_map)

        if report_view:
            new_plans_view = new_plans_view + "\n" + report_view

        return json.dumps({
            "planning_window": new_plans_view,
            "running_window": new_running_view
        }, ensure_ascii=False)

    async def gen_message_vis(self, message: GptsMessage) -> str:
        view_info = ""
        if message.action_report:
            action_out = message.action_report[0]
            if action_out is not None:  # noqa
                if action_out.is_exe_success and action_out.action == OUTLINE_STRUCTURE_ACTION:
                    if action_out.extra and action_out.extra.get("title"):
                        title = action_out.extra.get("title")
                        self.generate_title = title
                if action_out.is_exe_success and action_out.action == DOC_ACTION:  # noqa
                    view = action_out.view
                    view_info = view if view else action_out.content

        return view_info



    async def gen_stream_message_vis(
            self,
            message: Dict,
            is_first_chunk: bool = False,
            doc_type: Optional[str] = None,
    ):
        """Get agent stream message."""

        thinking = message.get("thinking")
        markdown = message.get("content")
        sender_role = message.get("sender_role")
        from derisk_ext.agent.agents.knowledge.document_generator import \
            DocGeneratorAgent
        if sender_role == DocGeneratorAgent().profile.role.default:
            from derisk_ext.vis.derisk.tags.drsk_doc import DrskDoc
            return DrskDoc().sync_display(
                content=markdown,
                message_id=message.get("conv_id"),
                type="incr",
                doc_type=doc_type,
                title=self.generate_spec_title if doc_type == GenerateDocTypeEnum.SPEC.value else self.generate_title,
            )
        else:
            return None

    async def gen_normal_message_vis(self, message: GptsMessage) -> str:
        uid = message.message_id
        content_view = message.content
        if message.action_report:
            action_out = message.action_report[0]
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
            role="",
            markdown=view_info,
            name="",
            avatar=message.avatar,
            model=message.model_name,
            start_time=message.created_at,
            task_id=message.goal_id
        )
        return DrskMsg().sync_display(content=drsk_msg_content.to_dict())

    async def gen_final_report_vis(self, message: GptsMessage):
        uid = message.message_id
        content_view = message.content
        title = ""
        description = ""
        doc_type = GenerateDocTypeEnum.YUQUE.value
        if message.action_report:
            action_out = message.action_report[0]
            if action_out is not None:
                if message.message_type == MessageType.RouterMessage.value and action_out.action:
                    return None
                content_view = action_out.content
                if action_out.extra and action_out.extra.get("title"):
                    title = action_out.extra.get("title")
                if action_out.extra and action_out.extra.get("description"):
                    description = action_out.extra.get("description")
                if action_out.extra and action_out.extra.get("doc_type"):
                    doc_type = action_out.extra.get("doc_type")
                    if doc_type == GenerateDocTypeEnum.SPEC.value:
                        title = self.generate_spec_title

        report_content = DrskTextContent(
            dynamic=False, markdown=content_view, uid=uid, type="all"
        )
        args = {
            "uid": self.report_uid
        }
        doc_report = DrskDocReport(**args).sync_display(
            content=report_content.to_dict(exclude_none=True),
            title=title,
            description=description,
            doc_type=doc_type,
            message_id=self.report_uid
        )
        # task_id = str(uuid.uuid4())
        items: List[KnowledgePlansContent] = [KnowledgePlansContent(
            uid=self.report_round_id,
            type=UpdateType.INCR.value,
            title="撰写知识",
            description="",
            avatar=message.avatar,
            items=[
                KnowledgeTaskContent(
                    uid=self.report_uid,
                    task_id=self.report_uid,
                    title="撰写知识",
                    description="",
                    avatar=message.avatar,
                    type=UpdateType.INCR.value,
                    markdown=doc_report,
                    status=Status.COMPLETE.value,
                )
            ],
        )]
        planning_window_content = KnowledgePlanningContent(
            uid=message.conv_id,
            type=UpdateType.ALL.value,
            items=items
        )
        report_vis = self.vis_inst(DrskVisTagPackage.KnowledgePlanningWindow.value).sync_display(
            content=planning_window_content.to_dict()
        )
        return report_vis


def find_title(content: str) -> str:
    cleaned_text = content.replace(
        "\\\\n", "\n").replace("\\\\", "\\"
                               )
    pattern = re.compile(r"^(#+)\s*(.*)(?=\n|$)", re.MULTILINE)
    match = pattern.search(cleaned_text)

    first_title = None
    if match:
        level = len(match.group(1))
        title_text = match.group(2).strip()
        first_title = {"level": level, "text": title_text}
    if match:
        level_hashes, title_text_raw = match.groups()
    return first_title.get("text") if first_title else ""


def find_description(content: str) -> str:
    cleaned_text = content.replace("\\\\n", "\n").replace("\\\\", "\\")

    # 首先找到第一个标题
    title_pattern = re.compile(r"^(#+)\s*(.*)(?=\n|$)", re.MULTILINE)
    title_match = title_pattern.search(cleaned_text)

    if not title_match:
        return ""

    # 获取标题结束的位置
    title_end_pos = title_match.end()

    remaining_text = cleaned_text[title_end_pos:]

    remaining_text = remaining_text.lstrip()

    if not remaining_text:
        return ""

    sentence_pattern = re.compile(r"^([^#\n]+?)(?:[。.!！?？\n]|$)")
    sentence_match = sentence_pattern.match(remaining_text)

    if sentence_match:
        description = sentence_match.group(1).strip()
        return description

    return ""



def parse_browser_vis(text) -> str:
    if not isinstance(text, str):
        logger.error(
            f"Browser Tool parse_browser_step View Failed! {text}"
        )
        return []
    pattern = r'drsk-browser\s*\n\s*(\{.*?\})\s*\n```'
    match = re.search(pattern, text, re.DOTALL)

    if match:
        json_str = match.group(1)
        json_str = json_str.replace(r'\"', '"')
        data = json.loads(json_str)
        data["data_type"] = "image"
        return json.dumps(data, ensure_ascii=False)
    return ""

def parse_file_vis(text) -> str:
    if not isinstance(text, str):
        logger.error(
            f"File Tool parse_file_step View Failed! {text}"
        )
        return []
    pattern = r'nex-step\s*\n\s*(\{.*?\})\s*\n```'
    match = re.search(pattern, text, re.DOTALL)

    if match:
        json_str = match.group(1)
        data = json.loads(json_str)
        tool_args =data.get("tool_args")
        description = "Derisk正在使用电脑-"
        if tool_args.get("description"):
            description += + tool_args.get("description")
        elif tool_args.get("path"):
            description += + tool_args.get("path")
        file_content = DrskBrowserContent(
            dynamic=False,
            uid=data.get("uid"),
            type="all",
            current_index=0,
            title="Derisk的电脑",
            items=[
                {
                    "url": data.get("path"),
                    "markdown": data.get("tool_result"),
                    "web_image":"",
                    "description": description,
                    "action":data.get("tool_name"),
                    "avatar":FILE_AVATAR,
                    "data_type":"markdown",
                }
            ]
        )
        return json.dumps(file_content.dict(), ensure_ascii=False)
    return ""

def parse_shell_vis(text) -> Tuple[str, str]:
    if not isinstance(text, str):
        logger.error(
            f"File Tool parse_file_step View Failed! {text}"
        )
        return []
    pattern = r'nex-step\s*\n\s*(\{.*?\})\s*\n```'
    match = re.search(pattern, text, re.DOTALL)
    plan_description = ""
    if match:
        json_str = match.group(1)
        data = json.loads(json_str)
        tool_args =data.get("tool_args")
        tool_result =data.get("tool_result")
        plan_description = f"正在执行命令 + {tool_args.get('command')}"
        file_content = DrskBrowserContent(
            dynamic=False,
            uid=data.get("uid"),
            type="all",
            current_index=0,
            title="Derisk的电脑",
            items=[
                {
                    "url": data.get("tool_name"),
                    "command": tool_args.get("command"),
                    "command_result": get_shell_result_content(tool_result),
                    "web_image":"",
                    "description": "Derisk正在使用终端-执行命令 " + tool_args.get("command"),
                    "action":data.get("tool_name"),
                    "avatar":SHELL_AVATAR,
                    "data_type": "shell",
                }
            ]
        )
        # data = json.loads(json_str)
        return json.dumps(file_content.dict(), ensure_ascii=False), plan_description
    return "", plan_description


def parse_view_vis(text) -> str:
    if not isinstance(text, str):
        logger.error(
            f"File Tool parse_view_vis View Failed! {text}"
        )
        return []
    pattern = r'nex-step\s*\n\s*(\{.*?\})\s*\n```'
    match = re.search(pattern, text, re.DOTALL)

    if match:
        json_str = match.group(1)
        data = json.loads(json_str)
        tool_args =data.get("tool_args")
        file_content = DrskBrowserContent(
            dynamic=False,
            uid=data.get("uid"),
            type="all",
            current_index=0,
            title="Derisk的电脑",
            items=[
                {
                    "url": tool_args.get("path"),
                    "markdown": data.get("tool_result"),
                    "web_image":"",
                    "description": "Derisk正在使用电脑-读取文件" + tool_args.get("path"),
                    "action":data.get("tool_name"),
                    "avatar":VIEW_AVATAR,
                    "data_type":"markdown",
                }
            ]
        )
        return json.dumps(file_content.dict(), ensure_ascii=False)
    return ""


def get_shell_result_content(text):
    """
    获取'结果:'后面的内容
    如果没有匹配到，返回原文本
    """
    if '结果:' in text:
        # 找到'结果:'的位置，返回其后的所有内容
        index = text.find('结果:')
        return text[index + len('结果:'):].strip()
    else:
        return text



