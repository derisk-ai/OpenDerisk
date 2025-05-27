import asyncio
import json
import logging
import time
import uuid
from abc import ABC
from copy import deepcopy
from typing import Any, Dict, List, Optional, Type, AsyncGenerator

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from derisk._private.config import Config
from derisk.agent import (
    AgentContext,
    AgentMemory,
    AutoPlanChatManager,
    ConversableAgent,
    EnhancedShortTermMemory,
    GptsMemory,
    HybridMemory,
    LLMConfig,
    ResourceType,
    UserProxyAgent,
    get_agent_manager,
)
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.memory.gpts import GptsMessage
from derisk_ext.vis.gptvis.gpt_vis_converter import GptVisConverter
from derisk.agent.core.schema import Status
from derisk.agent.resource import get_resource_manager, ResourceManager
from derisk.agent.util.llm.llm import LLMStrategyType
from derisk.component import BaseComponent, ComponentType, SystemApp
from derisk.core import PromptTemplate
from derisk.core.awel.flow.flow_factory import FlowCategory
from derisk.core.interface.message import StorageConversation
from derisk.model.cluster import WorkerManagerFactory
from derisk.model.cluster.client import DefaultLLMClient
from derisk.util.executor_utils import ExecutorFactory
from derisk.util.json_utils import serialize
from derisk.util.tracer.tracer_impl import root_tracer
from derisk_app.derisk_server import system_app
from derisk_app.scene.base import ChatScene
from derisk_serve.conversation.serve import Serve as ConversationServe
from derisk_serve.core import blocking_func_to_async
from derisk_serve.prompt.api.endpoints import get_service
from derisk_serve.prompt.service import service as PromptService

from ...rag.retriever.knowledge_space import KnowledgeSpaceRetriever
from ..db import GptsMessagesDao
from ..db.gpts_app import GptsApp, GptsAppDao, GptsAppQuery, GptsAppDetail
from ..db.gpts_conversations_db import GptsConversationsDao, GptsConversationsEntity
from ..team.base import TeamMode
from .derisks_memory import MetaDerisksMessageMemory, MetaDerisksPlansMemory

CFG = Config()

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_conversation(
        conv_id: str,
        select_param: Dict[str, Any],
        model_name: str,
        summary: str,
        app_code: str,
        conv_serve: ConversationServe,
        user_name: Optional[str] = "",
        sys_code: Optional[str] = "",
) -> StorageConversation:
    return StorageConversation(
        conv_uid=conv_id,
        chat_mode=ChatScene.ChatAgent.value(),
        user_name=user_name,
        sys_code=sys_code,
        model_name=model_name,
        summary=summary,
        param_type="derisks",
        param_value=select_param,
        app_code=app_code,
        conv_storage=conv_serve.conv_storage,
        message_storage=conv_serve.message_storage,
    )


