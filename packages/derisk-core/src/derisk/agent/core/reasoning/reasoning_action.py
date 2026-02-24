import json
import logging
import time
from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, Field

from derisk._private.pydantic import model_to_dict
from ..agent import (
    ActionOutput,
    AgentMessage,
    AgentContext,
    AgentMemory,
)
from ..action.base import AskUserType, Action
from .reasoning_engine import REASONING_LOGGER as LOGGER
from ..schema import ActionInferenceMetrics, Status
from ...resource import ResourcePack
from derisk.context.window import ContextWindow
from derisk.util.tracer import root_tracer
from derisk.vis import SystemVisTag
from derisk.vis.schema import VisStepContent

from derisk_serve.agent.resource.knowledge_pack import KnowledgePackSearchResource, \
    KnowledgeActionOperation
from ... import GptsMemory, AgentResource, ConversableAgent, ResourceType, Resource
from derisk_serve.rag.api.schemas import KnowledgeSearchResponse

logger = logging.getLogger(__name__)


class AgentActionInput(BaseModel):
    """Plugin input model."""

    agent_name: str = Field(
        ...,
        description="Identifier of the destination agent",
    )
    content: str = Field(
        ...,
        description="Instructions or information sent to the agent.",
    )
    thought: Optional[str] = Field(None, description="Summary of thoughts to the user")
    extra_info: Optional[dict] = Field(
        None,
        description="Additional metadata or contextual data supporting the agent's action.",
    )

    def to_dict(self):
        return model_to_dict(self)


class AgentAction(Action[AgentActionInput]):
    name = "Agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag = SystemVisTag.VisPlans.value

    async def _action_init_push(self, gpts_memory: GptsMemory, agent: "ConversableAgent",  message: AgentMessage,
                                agent_context: AgentContext, start_time, content:Optional[str] = None):
        init_action_outs = [ActionOutput(
            name=self.name,
            content=content or f"{agent.name}Agent启动中",
            start_time=start_time,
            action_id=self.action_uid,
            thoughts=self.action_input.thought,
            action=self.action_input.agent_name,
            action_input=self.action_input.to_dict(),
            state=Status.RUNNING.value,
        )]

        ## 展示工具任务基础信息
        await gpts_memory.push_message(conv_id=agent.agent_context.conv_id, stream_msg={
            "uid": message.message_id,
            "type": "all",
            "sender": agent.name or agent.role,
            "goal_id": message.goal_id,
            "sender_role": agent.role,
            "message_id": message.message_id,
            "conv_id": agent_context.conv_id,
            "conv_session_uid": agent_context.conv_session_id,
            "app_code": agent_context.gpts_app_code,
            "start_time": start_time,
            "action_report": init_action_outs
        }, )

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        action_input = self.action_input or AgentActionInput.model_validate_json(
            json_data=ai_message
        )
        metrics = ActionInferenceMetrics()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        try:

            action_id = kwargs.get("action_id", None)
            sender: ConversableAgent = kwargs["agent"]
            recipient = next(
                (agent for agent in sender.agents if
                 agent.name == action_input.agent_name or agent.agent_context.agent_app_code == action_input.agent_name),
                None,
            )
            if not recipient:
                raise RuntimeError("recipient can't be empty")

            received_message = (
                kwargs["message"] if "message" in kwargs else AgentMessage.init_new()
            )
            start_time = datetime.now()
            memory: AgentMemory = kwargs.get('memory')
            agent: ConversableAgent = kwargs.get('agent')
            agent_context: AgentContext = kwargs.get('agent_context')
            message_id: str = kwargs.get('message_id')
            self._render = kwargs.get("render_protocol") or self._render
            current_message: AgentMessage = kwargs.get('current_message')

            # 初始化AgentAction的展示
            await self._action_init_push(gpts_memory=memory.gpts_memory, agent=agent, message=current_message,
                                         agent_context=agent_context, start_time=start_time, content=action_input.content)

            #  构建转发给Agent的新消息
            message = AgentMessage.init_new(
                content=(
                    action_input.content
                    + "\n\n"
                    + json.dumps(action_input.extra_info, ensure_ascii=False)
                ),
                context=(received_message.context or {}) | (action_input.extra_info or {}),
                rounds=await sender.memory.gpts_memory.next_message_rounds(sender.not_null_agent_context.conv_id),
                name=sender.name,
                role=sender.role,
                show_message=False,
                observation=action_input.content,
                current_goal=action_input.content,
                goal_id=received_message.goal_id,
            )
            # message.goal_id = kwargs["action_id"] if "action_id" in kwargs else ""
            # message.current_goal = action_input.content
            # 合并context 且action_input.extra_info优先级更高
            message.message_id = self.action_uid
            message.context = (message.context or {}) | (action_input.extra_info or {})

            LOGGER.info(f"[ACTION]---------->   Agent Action [{sender.name}] --> [{recipient.name}]")

            await ContextWindow.create(agent=recipient, task_id=message.message_id)
            answer: AgentMessage = await sender.send(message=message, recipient=recipient, request_reply=True,
                                                     request_sender_reply=False)

            from derisk.agent.core.scheduled_agent import ScheduledAgent
            if isinstance(recipient, ScheduledAgent) and recipient.scheduler and recipient.scheduler.running():
                # ScheduledAgent由scheduler驱动，其他Agent由send/receive/generate_reply的loop驱动
                # ScheduledAgent receive后直接就return了，再异步act
                # 因此这里不能直接return，而需要确保所有异步act都执行完成了
                await recipient.scheduler.schedule()

            metrics.end_time_ms = time.time_ns() // 1_000_000
            ask_user = True if answer and answer.action_report and any(
                [act_out.ask_user for act_out in answer.action_report]) else False
            ## 终止状态要排除正常返回的报告Agent
            # terminate = True if answer and answer.action_report and any([act_out.terminate for act_out in answer.action_report]) else False
            ask_type = AskUserType.NESTED_AGENT if ask_user else None
            LOGGER.info(f"[ACTION]---------->   Agent Action [{sender.name}] --> answer: {answer}")
            return ActionOutput.from_dict({
                "action_id": action_id or self.action_uid,
                "is_exe_success": True,
                "thoughts": action_input.thought,
                "action": action_input.agent_name,
                "name": self.name,
                "state": Status.TODO.value,
                "action_input": action_input.content,
                "content": answer.message_id or answer.content if answer else "Not Have Answer！",
                "observations": answer.message_id or answer.content if answer else "Not Have Answer！",
                "ask_user": ask_user,
                "ask_type": ask_type,
                "metrics": metrics,
            })

        except Exception as e:
            logger.exception(f"Agent Action Run Failed!{str(e)}")
            metrics.end_time_ms = time.time_ns() // 1_000_000
            return ActionOutput.from_dict({
                "action_id": self.action_uid,
                "is_exe_success": False,
                "thoughts": action_input.thought,
                "action": action_input.agent_name,
                "name": self.name,
                "state": Status.FAILED.value,
                "action_input": action_input.to_dict(),
                "content": f"Agent启动异常！{str(e)}",
                "metrics": metrics,
            })


class KnowledgeRetrieveActionInput(BaseModel):
    query: str = Field(..., description="query to retrieve")
    knowledge_ids: Optional[List[str]] = Field(None, description="selected knowledge ids")
    func: Optional[str] = Field("search",
                                description="search(语义搜索知识) | read(读取文档内容) | doc_ls(查文档大纲目录) | ls(查阅知识库目录)")
    doc_uuids: Optional[List[str]] = Field(
        None, description="selected doc uuids"
    )
    header: Optional[str] = Field("header", description="具体文档大纲标题")
    intention: Optional[str] = Field("", description="intention to the user")
    thought: Optional[str] = Field("", description="thoughts to the user")