class MultiAgents(BaseComponent, ABC):
    name = ComponentType.MULTI_AGENTS

    def init_app(self, system_app: SystemApp):
        system_app.app.include_router(router, prefix="/api", tags=["Multi-Agents"])
        self.system_app = system_app

    def __init__(self, system_app: SystemApp):
        self.gpts_conversations = GptsConversationsDao()
        self.gpts_messages_dao = GptsMessagesDao()

        self.gpts_app = GptsAppDao()
        self.memory = GptsMemory(
            plans_memory=MetaDerisksPlansMemory(),
            message_memory=MetaDerisksMessageMemory(),
        )
        self.agent_memory_map = {}

        super().__init__(system_app)
        self.system_app = system_app

    def on_init(self):
        """Called when init the application.

        Import your own module here to ensure the module is loaded before the
        application starts
        """
        from ..db.gpts_app import (  # noqa: F401
            GptsAppCollectionEntity,
            GptsAppDetailEntity,
            GptsAppEntity,
            UserRecentAppsEntity,
        )

    def after_start(self):
        from derisk_serve.agent.app.controller import gpts_dao

        gpts_dao.init_native_apps()

        gpts_dao.init_native_apps("derisk")

    def get_derisks(self, user_code: str = None, sys_code: str = None):
        apps = self.gpts_app.app_list(
            GptsAppQuery(user_code=user_code, sys_code=sys_code)
        ).app_list
        return apps

    def get_app(self, app_code) -> GptsApp:
        """get app"""
        return self.gpts_app.app_detail(app_code)

    def get_or_build_agent_memory(self, conv_id: str, derisks_name: str) -> AgentMemory:
        from derisk.rag.embedding.embedding_factory import EmbeddingFactory
        from derisk_serve.rag.storage_manager import StorageManager

        executor = self.system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()

        storage_manager = StorageManager.get_instance(self.system_app)
        vector_store = storage_manager.create_vector_store(index_name="_agent_memory_")
        embeddings = EmbeddingFactory.get_instance(self.system_app).create()
        short_term_memory = EnhancedShortTermMemory(
            embeddings, executor=executor, buffer_size=10
        )
        memory = HybridMemory.from_vstore(
            vector_store,
            embeddings=embeddings,
            executor=executor,
            short_term_memory=short_term_memory,
        )
        agent_memory = AgentMemory(memory, gpts_memory=self.memory)

        return agent_memory

    async def _build_hitory_messages(self, gpts_conversations, gpt_app: Optional[GptsApp] = None):
        historical_dialogues: List[GptsMessage] = []
        ## When creating a new gpts conversation record, determine whether to
        # include the history of previous topics according to the application
        # definition.

        # Temporarily use system configuration management, and subsequently use
        # application configuration management
        msg_keep_start = 1
        msg_keep_end = 1

        if CFG.MESSAGES_KEEP_START_ROUNDS and CFG.MESSAGES_KEEP_START_ROUNDS > 0:
            msg_keep_start = CFG.MESSAGES_KEEP_START_ROUNDS
        if CFG.MESSAGES_KEEP_END_ROUNDS and CFG.MESSAGES_KEEP_END_ROUNDS > 0:
            msg_keep_end = CFG.MESSAGES_KEEP_END_ROUNDS
        if gpt_app:
            msg_keep_start = gpt_app.keep_start_rounds
            msg_keep_end = gpt_app.keep_end_rounds

        if msg_keep_start > 0 or msg_keep_end > 0:
            if gpts_conversations and len(gpts_conversations) > 0:
                rely_conversations = []
                if msg_keep_start + msg_keep_end < len(gpts_conversations):
                    if msg_keep_start > 0:
                        front = gpts_conversations[msg_keep_start:]
                        rely_conversations.extend(front)
                    if msg_keep_end > 0:
                        back = gpts_conversations[-msg_keep_end:]
                        rely_conversations.extend(back)
                else:
                    rely_conversations = gpts_conversations
                for gpts_conversation in rely_conversations:
                    temps: List[GptsMessage] = await self.memory.get_messages(
                        gpts_conversation.conv_id
                    )
                    if temps and len(temps) > 1:
                        historical_dialogues.append(temps[0])
                        historical_dialogues.append(temps[-1])
        return historical_dialogues

    async def agent_chat_v2(
            self,
            conv_id: str,
            gpts_name: str,
            user_query: str,
            user_code: str = None,
            sys_code: str = None,
            stream: Optional[bool] = True,
            **ext_info,
    ):
        logger.info(
            f"agent_chat_v2 conv_id:{conv_id},gpts_name:{gpts_name},user_query:"
            f"{user_query}"
        )

        gpts_conversations: List[GptsConversationsEntity] = self.gpts_conversations.get_by_session_id_asc(conv_id)

        logger.info(
            f"gpts_conversations count:{conv_id}, "
            f"{len(gpts_conversations) if gpts_conversations else 0}"
        )
        gpt_chat_order = (
            "1" if not gpts_conversations else str(len(gpts_conversations) + 1)
        )
        agent_conv_id = conv_id + "_" + gpt_chat_order
        message_round = 0
        history_message_count = 0
        is_retry_chat = False
        last_speaker_name = None
        history_messages = None
        gpt_app=None
        if gpts_name == "ai_sre":
            team_mode = TeamMode.AUTO_PLAN.value
        else:
            # Create a new gpts conversation record
            gpt_app: GptsApp = self.gpts_app.app_detail(gpts_name)
            if not gpt_app:
                raise ValueError(f"Not found app {gpts_name}!")
            team_mode = gpt_app.team_mode

        self.gpts_conversations.add(
            GptsConversationsEntity(
                conv_id=agent_conv_id,
                conv_session_id=conv_id,
                user_goal=user_query,
                gpts_name=gpts_name,
                team_mode=team_mode,
                state=Status.RUNNING.value,
                max_auto_reply_round=0,
                auto_reply_count=0,
                user_code=user_code,
                sys_code=sys_code,
            )
        )

        # init gpts  memory
        vis_render = ext_info.get("vis_render", None)

        logger.warning(f"vis_render_protocol:{vis_render} ！")
        # 暂时不支持 增量协议
        ext_info['incremental'] = False
        from derisk_ext.vis.gptvis.gpt_vis_converter_old import GptVisOldConverter
        from derisk_ext.vis.gptvis.gpt_vis_converter_window import GptVisLRConverter
        # vis_protocol = GptVisOldConverter()
        vis_protocol = GptVisLRConverter()

        self.memory.init(
            agent_conv_id,
            history_messages=history_messages,
            start_round=history_message_count,
            vis_converter=vis_protocol,
        )
        # init agent memory
        agent_memory = self.get_or_build_agent_memory(conv_id, gpts_name)

        historical_dialogues = await self._build_hitory_messages(gpts_conversations, gpt_app)
        task = None
        try:
            if gpts_name == "ai_sre":
                from derisk_serve.agent.aisre.aisre_controller import ai_sre_controller
                task = asyncio.create_task(
                    ai_sre_controller.ai_sre_chat(
                        user_query=user_query,
                        conv_session_id=conv_id,
                        conv_uid=agent_conv_id,
                        agent_memory=agent_memory,
                        gpts_conversations=self.gpts_conversations,
                        is_retry_chat=is_retry_chat,
                        last_speaker_name=last_speaker_name,
                        init_message_rounds=message_round,
                        historical_dialogues=historical_dialogues,
                        user_code=user_code,
                        sys_code=sys_code,
                        stream=stream,
                        **ext_info,
                    )
                )
            else:
                task = asyncio.create_task(
                    multi_agents.agent_team_chat_new(
                        user_query=user_query,
                        conv_session_id=conv_id,
                        conv_uid=agent_conv_id,
                        gpts_app=gpt_app,
                        agent_memory=agent_memory,
                        is_retry_chat=is_retry_chat,
                        last_speaker_name=last_speaker_name,
                        init_message_rounds=message_round,
                        historical_dialogues=historical_dialogues,
                        user_code=user_code,
                        sys_code=sys_code,
                        stream=stream,
                        **ext_info,
                    )
                )

            async for chunk in multi_agents.chat_messages(agent_conv_id):
                if chunk and len(chunk) > 0:
                    try:

                        content = json.dumps(
                            {"vis": chunk},
                            default=serialize,
                            ensure_ascii=False,
                        )

                        resp = f"data:{content}\n\n"
                        yield task, resp, agent_conv_id
                    except Exception as e:
                        logger.exception(
                            f"get messages {gpts_name} Exception!" + str(e)
                        )
                        yield task, f"data: {str(e)}\n\n", agent_conv_id

            yield (
                task,
                _format_vis_msg("[DONE]"),
                agent_conv_id,
            )

        except asyncio.CancelledError:
            # 取消时不立即回调
            logger.info("Generator cancelled, delaying callback")
            raise
        except Exception as e:
            logger.exception(f"Agent chat have error!{str(e)}")
            yield task, str(e), agent_conv_id

    async def save_conversation(self, agent_conv_id: str, current_message: StorageConversation):
        logger.info(f"Agent chat end, save conversation {agent_conv_id}!")
        """统一保存对话结果的逻辑"""
        final_message = ""
        try:
            final_message = await self.stable_message(agent_conv_id)
        except Exception as e:
            logger.exception(f"获取{agent_conv_id}最终消息异常: {str(e)}")

        self.memory.clear(agent_conv_id)
        current_message.add_view_message(final_message)
        current_message.end_current_round()
        current_message.save_to_storage()

    async def app_agent_chat_v2(
            self,
            conv_uid: str,
            gpts_name: str,
            user_query: str,
            background_tasks: BackgroundTasks,
            user_code: str = None,
            sys_code: str = None,
            stream: Optional[bool] = True,
            **ext_info,
    ) -> StreamingResponse:
        logger.info(f"app_agent_chat:{gpts_name},{user_query},{conv_uid}")
        # Temporary compatible scenario messages
        conv_serve = ConversationServe.get_instance(CFG.SYSTEM_APP)
        current_message: StorageConversation = _build_conversation(
            conv_id=conv_uid,
            select_param=gpts_name,
            summary=user_query,
            model_name="",
            app_code=gpts_name,
            conv_serve=conv_serve,
            user_name=user_code,
        )
        current_message.save_to_storage()
        current_message.start_new_round()
        current_message.add_user_message(user_query)

        # 创建独立的任务队列
        task_queue = asyncio.Queue()
        # 状态标志
        processing_complete = asyncio.Event()

        async def agent_processor():
            """独立处理生成器的协程"""
            try:
                async for task, chunk, agent_conv_id in multi_agents.agent_chat_v2(
                        conv_uid,
                        gpts_name,
                        user_query,
                        user_code,
                        sys_code,
                        **ext_info,
                        stream=stream,
                ):
                    await task_queue.put((chunk, agent_conv_id))
            finally:
                # 最终标记处理完成
                processing_complete.set()

        # 启动独立处理任务
        processor_task = asyncio.create_task(agent_processor())

        async def stream_generator() -> AsyncGenerator[str, None]:
            """带断开检测的流生成器"""
            client_disconnected = False
            agent_conv_id = None
            try:
                while True:
                    try:
                        # 设置超时避免永久阻塞
                        chunk, agent_conv_id = await asyncio.wait_for(task_queue.get(), timeout=0.01)
                        agent_conv_id = agent_conv_id
                        yield chunk
                        task_queue.task_done()
                    except asyncio.TimeoutError:
                        if processing_complete.is_set():
                            break
            except asyncio.CancelledError:
                logger.info(f"Client disconnected: {conv_uid}")
                client_disconnected = True
                raise
            finally:
                if client_disconnected:
                    # 启动后台清理任务
                    async def background_cleanup():
                        try:
                            # 等待剩余数据处理完成（最多等待30秒）
                            await asyncio.wait_for(processing_complete.wait(), timeout=30 * 60)
                        except asyncio.TimeoutError:
                            logger.warning(f"Timeout waiting for processing: {conv_uid}")
                        finally:
                            # 确保保存最终状态
                            agent_conv_id = conv_uid
                            if not task_queue.empty():
                                logger.info(f"Draining {task_queue.qsize()} remaining messages")
                                while not task_queue.empty():
                                    chunk, agent_conv_id = task_queue.get_nowait()
                            # 获取最终对话ID
                            await multi_agents.save_conversation(agent_conv_id, current_message)

                    background_tasks.add_task(background_cleanup)
                else:
                    # 获取最终对话ID
                    await multi_agents.save_conversation(agent_conv_id, current_message)
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"X-Conversation-ID": conv_uid}
        )

    async def _build_agent_by_gpts(
            self,
            context: AgentContext,
            agent_memory: AgentMemory,
            rm: ResourceManager,
            app: GptsApp,
            **kwargs
    ) -> ConversableAgent:
        """Build a dialogue target agent through gpts configuration"""
        logger.info(f"_build_agent_by_gpts:{app.app_code},{app.app_name}")
        employees: List[ConversableAgent] = []
        if app.details is not None and len(app.details) > 0:
            employees: List[ConversableAgent] = await self._build_employees(
                context, agent_memory, rm, [deepcopy(item) for item in app.details]
            )
        if "extra_agents" in kwargs and kwargs.get("extra_agents"):
            employees.extend([await self._build_agent_by_gpts(
                context, agent_memory, rm, deepcopy(self.gpts_app.app_detail(extra_agent))
            ) for extra_agent in kwargs.get("extra_agents") if
                              not next((employee for employee in employees if employee.name == extra_agent), None)])
        team_mode = TeamMode(app.team_mode)
        prompt_service: PromptService = get_service()
        if team_mode == TeamMode.SINGLE_AGENT:
            if employees is not None and len(employees) == 1:
                recipient = employees[0]
            else:
                single_context = app.team_context
                cls: Type[ConversableAgent] = self.agent_manage.get_by_name(
                    single_context.agent_name
                )

                llm_config = LLMConfig(
                    llm_client=self.llm_provider,
                    lm_strategy=LLMStrategyType(single_context.llm_strategy),
                    strategy_context=single_context.llm_strategy_value,
                )
                prompt_template = None
                if single_context.prompt_template:
                    prompt_template: PromptTemplate = prompt_service.get_template(
                        prompt_code=single_context.prompt_template
                    )
                depend_resource = await blocking_func_to_async(
                    CFG.SYSTEM_APP, rm.build_resource, single_context.resources
                )

                recipient = (
                    await cls()
                    .bind(context)
                    .bind(agent_memory)
                    .bind(llm_config)
                    .bind(depend_resource)
                    .bind(prompt_template)
                    .build()
                )
                recipient.profile.name = app.app_name
                recipient.profile.desc = app.app_describe
                recipient.profile.avatar = app.icon
            return recipient
        elif TeamMode.AUTO_PLAN == team_mode:
            if app.team_context:
                agent_manager = get_agent_manager()
                auto_team_ctx = app.team_context

                manager_cls: Type[ConversableAgent] = agent_manager.get_by_name(
                    auto_team_ctx.teamleader
                )
                manager = manager_cls()
                if isinstance(manager, ManagerAgent) and len(employees) > 0:
                    manager.hire(employees)

                llm_config = LLMConfig(
                    llm_client=self.llm_provider,
                    llm_strategy=LLMStrategyType(auto_team_ctx.llm_strategy),
                    strategy_context=auto_team_ctx.llm_strategy_value,
                )
                manager.bind(llm_config)

                if auto_team_ctx.prompt_template:
                    prompt_template: PromptTemplate = prompt_service.get_template(
                        prompt_code=auto_team_ctx.prompt_template
                    )
                    manager.bind(prompt_template)
                if auto_team_ctx.resources:
                    depend_resource = await blocking_func_to_async(
                        CFG.SYSTEM_APP, rm.build_resource, auto_team_ctx.resources
                    )
                    manager.bind(depend_resource)

                manager = await manager.bind(context).bind(agent_memory).build()
            else:
                ## default
                manager = AutoPlanChatManager()
                llm_config = employees[0].llm_config

                if not employees or len(employees) < 0:
                    raise ValueError("APP exception no available agent！")
                manager = (
                    await manager.bind(context)
                    .bind(agent_memory)
                    .bind(llm_config)
                    .build()
                )
                manager.hire(employees)

            manager.profile.name = app.app_name
            manager.profile.desc = app.app_describe
            manager.profile.avatar = app.icon
            logger.info(
                f"_build_agent_by_gpts return:{manager.profile.name},{manager.profile.desc},{id(manager)}"
            )
            return manager
        elif TeamMode.NATIVE_APP == team_mode:
            raise ValueError("Native APP chat not supported!")
        else:
            raise ValueError(f"Unknown Agent Team Mode!{team_mode}")

    async def _build_employees(
            self,
            context: AgentContext,
            agent_memory: AgentMemory,
            rm: ResourceManager,
            app_details: List[GptsAppDetail],
    ) -> List[ConversableAgent]:
        """Constructing dialogue members through gpts-related Agent or gpts app information."""
        logger.info(
            f"_build_employees:{[item.agent_role + ',' + item.agent_name for item in app_details] if app_details else ''}"
        )
        employees: List[ConversableAgent] = []
        prompt_service: PromptService = get_service()
        for record in app_details:
            logger.info(f"_build_employees循环:{record.agent_role},{record.agent_name}")
            if record.type == "app":
                gpt_app: GptsApp = deepcopy(self.gpts_app.app_detail(record.agent_role))
                if not gpt_app:
                    raise ValueError(f"Not found app {record.agent_role}!")
                employee_agent = await self._build_agent_by_gpts(
                    context, agent_memory, rm, gpt_app
                )
                logger.info(
                    f"append employee_agent:{employee_agent.profile.name},{employee_agent.profile.desc},{id(employee_agent)}"
                )
                employees.append(employee_agent)
            else:
                cls: Type[ConversableAgent] = self.agent_manage.get_by_name(
                    record.agent_role
                )
                llm_config = LLMConfig(
                    llm_client=self.llm_provider,
                    lm_strategy=LLMStrategyType(record.llm_strategy),
                    strategy_context=record.llm_strategy_value,
                )
                prompt_template = None
                if record.prompt_template:
                    prompt_template: PromptTemplate = prompt_service.get_template(
                        prompt_code=record.prompt_template
                    )
                depend_resource = await blocking_func_to_async(
                    CFG.SYSTEM_APP, rm.build_resource, record.resources
                )
                agent = (
                    await cls()
                    .bind(context)
                    .bind(agent_memory)
                    .bind(llm_config)
                    .bind(depend_resource)
                    .bind(prompt_template)
                    .build()
                )
                if record.agent_describe:
                    temp_profile = agent.profile.copy()
                    temp_profile.desc = record.agent_describe
                    temp_profile.name = record.agent_name
                    agent.bind(temp_profile)
                employees.append(agent)
        logger.info(
            f"_build_employees return:{[item.profile.name if item.profile.name else '' + ',' + str(id(item)) for item in employees]}"
        )
        return employees

    async def agent_team_chat_new(
            self,
            user_query: str,
            conv_session_id: str,
            conv_uid: str,
            gpts_app: GptsApp,
            agent_memory: AgentMemory,
            is_retry_chat: bool = False,
            last_speaker_name: str = None,
            init_message_rounds: int = 0,
            link_sender: ConversableAgent = None,
            app_link_start: bool = False,
            historical_dialogues: Optional[List[GptsMessage]] = None,
            rely_messages: Optional[List[GptsMessage]] = None,
            stream: Optional[bool] = True,
            **ext_info,
    ):
        gpts_status = Status.COMPLETE.value
        try:
            self.agent_manage = get_agent_manager()

            context: AgentContext = AgentContext(
                conv_id=conv_uid,
                conv_session_id=conv_session_id,
                trace_id=ext_info.get("trace_id", uuid.uuid4().hex),
                rpc_id=ext_info.get("rpc_id", "0.1"),
                gpts_app_code=gpts_app.app_code,
                gpts_app_name=gpts_app.app_name,
                language=gpts_app.language,
                app_link_start=app_link_start,
                incremental=ext_info.get("incremental", False),
                stream=stream,
            )

            root_tracer.start_span(
                operation_name="agent_chat", parent_span_id=context.trace_id
            )

            rm = get_resource_manager()

            # init llm provider
            ### init chat param
            worker_manager = CFG.SYSTEM_APP.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            self.llm_provider = DefaultLLMClient(
                worker_manager, auto_convert_message=True
            )

            recipient = await self._build_agent_by_gpts(
                context, agent_memory, rm, gpts_app, **ext_info,
            )

            if is_retry_chat:
                # retry chat
                self.gpts_conversations.update(conv_uid, Status.RUNNING.value)

            user_proxy = None
            if link_sender:
                await link_sender.initiate_chat(
                    recipient=recipient,
                    message=user_query,
                    is_retry_chat=is_retry_chat,
                    last_speaker_name=last_speaker_name,
                    message_rounds=init_message_rounds,
                )
            else:
                user_proxy: UserProxyAgent = (
                    await UserProxyAgent().bind(context).bind(agent_memory).build()
                )
                user_code = ext_info.get("user_code", None)
                if user_code:
                    app_config = self.system_app.config.configs.get("app_config")
                    web_config = app_config.service.web
                    user_proxy.profile.avatar = f"{web_config.web_url}/user/avatar?loginName={user_code}"
                await user_proxy.initiate_chat(
                    recipient=recipient,
                    message=user_query,
                    is_retry_chat=is_retry_chat,
                    last_speaker_name=last_speaker_name,
                    message_rounds=init_message_rounds,
                    historical_dialogues=user_proxy.convert_to_agent_message(
                        historical_dialogues
                    ),
                    rely_messages=rely_messages,
                    **ext_info,
                )

            if user_proxy:
                # Check if the user has received a question.
                if user_proxy.have_ask_user():
                    gpts_status = Status.WAITING.value
            if not app_link_start:
                self.gpts_conversations.update(conv_uid, gpts_status)
        except Exception as e:
            logger.error(f"chat abnormal termination！{str(e)}", e)
            self.gpts_conversations.update(conv_uid, Status.FAILED.value)
            raise ValueError(f"The conversation is abnormal!{str(e)}")
        finally:
            if not app_link_start:
                await self.memory.complete(conv_uid)

        return conv_uid

    async def chat_messages(
            self,
            conv_id: str,
            user_code: str = None,
            system_app: str = None,
    ):
        while True:
            queue = self.memory.queue(conv_id)
            if not queue:
                break
            item = await queue.get()
            if item == "[DONE]":
                queue.task_done()
                break
            else:
                yield item
                await asyncio.sleep(0.005)

    async def stable_message(
            self, conv_id: str, user_code: str = None, system_app: str = None
    ):
        gpts_conv = self.gpts_conversations.get_by_conv_id(conv_id)
        if gpts_conv:
            is_complete = (
                True
                if gpts_conv.state
                   in [Status.COMPLETE.value, Status.WAITING.value, Status.FAILED.value]
                else False
            )
            if is_complete:
                return await self.memory.vis_final(conv_id)
            else:
                # 未完成 也可以给稳定消息（落库部分）
                return await self.memory.vis_final(conv_id)

        else:
            raise Exception("No conversation record found!")

    def gpts_conv_list(self, user_code: str = None, system_app: str = None):
        return self.gpts_conversations.get_convs(user_code, system_app)

    async def topic_terminate(
            self,
            conv_id: str,
    ):
        gpts_conversations: List[GptsConversationsEntity] = (
            self.gpts_conversations.get_by_session_id_asc(conv_id)
        )
        # 检查最后一个对话记录是否完成，如果是等待状态，则要继续进行当前对话
        if gpts_conversations and len(gpts_conversations) > 0:
            last_gpts_conversation: GptsConversationsEntity = gpts_conversations[-1]
            if last_gpts_conversation.state == Status.WAITING.value:
                self.gpts_conversations.update(
                    last_gpts_conversation.conv_id, Status.COMPLETE.value
                )

    async def get_knowledge_resources(self, app_code: str, question: str):
        """Get the knowledge resources."""
        context = []
        app: GptsApp = self.get_app(app_code)
        if app and app.details and len(app.details) > 0:
            for detail in app.details:
                if detail and detail.resources and len(detail.resources) > 0:
                    for resource in detail.resources:
                        if resource.type == ResourceType.Knowledge:
                            retriever = KnowledgeSpaceRetriever(
                                space_id=str(resource.value),
                                top_k=CFG.KNOWLEDGE_SEARCH_TOP_SIZE,
                            )
                            chunks = await retriever.aretrieve_with_scores(
                                question, score_threshold=0.3
                            )
                            context.extend([chunk.content for chunk in chunks])
                        else:
                            continue
        return context


def _format_vis_msg(msg: str):
    content = json.dumps({"vis": msg}, default=serialize, ensure_ascii=False)
    return f"data:{content} \n\n"


multi_agents = MultiAgents(system_app)