class KnowledgeRetrieveAction(Action[KnowledgeRetrieveActionInput]):
    name = "KnowledgeRetrieve"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag: str = SystemVisTag.VisTool.value

    @property
    def resource_need(self) -> Optional[ResourceType]:
        return ResourceType.KnowledgePack

    def _inited_resource(self) -> Optional[KnowledgePackSearchResource]:
        def _unpack(resource: Resource) -> Optional[Resource]:
            if not resource:
                return None
            elif isinstance(resource, KnowledgePackSearchResource):
                return resource
            elif isinstance(resource, ResourcePack) and resource.sub_resources:
                return next(
                    (r2 for r1 in resource.sub_resources if (r2 := _unpack(r1))), None
                )
            else:
                return None

        return _unpack(self.resource)

    async def _retrieve_doc_directory(
        self,
        resource: Optional[KnowledgePackSearchResource] = None,
        agent: Optional[ConversableAgent] = None,
    ) -> ActionOutput:
        output_dict = {
            "is_exe_success": True,
            "action": "查阅文档目录大纲",
            "action_name": self.action_input.intention,
            "action_input": self.action_input.query,
        }
        try:
            summary_res = await resource.get_directory(
                query=self.action_input.query,
                selected_knowledge_ids=self.action_input.knowledge_ids,
                doc_uuids=self.action_input.doc_uuids,
            )
            summary: str = (
                str(summary_res.directory)
                if summary_res
                   and isinstance(summary_res, KnowledgeSearchResponse)
                   and summary_res.directory
                else "未找到相关目录知识"
            )
            output_dict["content"] = summary
            output_dict["resource_value"] = (
                summary_res.dict()
                if isinstance(summary_res, KnowledgeSearchResponse)
                else None
            )
            LOGGER.info(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> action_output: {output_dict} "
            )
        except Exception as e:
            output_dict["is_exe_success"] = False
            output_dict["content"] = "知识目录检索失败"
            output_dict["view"] = "知识目录检索失败"
            LOGGER.exception(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> exception: {repr(e)} "
            )
        action_output = ActionOutput.from_dict(output_dict)
        return action_output

    async def _retrieve_book_directory(self,
                                       resource: Optional[KnowledgePackSearchResource] = None,
                                       agent: Optional[ConversableAgent] = None,
                                       ) -> ActionOutput:
        output_dict = {
            "is_exe_success": True,
            "action": "检索语雀知识库目录",
            "action_name": self.action_input.intention,
            "action_input": self.action_input.query,
        }
        try:
            summary_res = await resource.get_directory(
                query=self.action_input.query,
                selected_knowledge_ids=self.action_input.knowledge_ids,
                directory_mode="book",
            )
            summary: str = (
                str(summary_res.book_directory)
                if summary_res
                   and isinstance(summary_res, KnowledgeSearchResponse)
                   and summary_res.book_directory
                else "未找到相关语雀知识库目录知识"
            )
            output_dict["content"] = summary
            output_dict["resource_value"] = (
                summary_res.dict()
                if isinstance(summary_res, KnowledgeSearchResponse)
                else None
            )
            LOGGER.info(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> action_output: {output_dict} "
            )
        except Exception as e:
            output_dict["is_exe_success"] = False
            output_dict["content"] = "book目录检索失败"
            output_dict["view"] = "book目录检索失败"
            LOGGER.exception(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> exception: {repr(e)} "
            )
        action_output = ActionOutput.from_dict(output_dict)
        return action_output

    async def _read_document(self,
                             resource: Optional[KnowledgePackSearchResource] = None,
                             agent: Optional[ConversableAgent] = None,
                             ) -> ActionOutput:
        output_dict = {
            "is_exe_success": True,
            "action": "读取文档内容",
            "action_name": self.action_input.intention,
            "action_input": self.action_input.query,
        }
        try:
            summary_res = await resource.read_document(
                query=self.action_input.query,
                selected_knowledge_ids=self.action_input.knowledge_ids,
                doc_uuids=self.action_input.doc_uuids,
                header=self.action_input.header
            )
            summary: str = (
                "\n".join(summary_res.document_contents)
                if summary_res
                   and isinstance(summary_res, KnowledgeSearchResponse)
                   and summary_res.document_contents
                else "未找到相关单个文档知识"
            )
            output_dict["content"] = summary
            output_dict["resource_value"] = (
                summary_res.dict()
                if isinstance(summary_res, KnowledgeSearchResponse)
                else None
            )
            LOGGER.info(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> action_output: {output_dict} "
            )
        except Exception as e:
            output_dict["is_exe_success"] = False
            output_dict["content"] = "单个文档检索失败"
            output_dict["view"] = "单个文档检索失败"
            LOGGER.exception(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> exception: {repr(e)} "
            )
        action_output = ActionOutput.from_dict(output_dict)
        return action_output

    async def _retrieve_knowledge_summary(self,
                                          resource: Optional[KnowledgePackSearchResource] = None,
                                          agent: Optional[ConversableAgent] = None,
                                          ) -> ActionOutput:
        output_dict = {
            "is_exe_success": True,
            "action": "知识检索",
            "action_name": self.action_input.intention,
            "thoughts": self.action_input.thought,
            "action_input": self.action_input.query,
        }
        try:
            summary_res = await resource.get_summary(
                query=self.action_input.query,
                selected_knowledge_ids=self.action_input.knowledge_ids,
            )
            summary: str = (
                summary_res.summary_content
                if summary_res
                   and isinstance(summary_res, KnowledgeSearchResponse)
                   and summary_res.summary_content
                else "未找到相关知识"
            )
            output_dict["content"] = summary
            output_dict["resource_value"] = (
                summary_res.dict()
                if isinstance(summary_res, KnowledgeSearchResponse)
                else None
            )
            LOGGER.info(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> action_output: {output_dict} "
            )
        except Exception as e:
            output_dict["is_exe_success"] = False
            output_dict["content"] = "知识检索失败"
            output_dict["view"] = "知识检索失败"
            LOGGER.exception(
                f"[ACTION]---------->   "
                f"KnowledgeRetrieveAction [{agent.name if agent else None}] --> exception: {repr(e)} "
            )
        action_output = ActionOutput.from_dict(output_dict)
        return action_output

    async def push_action_init_msg(self, gpts_memory, agent, agent_context, message_id,
                                   start_time: Optional[Any] = None):

        init_action_report = ActionOutput(
            name=self.name,
            content='正在检索知识..',
            view=await self.gen_view(message_id=message_id, tool_call_id=self.action_uid,
                                     tool_name=self.action_input.intention,
                                     args=self.action_input.query,
                                     status=Status.RUNNING.value,
                                     start_time=start_time),
            action_id=self.action_uid,
            action=self.action_input.intention,
            action_name=self.action_input.thought,
            action_input=self.action_input.query,
            state=Status.RUNNING.value,
        )

        ## 展示工具任务基础信息
        await gpts_memory.push_message(conv_id=agent.agent_context.conv_id, stream_msg={
            "uid": message_id,
            "type": "all",
            "sender": agent.name or agent.role,
            "sender_role": agent.role,
            "message_id": message_id,
            "avatar": agent.avatar,
            "conv_id": agent_context.conv_id,
            "conv_session_uid": agent_context.conv_session_id,
            "app_code": agent_context.gpts_app_code,
            "start_time": start_time,
            "action_report": [init_action_report]
        }, )

    async def run(
        self,
        ai_message: str = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        logger.info(f"{self.name} action run!")
        agent: Optional[ConversableAgent] = kwargs.get("agent", None)
        start_time = datetime.now()
        metrics = ActionInferenceMetrics()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        try:
            with root_tracer.start_span(
                "agent.resource.knowledge_retrieve",
                metadata={
                    "message_id": kwargs.get("message_id"),
                    "rag_span_type": "knowledge_retrieve",
                    "conv_id": agent.agent_context.conv_id if agent else None,
                    "app_code": agent.agent_context.gpts_app_code if agent else None,
                },
            ) as span:
                agent_context: AgentContext = kwargs.get('agent_context')
                action_id = kwargs.get("action_id", None)
                message_id = kwargs.get("message_id", None)
                memory: AgentMemory = kwargs.get('memory')
                resource_map: dict[str, List[Resource]] = kwargs.get("resource_map")
                # resource: Resource = kwargs.get("resource")

                self._render = kwargs.get("render_protocol") or self._render
                ## 推送工具执行初始化消息
                await self.push_action_init_msg(gpts_memory=memory.gpts_memory, agent=agent,
                                                agent_context=agent_context,
                                                message_id=message_id, start_time=start_time)

                if resource_map:
                    resource_lst = resource_map.get(KnowledgePackSearchResource.type())
                    resource = resource_lst[0] if resource_lst else None
                else:
                    resource = self._inited_resource()
                if not resource:
                    raise RuntimeError("knowledge resource is empty or not init")
                if self.action_input.func == KnowledgeActionOperation.DOC_LS.action:
                    # func1: 查文档目录大纲
                    action_out = await self._retrieve_doc_directory(
                        resource=resource,
                        agent=agent
                    )
                elif self.action_input.func == KnowledgeActionOperation.LS.action:
                    # func2: 查知识库目录
                    action_out = await self._retrieve_book_directory(
                        resource=resource, agent=agent
                    )
                elif self.action_input.func == KnowledgeActionOperation.READ.action:
                    # func3: 检索文档内容
                    action_out = await self._read_document(
                        resource=resource, agent=agent
                    )
                else:
                    # func4: 默认的检索所有知识
                    action_out = await self._retrieve_knowledge_summary(
                        resource=resource, agent=agent
                    )

                metrics.end_time_ms = time.time_ns() // 1_000_000
                metrics.result_tokens = len(str(action_out.content))
                cost_ms = metrics.end_time_ms - metrics.start_time_ms
                metrics.cost_seconds = round(cost_ms / 1000, 2)

                action_out.metrics = metrics

                status = Status.COMPLETE.value if action_out.is_exe_success else Status.FAILED.value
                err_msg = action_out.view if not action_out.is_exe_success else None
                action_out.name = self.name
                action_out.state = Status.COMPLETE.value
                action_out.action_id = action_id or self.action_uid
                kn_view = await self.gen_view(message_id=message_id, tool_call_id=action_out.action_id,
                                              status=status, tool_name=action_out.action_name,
                                              args=action_out.action_input, tool_result=action_out.content,
                                              err_msg=err_msg, tool_cost=metrics.cost_seconds,
                                              start_time=start_time)
                # ref_view = None
                # if action_out.resource_value:
                #     ref_view = await self._render_reference_view(self._render, action_out.resource_value, message_id)
                # if ref_view:
                #     action_out.view = kn_view + "\n" + ref_view
                # else:
                action_out.view = kn_view
                action_out.thoughts = self.action_input.thought
                return action_out
        except Exception as e:
            logger.exception(f"Knowledge Action Run Failed!{str(e)}")
            metrics.end_time_ms = time.time_ns() // 1_000_000
            return ActionOutput.from_dict({
                "action_id": self.action_uid,
                "is_exe_success": False,
                "thoughts": self.action_input.thought,
                "action": self.action_input.func,
                "action_input": self.action_input.query,
                "name": self.name,
                "state": Status.FAILED.value,
                "content": str(e),
                "metrics": metrics,
            })

    async def gen_view(self, message_id, tool_call_id, status,
                       tool_name: str, tool_description: Optional[str] = None,
                       args: Optional[Any] = None,
                       out_type: Optional[str] = "markdown",
                       tool_result: Optional[Any] = None, err_msg: Optional[str] = None, tool_cost: float = 0,
                       start_time: Optional[Any] = None, **kwargs):
        # 设置进度
        progress = 100 if status == "completed" else (
            50 if status == "running" else 0
        )
        # Build visualization content
        drsk_content = VisStepContent(
            uid=tool_call_id,
            message_id=message_id,
            type="all",
            avatar=None,
            tool_name=tool_name,
            tool_desc=tool_description,
            tool_version=None,
            tool_author=None,
            tool_args=args,
            status=status,
            out_type=out_type,
            tool_result=tool_result,
            err_msg=err_msg,
            tool_cost=tool_cost,
            start_time=start_time,
            progress=progress,
        )
        self.action_view_tag: str = SystemVisTag.VisTool.value
        return self.render_protocol.sync_display(
            content=drsk_content.to_dict()
        )

    async def _render_reference_view(
        self, render_protocol, ref_resources: List[dict], message_id: Optional[str] = None
    ) -> str:
        """Render a reference view for the given text."""
        vis_refs = self._render.vis_inst(SystemVisTag.VisRefs.value)
        if not vis_refs:
            return ""
        return vis_refs.sync_display(
            content=ref_resources, uid=self.action_uid + "_ref", message_id=message_id
        )


class UserConfirmAction(Action[None]):
    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        raise NotImplementedError


def get_parent_action_id(action_id: str) -> str:
    idx = action_id.rfind("-")
    return action_id[:idx] if idx > 0 else ""
